"""Execution Engine facade (Execution Engine v1.0).

The single entry point for the user-facing order lifecycle: ``submit`` /
``modify`` / ``cancel`` with idempotency, risk routing and canonical domain
events. Composes the production stack (OMS → Broker SDK) via the engine gate
and is multi-account/multi-broker by construction (every call is scoped by
``user_id`` + order broker).

The gateway is injectable so the facade is unit-testable without a broker or
DB; ``None`` lazily resolves to the production ``engine.gate.execute_order``.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from core.models import NormalizedOrder, OrderResult

from execution_engine.events import (
    ExecutionEventType,
    execution_bus,
    order_event,
)

logger = logging.getLogger(__name__)

Gateway = Callable[..., Awaitable[OrderResult]]


def _default_gateway() -> Gateway:
    from engine.gate import execute_order

    return execute_order


class ExecutionEngine:
    def __init__(self, bus: Any | None = None, gateway: Gateway | None = None, order_manager: Any | None = None) -> None:
        self._bus = bus or execution_bus
        self._gateway = gateway
        self._order_manager = order_manager

    # ------------------------------------------------------------------
    async def submit(
        self,
        user_id: str,
        order: NormalizedOrder,
        *,
        source: str = "manual",
        idempotency_key: str | None = None,
    ) -> OrderResult:
        """Idempotent order submission with canonical lifecycle events."""
        try:
            order.user_id = user_id
            order.source = source
            order.client_order_id = idempotency_key or order.client_order_id
            correlation = order.client_order_id

            self._bus.publish(
                order_event(
                    ExecutionEventType.ORDER_SUBMITTED,
                    user_id=user_id,
                    broker=order.broker or "",
                    client_order_id=correlation or "",
                    correlation_id=correlation,
                    symbol=order.symbol,
                    side=order.side.value if order.side else "",
                    quantity=order.quantity,
                    price=order.price or 0.0,
                    state="NEW",
                    message=f"Submitting {order.side} {order.quantity} {order.symbol}",
                    payload={"source": source, "is_paper": order.is_paper, "strategy_id": order.strategy_id or ""},
                )
            )

            gateway = self._gateway or _default_gateway()
            result = await gateway(user_id, order, source=source, idempotency_key=idempotency_key)

            self._publish_outcome(result, order, correlation)
            return result
        except Exception as e:
            logger.error("ExecutionEngine.submit failed for user=%s: %s", user_id, e)
            self._bus.publish(
                order_event(
                    ExecutionEventType.ORDER_FAILED,
                    user_id=user_id,
                    broker=order.broker or "",
                    client_order_id=order.client_order_id or "",
                    correlation_id=order.client_order_id or "",
                    symbol=order.symbol,
                    side=order.side.value if order.side else "",
                    quantity=order.quantity,
                    message=f"Submission failed: {e}",
                )
            )
            return OrderResult(success=False, order=order, message=str(e), status="error")

    def _publish_outcome(self, result: OrderResult, order: NormalizedOrder, correlation: str | None) -> None:
        status = (result.status or "error").lower()
        broker = order.broker or ""
        base = {
            "user_id": order.user_id,
            "broker": broker,
            "client_order_id": correlation or order.client_order_id or "",
            "correlation_id": correlation or order.client_order_id or "",
            "symbol": order.symbol,
            "side": order.side.value if order.side else "",
            "quantity": order.quantity,
            "broker_order_id": result.broker_order_id or "",
            "message": result.message or "",
            "payload": {
                "filled_qty": getattr(result, "filled_qty", 0) or 0,
                "avg_price": getattr(result, "avg_price", 0.0) or 0.0,
                "source": "execution_engine",
            },
        }

        if status == "filled":
            base["filled_quantity"] = getattr(result, "filled_qty", 0) or 0
            base["avg_price"] = getattr(result, "avg_price", 0.0) or 0.0
            base["state"] = "FILLED"
            self._bus.publish(order_event(ExecutionEventType.ORDER_FILLED, **base))
        elif status == "partially_filled" or status in ("partial", "partially filled"):
            base["filled_quantity"] = getattr(result, "filled_qty", 0) or 0
            base["avg_price"] = getattr(result, "avg_price", 0.0) or 0.0
            base["state"] = "PARTIALLY_FILLED"
            self._bus.publish(order_event(ExecutionEventType.ORDER_PARTIALLY_FILLED, **base))
        elif status == "pending":
            base["state"] = "PENDING"
            self._bus.publish(order_event(ExecutionEventType.ORDER_PENDING, **base))
        elif status == "rejected":
            base["state"] = "REJECTED"
            self._bus.publish(order_event(ExecutionEventType.ORDER_REJECTED, **base))
        elif status == "duplicate":
            return
        elif status == "error":
            base["state"] = "FAILED"
            self._bus.publish(order_event(ExecutionEventType.ORDER_FAILED, **base))
        else:
            base["state"] = status.upper()
            self._bus.publish(order_event(ExecutionEventType.ORDER_PENDING, **base))

        self._bus.publish(
            order_event(
                ExecutionEventType.EXECUTION_RESULT,
                user_id=base["user_id"],
                broker=broker,
                client_order_id=base["client_order_id"],
                correlation_id=base["correlation_id"],
                symbol=order.symbol,
                quantity=base["quantity"],
                state=base["state"],
                message=result.message or "",
                payload={
                    "broker_order_id": result.broker_order_id or "",
                    "filled_qty": base.get("filled_quantity", 0),
                    "avg_price": base.get("avg_price", 0.0),
                    "status": status,
                },
            )
        )

    # ------------------------------------------------------------------
    async def get_order_manager(self):
        if self._order_manager is None:
            from oms.manager import order_manager

            self._order_manager = order_manager
        return self._order_manager

    async def cancel(self, user_id: str, oms_order_id: str) -> dict[str, Any]:
        """Cancel an OMS order by its ``oms_order_id``; emits ``order.cancelled``."""
        om = await self.get_order_manager()
        try:
            order = await om.cancel_order(oms_order_id)
        except Exception as e:
            logger.error("ExecutionEngine.cancel failed for user=%s order=%s: %s", user_id, oms_order_id, e)
            return {"success": False, "message": str(e)}
        if order is None:
            return {"success": False, "message": "Order not found or not cancellable"}
        self._bus.publish(
            order_event(
                ExecutionEventType.ORDER_CANCELLED,
                user_id=order.user_id,
                broker=order.broker,
                order_id=order.oms_order_id,
                client_order_id=order.client_order_id,
                broker_order_id=order.broker_order_id,
                correlation_id=order.client_order_id or order.oms_order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                state=order.state.value,
                message=order.message or "",
            )
        )
        return {"success": True, "oms_order_id": order.oms_order_id, "broker_order_id": order.broker_order_id, "state": order.state.value}

    async def modify(self, user_id: str, oms_order_id: str, changes: dict) -> dict[str, Any]:
        """Modify an OMS order; publishes ``order.modified``."""
        om = await self.get_order_manager()
        try:
            order = await om.modify_order(oms_order_id, changes)
        except Exception as e:
            logger.error("ExecutionEngine.modify failed for user=%s order=%s: %s", user_id, oms_order_id, e)
            return {"success": False, "message": str(e)}
        if order is None:
            return {"success": False, "message": "Order not found or cannot modify"}
        self._bus.publish(
            order_event(
                ExecutionEventType.ORDER_MODIFIED,
                user_id=order.user_id,
                broker=order.broker,
                order_id=order.oms_order_id,
                client_order_id=order.client_order_id,
                broker_order_id=order.broker_order_id,
                correlation_id=order.client_order_id or order.oms_order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                price=order.price or 0.0,
                state=order.state.value,
                message=order.message or "",
                payload={"changes": changes},
            )
        )
        return {"success": True, "oms_order_id": order.oms_order_id, "state": order.state.value}

    # ------------------------------------------------------------------
    def publish_order_event(self, event_type: ExecutionEventType, **kwargs) -> None:
        """Helper for callers that already hold a terminal OmniOrder."""
        self._bus.publish(order_event(event_type, **kwargs))


execution_engine = ExecutionEngine()