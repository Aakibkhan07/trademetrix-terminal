import hashlib
import logging
import time
from datetime import UTC, datetime
from typing import Any

from core.db import async_supabase, get_supabase
from core.models import Exchange, InstrumentType, NormalizedOrder, OptionType, OrderResult, OrderSide, OrderStatus, OrderType, ProductType
from core.safe_query import async_safe_single
from execution.audit import log_execution_event, log_validation_failure
from execution.broker_adapter import BrokerExecutionAdapter
from execution.event_bus import execution_event_bus, ExecutionEvent, fire_and_forget
from execution.models import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionState,
    EXECUTION_STATE_TRANSITIONS,
)
from execution.observability import execution_observability
from execution.retry import retry_with_backoff
from execution.validation import validate_order
from risk.manager import risk_manager
from risk.models import RiskDecision

logger = logging.getLogger(__name__)


def _generate_execution_request_id(user_id: str, broker: str, symbol: str, side: str, timestamp: float) -> str:
    raw = f"{user_id}:{broker}:{symbol}:{side}:{timestamp}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _compute_payload_hash(payload: dict) -> str:
    import json
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _empty_req(user_id: str, broker: str) -> ExecutionRequest:
    return ExecutionRequest(user_id=user_id, broker=broker, symbol="", side="", quantity=0, source="system")


def _transition_allowed(current: ExecutionState, target: ExecutionState) -> bool:
    allowed = EXECUTION_STATE_TRANSITIONS.get(current, set())
    return target in allowed


class ExecutionManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._adapters: dict[str, Any] = {}

    async def place_order(self, req: ExecutionRequest) -> ExecutionResult:
        exec_start = time.monotonic()
        request_id = req.execution_request_id or _generate_execution_request_id(
            req.user_id, req.broker, req.symbol, req.side, time.time(),
        )

        if not req.execution_request_id:
            req.execution_request_id = request_id

        order = self._build_normalized_order(req)
        if not order:
            return ExecutionResult(
                success=False, execution_request_id=request_id,
                state=ExecutionState.FAILED, message="Failed to build order",
                error_code="ORDER_BUILD_FAILED",
            )

        state = ExecutionState.NEW
        result = ExecutionResult(execution_request_id=request_id)

        try:
            state = ExecutionState.VALIDATED
            validation = await validate_order(order, req.user_id)

            if not validation.valid:
                state = ExecutionState.REJECTED
                execution_observability.record_validation_failure()
                payload = order.model_dump(mode="json")
                await log_validation_failure(req.user_id, req.broker, validation.errors, payload)
                self._publish_event("OrderRejected", request_id, req, state, message="Validation failed")
                return ExecutionResult(
                    success=False, execution_request_id=request_id,
                    state=ExecutionState.REJECTED, message="Validation failed",
                    error_code="VALIDATION_FAILED",
                )

            risk_result = await risk_manager.evaluate(req)
            if risk_result.decision == RiskDecision.REJECTED:
                state = ExecutionState.REJECTED
                execution_observability.record_validation_failure()
                payload = order.model_dump(mode="json")
                await log_validation_failure(req.user_id, req.broker, [risk_result.message], payload)
                self._publish_event("OrderRejected", request_id, req, state, message=risk_result.message)
                return ExecutionResult(
                    success=False, execution_request_id=request_id,
                    state=ExecutionState.REJECTED, message=risk_result.message,
                    error_code="RISK_REJECTED",
                )

            state = ExecutionState.SENT
            adapter = await self._get_adapter(req.user_id, req.broker)
            if not adapter:
                state = ExecutionState.FAILED
                self._publish_event("OrderFailed", request_id, req, state, message="Broker not available")
                return ExecutionResult(
                    success=False, execution_request_id=request_id,
                    state=ExecutionState.FAILED, message="Broker not available",
                    error_code="BROKER_UNAVAILABLE",
                )

            order_inserted = await self._insert_order_atomic(order)
            if order_inserted is None:
                execution_observability.record_duplicate_prevented()
                existing = await self._check_existing_order(request_id)
                return ExecutionResult(
                    success=True,
                    execution_request_id=request_id,
                    broker_order_id=existing.get("broker_order_id", ""),
                    state=ExecutionState.FILLED if existing and existing.get("status") == "FILLED" else ExecutionState.PENDING,
                    message="DUPLICATE_REQUEST",
                )

            broker_result = await self._execute_with_retry(adapter, order, request_id, req)

            elapsed_ms = round((time.monotonic() - exec_start) * 1000, 2)

            if broker_result.success:
                state = ExecutionState.FILLED
                order.broker_order_id = broker_result.broker_order_id
                order.status = OrderStatus.FILLED
                await self._update_order_in_db(order, req.user_id, broker_result.broker_order_id)

                execution_observability.record_order_placed()
                execution_observability.record_latency(elapsed_ms, req.broker)
                self._publish_event("OrderPlaced", request_id, req, state, message="Order placed successfully")
                try:
                    from portfolio.manager import portfolio_manager as _pm
                    fire_and_forget(_pm.refresh(req.user_id, req.broker))
                except Exception as e:
                    logger.warning("Portfolio refresh fire-and-forget failed: %s", e)

                await log_execution_event(
                    user_id=req.user_id, broker=req.broker, action="placed",
                    execution_request_id=request_id, broker_order_id=broker_result.broker_order_id,
                    symbol=req.symbol, side=req.side, quantity=req.quantity, price=req.price,
                    latency_ms=elapsed_ms, status="filled", message="Order placed successfully",
                    payload=payload, result={"broker_order_id": broker_result.broker_order_id},
                )

                result = ExecutionResult(
                    success=True, execution_request_id=request_id,
                    broker_order_id=broker_result.broker_order_id,
                    state=ExecutionState.FILLED, message="Order placed successfully",
                    latency_ms=elapsed_ms,
                )
            else:
                state = ExecutionState.REJECTED
                execution_observability.record_order_failed()
                execution_observability.record_broker_error(req.broker)
                self._publish_event("OrderRejected", request_id, req, state, message=broker_result.message)

                await log_execution_event(
                    user_id=req.user_id, broker=req.broker, action="failed",
                    execution_request_id=request_id, symbol=req.symbol, side=req.side,
                    quantity=req.quantity, price=req.price, latency_ms=elapsed_ms,
                    status="rejected", message=broker_result.message,
                    payload=payload, result={"error": broker_result.message},
                )

                result = ExecutionResult(
                    success=False, execution_request_id=request_id,
                    state=ExecutionState.REJECTED, message=broker_result.message,
                    error_code="ORDER_REJECTED", latency_ms=elapsed_ms,
                )

        except Exception as e:
            elapsed_ms = round((time.monotonic() - exec_start) * 1000, 2)
            state = ExecutionState.FAILED
            execution_observability.record_order_failed()
            execution_observability.record_broker_error(req.broker)
            self._publish_event("OrderFailed", request_id, req, state, message=str(e))

            await log_execution_event(
                user_id=req.user_id, broker=req.broker, action="error",
                execution_request_id=request_id, symbol=req.symbol, side=req.side,
                quantity=req.quantity, price=req.price, latency_ms=elapsed_ms,
                status="failed", message=str(e), payload=payload,
            )

            result = ExecutionResult(
                success=False, execution_request_id=request_id,
                state=ExecutionState.FAILED, message=str(e),
                error_code="EXECUTION_FAILED", latency_ms=elapsed_ms,
            )

        return result

    async def modify_order(self, req: ExecutionRequest, order_id: str, changes: dict) -> ExecutionResult:
        exec_start = time.monotonic()
        request_id = _generate_execution_request_id(req.user_id, req.broker, f"modify:{order_id}", "", time.time())

        try:
            adapter = await self._get_adapter(req.user_id, req.broker)
            if not adapter:
                return ExecutionResult(
                    success=False, execution_request_id=request_id,
                    state=ExecutionState.FAILED, message="Broker not available",
                )

            broker_result, attempts, _ = await retry_with_backoff(
                "modify_order", adapter.modify_order, order_id, changes
            )
            if attempts:
                execution_observability.record_retry()

            elapsed_ms = round((time.monotonic() - exec_start) * 1000, 2)

            if broker_result.success:
                self._publish_event("OrderModified", request_id, req, ExecutionState.SENT, message="Order modified")
                execution_observability.record_latency(elapsed_ms, req.broker)
            else:
                self._publish_event("OrderFailed", request_id, req, ExecutionState.FAILED, message=broker_result.message)
                execution_observability.record_broker_error(req.broker)

            await log_execution_event(
                user_id=req.user_id, broker=req.broker, action="modified",
                execution_request_id=request_id, broker_order_id=order_id,
                latency_ms=elapsed_ms, status="modified" if broker_result.success else "failed",
                message=broker_result.message, payload={"changes": changes},
                result={"success": broker_result.success},
            )

            return ExecutionResult(
                success=broker_result.success, execution_request_id=request_id,
                broker_order_id=order_id, message=broker_result.message,
                latency_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = round((time.monotonic() - exec_start) * 1000, 2)
            execution_observability.record_broker_error(req.broker)
            self._publish_event("OrderFailed", request_id, req, ExecutionState.FAILED, message=str(e))
            return ExecutionResult(
                success=False, execution_request_id=request_id,
                state=ExecutionState.FAILED, message=str(e),
                error_code="MODIFY_FAILED", latency_ms=elapsed_ms,
            )

    async def cancel_order(self, req: ExecutionRequest, order_id: str) -> ExecutionResult:
        exec_start = time.monotonic()
        request_id = _generate_execution_request_id(req.user_id, req.broker, f"cancel:{order_id}", "", time.time())

        try:
            adapter = await self._get_adapter(req.user_id, req.broker)
            if not adapter:
                return ExecutionResult(
                    success=False, execution_request_id=request_id,
                    state=ExecutionState.FAILED, message="Broker not available",
                )

            broker_result, attempts, _ = await retry_with_backoff(
                "cancel_order", adapter.cancel_order, order_id
            )
            if attempts:
                execution_observability.record_retry()

            elapsed_ms = round((time.monotonic() - exec_start) * 1000, 2)

            if broker_result.success:
                self._publish_event("OrderCancelled", request_id, req, ExecutionState.CANCELLED, message="Order cancelled")
            else:
                self._publish_event("OrderFailed", request_id, req, ExecutionState.FAILED, message=broker_result.message)
                execution_observability.record_broker_error(req.broker)

            await log_execution_event(
                user_id=req.user_id, broker=req.broker, action="cancelled",
                execution_request_id=request_id, broker_order_id=order_id,
                latency_ms=elapsed_ms, status="cancelled" if broker_result.success else "failed",
                message=broker_result.message,
            )

            return ExecutionResult(
                success=broker_result.success, execution_request_id=request_id,
                broker_order_id=order_id, message=broker_result.message,
                latency_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = round((time.monotonic() - exec_start) * 1000, 2)
            return ExecutionResult(
                success=False, execution_request_id=request_id,
                state=ExecutionState.FAILED, message=str(e),
                error_code="CANCEL_FAILED", latency_ms=elapsed_ms,
            )

    async def square_off(self, user_id: str, broker: str, symbol: str) -> ExecutionResult:
        adapter = await self._get_adapter(user_id, broker)
        if not adapter:
            return ExecutionResult(success=False, message="Broker not available", state=ExecutionState.FAILED)

        positions = await adapter.get_positions()
        target_position = None
        for p in positions:
            if p.symbol == symbol and p.quantity != 0:
                target_position = p
                break

        if not target_position:
            return ExecutionResult(success=False, message=f"No open position for {symbol}", state=ExecutionState.REJECTED)

        side = "SELL" if target_position.quantity > 0 else "BUY"
        qty = abs(target_position.quantity)

        req = ExecutionRequest(
            user_id=user_id, broker=broker, symbol=symbol,
            exchange=target_position.exchange.value if hasattr(target_position.exchange, "value") else "NSE",
            side=side, order_type="MARKET", product="INTRADAY",
            quantity=qty, source="square_off",
        )
        return await self.place_order(req)

    async def exit_all(self, user_id: str, broker: str) -> list[ExecutionResult]:
        adapter = await self._get_adapter(user_id, broker)
        if not adapter:
            return [ExecutionResult(success=False, message="Broker not available", state=ExecutionState.FAILED)]

        positions = await adapter.get_positions()
        results = []
        for p in positions:
            if p.quantity == 0:
                continue
            side = "SELL" if p.quantity > 0 else "BUY"
            qty = abs(p.quantity)
            req = ExecutionRequest(
                user_id=user_id, broker=broker, symbol=p.symbol,
                exchange=p.exchange.value if hasattr(p.exchange, "value") else "NSE",
                side=side, order_type="MARKET", product="INTRADAY",
                quantity=qty, source="exit_all",
            )
            result = await self.place_order(req)
            results.append(result)

        return results

    async def get_order_status(self, user_id: str, broker: str, order_id: str) -> NormalizedOrder | None:
        adapter = await self._get_adapter(user_id, broker)
        if not adapter:
            return None
        return await adapter.get_order(order_id)

    async def sync_positions(self, user_id: str, broker: str) -> list:
        adapter = await self._get_adapter(user_id, broker)
        if not adapter:
            return []
        positions = await adapter.get_positions()
        try:
            supabase = get_supabase()
            for p in positions:
                data = {
                    "user_id": user_id,
                    "broker": broker,
                    "symbol": p.symbol,
                    "exchange": p.exchange.value if hasattr(p.exchange, "value") else "NSE",
                    "quantity": p.quantity,
                    "buy_quantity": p.buy_quantity,
                    "sell_quantity": p.sell_quantity,
                    "average_buy_price": p.average_buy_price,
                    "average_sell_price": p.average_sell_price,
                    "unrealised_pnl": p.unrealised_pnl,
                    "realised_pnl": p.realised_pnl,
                    "m2m": p.m2m,
                    "product": p.product.value if hasattr(p.product, "value") else "INTRADAY",
                    "updated_at": datetime.now(UTC).isoformat(),
                }
                await async_supabase(lambda: supabase.table("positions_snapshot").upsert(
                    data, on_conflict=["user_id", "broker", "symbol"]
                ).execute())
            self._publish_event("PositionUpdated", "", _empty_req(user_id, broker), ExecutionState.FILLED, message=f"Synced {len(positions)} positions")
        except Exception as e:
            logger.error("Failed to sync positions: %s", e)
        return positions

    async def get_orders(self, user_id: str, broker: str) -> list[NormalizedOrder]:
        adapter = await self._get_adapter(user_id, broker)
        if not adapter:
            return []
        return await adapter.get_orders()

    async def _get_adapter(self, user_id: str, broker: str) -> BrokerExecutionAdapter | None:
        if broker == "paper":
            from paper.paper_broker import PaperBroker
            key = f"{user_id}:paper"
            if key in self._adapters:
                adapter = self._adapters[key]
                health = await adapter.health()
                if health.get("authenticated"):
                    return adapter
            adapter = PaperBroker(user_id)
            connected = await adapter.connect()
            if connected:
                self._adapters[key] = adapter
                return adapter
            return None

        key = f"{user_id}:{broker}"
        if key in self._adapters:
            adapter = self._adapters[key]
            health = await adapter.health()
            if health.get("authenticated"):
                return adapter

        adapter = BrokerExecutionAdapter(user_id, broker)
        connected = await adapter.connect()
        if connected:
            self._adapters[key] = adapter
            return adapter
        return None

    async def _execute_with_retry(self, adapter: BrokerExecutionAdapter, order: NormalizedOrder, request_id: str, req: ExecutionRequest) -> OrderResult:
        try:
            result, attempts, elapsed = await retry_with_backoff(
                "place_order", adapter.place_order, order,
            )
            if attempts > 0:
                execution_observability.record_retry()
            return result
        except Exception as e:
            logger.error("All retry attempts failed for %s: %s", request_id, e)
            return OrderResult(success=False, message=str(e))

    def _build_normalized_order(self, req: ExecutionRequest) -> NormalizedOrder | None:
        try:
            return NormalizedOrder(
                symbol=req.symbol,
                exchange=Exchange(req.exchange),
                side=OrderSide(req.side),
                order_type=OrderType(req.order_type),
                product=ProductType(req.product),
                quantity=req.quantity,
                price=req.price,
                trigger_price=req.trigger_price,
                disclosed_quantity=req.disclosed_quantity,
                validity=req.validity,
                instrument_type=InstrumentType(req.instrument_type),
                strike_price=req.strike_price,
                expiry_date=req.expiry_date,
                option_type=OptionType(req.option_type) if req.option_type else None,
                strategy_id=req.strategy_id,
                source=req.source,
                user_id=req.user_id,
                broker=req.broker,
                client_order_id=req.execution_request_id or "",
            )
        except Exception as e:
            logger.error("Failed to build order: %s", e)
            return None

    async def _check_existing_order(self, request_id: str) -> dict | None:
        try:
            supabase = get_supabase()
            return await async_safe_single(
                supabase.table("orders")
                .select("*")
                .eq("client_order_id", request_id)
            )
        except Exception:
            return None

    async def _insert_order_atomic(self, order: NormalizedOrder) -> dict | None:
        try:
            supabase = get_supabase()
            data = order.model_dump(mode="json")
            for field in ("id", "run_id", "signal_id", "validity", "disclosed_quantity"):
                if field in data and not data[field]:
                    del data[field]
            if not data.get("client_order_id"):
                data["client_order_id"] = order.client_order_id or order.broker or ""
            result = await async_supabase(
                lambda: supabase.table("orders")
                .upsert(data, on_conflict=["client_order_id"], ignore_duplicates=True)
                .execute()
            )
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error("Failed to insert order atomically: %s", e)
            return None

    async def _log_order(self, user_id: str, order: NormalizedOrder) -> None:
        try:
            supabase = get_supabase()
            data = order.model_dump(mode="json")
            for field in ("id", "run_id", "signal_id", "validity", "disclosed_quantity"):
                if field in data and not data[field]:
                    del data[field]
            await async_supabase(lambda: supabase.table("orders").insert(data).execute())
        except Exception as e:
            logger.error("Failed to log order: %s", e)

    async def _update_order_in_db(self, order: NormalizedOrder, user_id: str, broker_order_id: str) -> None:
        try:
            supabase = get_supabase()
            await async_supabase(lambda: supabase.table("orders").update({
                "broker_order_id": broker_order_id,
                "status": "FILLED",
                "filled_at": datetime.now(UTC).isoformat(),
            }).eq("user_id", user_id).eq("client_order_id", order.client_order_id).execute())
        except Exception as e:
            logger.error("Failed to update order in DB: %s", e)

    def _publish_event(self, event_type: str, request_id: str, req: ExecutionRequest, state: ExecutionState, message: str = "") -> None:
        event = ExecutionEvent(
            event_type=event_type,
            execution_request_id=request_id,
            user_id=req.user_id,
            broker=req.broker,
            symbol=req.symbol,
            side=req.side,
            state=state,
            message=message,
            payload=req.model_dump(mode="json"),
        )
        fire_and_forget(execution_event_bus.publish(event))
