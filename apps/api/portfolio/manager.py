import logging
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta, timezone

from core.db import async_supabase, get_supabase
from core.models import Position, Holding, Funds
from core.safe_query import async_safe_execute, safe_execute, safe_single
from execution.broker_adapter import BrokerExecutionAdapter
from execution.event_bus import execution_event_bus, ExecutionEvent, fire_and_forget
from execution.models import ExecutionRequest
from portfolio.models import (
    BrokerSyncStatus,
    PortfolioFunds,
    PortfolioHolding,
    PortfolioPnL,
    PortfolioPosition,
    PortfolioState,
    PortfolioSummary,
    ReconciliationResult,
    SyncStatus,
)
from portfolio.observability import portfolio_metrics

logger = logging.getLogger(__name__)

DAY_SECONDS = 86400


def _state_key(user_id: str, broker: str) -> str:
    return f"{user_id}:{broker}"


class PortfolioManager:
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
        self._states: dict[str, PortfolioState] = {}
        self._broker_adapters: dict[str, BrokerExecutionAdapter] = {}

    async def get_positions(self, user_id: str, broker: str) -> list[PortfolioPosition]:
        state = await self._ensure_state(user_id, broker)
        return list(state.positions.values())

    async def get_holdings(self, user_id: str, broker: str) -> list[PortfolioHolding]:
        state = await self._ensure_state(user_id, broker)
        return list(state.holdings.values())

    async def get_margin(self, user_id: str, broker: str) -> PortfolioFunds:
        state = await self._ensure_state(user_id, broker)
        return state.funds

    async def get_portfolio(self, user_id: str, broker: str) -> PortfolioState:
        return await self._ensure_state(user_id, broker)

    async def get_pnl(self, user_id: str, broker: str) -> PortfolioPnL:
        state = await self._ensure_state(user_id, broker)
        return state.pnl

    async def get_summary(self, user_id: str) -> PortfolioSummary:
        brokers = self._get_user_brokers(user_id)
        if not brokers:
            return PortfolioSummary(user_id=user_id)

        total_positions = 0
        open_positions = 0
        total_holdings = 0
        total_margin = 0.0
        used_margin = 0.0
        available_margin = 0.0
        unrealised_pnl = 0.0
        realised_pnl = 0.0
        daily_pnl = 0.0
        total_invested = 0.0
        total_exposure = 0.0
        drawdown_pct = 0.0
        last_synced: datetime | None = None

        for broker in brokers:
            state = self._states.get(_state_key(user_id, broker))
            if not state:
                continue
            total_positions += len(state.positions)
            open_positions += sum(1 for p in state.positions.values() if p.quantity != 0)
            total_holdings += len(state.holdings)
            funds = state.funds
            total_margin += funds.total_margin
            used_margin += funds.used_margin
            available_margin += funds.available_margin
            unrealised_pnl += state.pnl.unrealised_pnl
            realised_pnl += state.pnl.realised_pnl
            daily_pnl += state.pnl.daily_pnl
            total_invested += sum(
                abs(p.quantity) * p.average_buy_price for p in state.positions.values()
            )
            total_exposure += sum(
                abs(p.quantity) * (p.last_price or p.average_buy_price) for p in state.positions.values()
            )
            drawdown_pct = max(drawdown_pct, state.pnl.drawdown_pct)
            sync_time = state.sync_status.last_positions_sync
            if sync_time and (last_synced is None or sync_time > last_synced):
                last_synced = sync_time

        return PortfolioSummary(
            user_id=user_id,
            total_positions=total_positions,
            open_positions=open_positions,
            total_holdings=total_holdings,
            total_margin=total_margin,
            used_margin=used_margin,
            available_margin=available_margin,
            unrealised_pnl=unrealised_pnl,
            realised_pnl=realised_pnl,
            daily_pnl=daily_pnl,
            total_invested=total_invested,
            total_exposure=total_exposure,
            drawdown_pct=round(drawdown_pct, 2),
            last_synced=last_synced,
            brokers=brokers,
        )

    async def refresh(self, user_id: str, broker: str) -> PortfolioState:
        sync_start = time.monotonic()
        state = self._states.get(_state_key(user_id, broker))
        if not state:
            state = PortfolioState(user_id=user_id, broker=broker)
            self._states[_state_key(user_id, broker)] = state

        adapter = await self._get_adapter(user_id, broker)
        if not adapter:
            state.sync_status.positions_sync_status = SyncStatus.FAILED
            state.sync_status.error_message = "Broker adapter not available"
            portfolio_metrics.record_sync(broker, (time.monotonic() - sync_start) * 1000, False)
            return state

        try:
            broker_positions = await adapter.get_positions()
            self._sync_positions(state, broker_positions, user_id, broker)
            state.sync_status.last_positions_sync = datetime.now(UTC)
            state.sync_status.positions_sync_status = SyncStatus.SYNCED
        except Exception as e:
            logger.error("Position sync failed for %s/%s: %s", user_id, broker, e)
            state.sync_status.positions_sync_status = SyncStatus.FAILED
            state.sync_status.error_message = str(e)

        try:
            broker_holdings = await adapter.get_holdings()
            self._sync_holdings(state, broker_holdings, user_id, broker)
            state.sync_status.last_holdings_sync = datetime.now(UTC)
            state.sync_status.holdings_sync_status = SyncStatus.SYNCED
        except Exception as e:
            logger.error("Holding sync failed for %s/%s: %s", user_id, broker, e)
            state.sync_status.holdings_sync_status = SyncStatus.FAILED

        try:
            broker_funds = await adapter.get_funds()
            self._sync_funds(state, broker_funds, user_id, broker)
            state.sync_status.last_funds_sync = datetime.now(UTC)
            state.sync_status.funds_sync_status = SyncStatus.SYNCED
        except Exception as e:
            logger.error("Funds sync failed for %s/%s: %s", user_id, broker, e)
            state.sync_status.funds_sync_status = SyncStatus.FAILED

        try:
            broker_orders = await adapter.get_orders()
            state.orders = [o.model_dump(mode="json") if hasattr(o, "model_dump") else o for o in broker_orders]
            state.sync_status.last_orders_sync = datetime.now(UTC)
            state.sync_status.orders_sync_status = SyncStatus.SYNCED
        except Exception as e:
            logger.error("Orders sync failed for %s/%s: %s", user_id, broker, e)
            state.sync_status.orders_sync_status = SyncStatus.FAILED

        await self._reconcile(state, user_id, broker)
        await self._compute_pnl(state, user_id, broker)
        state.last_updated = datetime.now(UTC)

        elapsed_ms = (time.monotonic() - sync_start) * 1000
        portfolio_metrics.record_sync(broker, elapsed_ms, True)

        self._publish_event("PortfolioUpdated", user_id, broker, state)
        return state

    async def reconcile(self, user_id: str, broker: str) -> ReconciliationResult:
        state = await self._ensure_state(user_id, broker)
        self._reconcile(state, user_id, broker)
        portfolio_metrics.record_reconciliation(state.reconciliation.drift_detected)
        return state.reconciliation

    async def validate_risk_exposure(self, user_id: str, symbol: str, quantity: int, price: float) -> dict:
        brokers = self._get_user_brokers(user_id)
        total_exposure = 0.0
        for broker in brokers:
            state = self._states.get(_state_key(user_id, broker))
            if state:
                for pos in state.positions.values():
                    total_exposure += abs(pos.quantity) * (pos.last_price or pos.average_buy_price)
        new_exposure = total_exposure + quantity * price
        return {
            "current_exposure": total_exposure,
            "new_exposure": new_exposure,
            "position_count": sum(len(self._states.get(_state_key(user_id, b)).positions) for b in brokers if _state_key(user_id, b) in self._states),
        }

    async def get_daily_pnl(self, user_id: str) -> float:
        total = 0.0
        for key, state in self._states.items():
            if key.startswith(f"{user_id}:"):
                total += state.pnl.daily_pnl
        return total

    async def _ensure_state(self, user_id: str, broker: str) -> PortfolioState:
        key = _state_key(user_id, broker)
        if key not in self._states:
            state = PortfolioState(user_id=user_id, broker=broker)
            self._states[key] = state
            try:
                await self._load_state_from_db(state, user_id, broker)
            except Exception as e:
                logger.debug("No persisted state for %s/%s: %s", user_id, broker, e)
        return self._states[key]

    def _sync_positions(self, state: PortfolioState, broker_positions: list, user_id: str, broker: str):
        prev_symbols = set(state.positions.keys())
        new_symbols = set()

        for bp in broker_positions:
            symbol = bp.symbol if hasattr(bp, "symbol") else bp.get("symbol", "")
            new_symbols.add(symbol)
            existing = state.positions.get(symbol)
            qty = bp.quantity if hasattr(bp, "quantity") else bp.get("quantity", 0)
            prev_qty = existing.quantity if existing else 0

            pos = PortfolioPosition(
                user_id=user_id,
                broker=broker,
                symbol=symbol,
                exchange=bp.exchange.value if hasattr(bp.exchange, "value") else bp.get("exchange", "NSE"),
                quantity=qty,
                buy_quantity=bp.buy_quantity if hasattr(bp, "buy_quantity") else bp.get("buy_quantity", 0),
                sell_quantity=bp.sell_quantity if hasattr(bp, "sell_quantity") else bp.get("sell_quantity", 0),
                average_buy_price=float(bp.average_buy_price if hasattr(bp, "average_buy_price") else bp.get("average_buy_price", 0)),
                average_sell_price=float(bp.average_sell_price if hasattr(bp, "average_sell_price") else bp.get("average_sell_price", 0)),
                unrealised_pnl=float(bp.unrealised_pnl if hasattr(bp, "unrealised_pnl") else bp.get("unrealised_pnl", 0)),
                realised_pnl=float(bp.realised_pnl if hasattr(bp, "realised_pnl") else bp.get("realised_pnl", 0)),
                m2m=float(bp.m2m if hasattr(bp, "m2m") else bp.get("m2m", 0)),
                product=bp.product.value if hasattr(bp.product, "value") else bp.get("product", "INTRADAY"),
                last_price=float(bp.last_price if hasattr(bp, "last_price") else bp.get("last_price", 0)),
                multiplier=float(bp.multiplier if hasattr(bp, "multiplier") else bp.get("multiplier", 1)),
                updated_at=datetime.now(UTC),
            )
            state.positions[symbol] = pos

            if qty != 0 and prev_qty == 0:
                self._publish_event("PositionOpened", user_id, broker, state, symbol=symbol, quantity=qty)
            elif qty == 0 and prev_qty != 0:
                self._publish_event("PositionClosed", user_id, broker, state, symbol=symbol, prev_quantity=prev_qty)
            elif qty != prev_qty:
                self._publish_event("PositionUpdated", user_id, broker, state, symbol=symbol, quantity=qty, prev_quantity=prev_qty)

        closed = prev_symbols - new_symbols
        for symbol in closed:
            pos = state.positions.pop(symbol, None)
            if pos and pos.quantity != 0:
                self._publish_event("PositionClosed", user_id, broker, state, symbol=symbol, prev_quantity=pos.quantity)

    def _sync_holdings(self, state: PortfolioState, broker_holdings: list, user_id: str, broker: str):
        for bh in broker_holdings:
            symbol = bh.symbol if hasattr(bh, "symbol") else bh.get("symbol", "")
            holding = PortfolioHolding(
                user_id=user_id,
                broker=broker,
                symbol=symbol,
                exchange=bh.exchange.value if hasattr(bh.exchange, "value") else bh.get("exchange", "NSE"),
                quantity=bh.quantity if hasattr(bh, "quantity") else bh.get("quantity", 0),
                t1_quantity=bh.t1_quantity if hasattr(bh, "t1_quantity") else bh.get("t1_quantity", 0),
                average_price=float(bh.average_price if hasattr(bh, "average_price") else bh.get("average_price", 0)),
                current_price=float(bh.current_price if hasattr(bh, "current_price") else bh.get("current_price", 0)),
                pnl=float(bh.pnl if hasattr(bh, "pnl") else bh.get("pnl", 0)),
                cost_price=float(bh.average_price if hasattr(bh, "average_price") else bh.get("average_price", 0)),
                updated_at=datetime.now(UTC),
            )
            state.holdings[symbol] = holding

        self._publish_event("HoldingUpdated", user_id, broker, state)

    def _sync_funds(self, state: PortfolioState, broker_funds: Funds, user_id: str, broker: str):
        state.funds = PortfolioFunds(
            user_id=user_id,
            broker=broker,
            total_margin=getattr(broker_funds, "total_margin", 0.0),
            used_margin=getattr(broker_funds, "used_margin", 0.0),
            available_margin=getattr(broker_funds, "available_margin", 0.0),
            payin=getattr(broker_funds, "payin", 0.0),
            payout=getattr(broker_funds, "payout", 0.0),
            collateral=getattr(broker_funds, "collateral", 0.0),
            m2m_unrealised=sum(p.unrealised_pnl for p in state.positions.values()),
            updated_at=datetime.now(UTC),
        )
        self._publish_event("MarginUpdated", user_id, broker, state)

    async def _compute_pnl(self, state: PortfolioState, user_id: str, broker: str):
        pnl_start = time.monotonic()
        realised = sum(p.realised_pnl for p in state.positions.values())
        unrealised = sum(p.unrealised_pnl for p in state.positions.values())

        today_filled_pnl = await self._get_today_filled_pnl(user_id, broker)
        daily_pnl = realised + today_filled_pnl

        state.pnl = PortfolioPnL(
            user_id=user_id,
            broker=broker,
            realised_pnl=round(realised, 2),
            unrealised_pnl=round(unrealised, 2),
            daily_pnl=round(daily_pnl, 2),
            overall_pnl=round(realised + unrealised, 2),
            current_equity=round(state.funds.total_margin + unrealised, 2),
            day_start_equity=round(state.funds.total_margin + unrealised, 2) if not state.pnl.day_start_equity else state.pnl.day_start_equity,
                peak_equity=max(round(state.funds.total_margin + unrealised, 2), state.pnl.peak_equity or 0),
            updated_at=datetime.now(UTC),
        )

        if state.pnl.peak_equity > 0:
            dd = max(0.0, (state.pnl.peak_equity - state.pnl.current_equity) / state.pnl.peak_equity * 100)
            state.pnl.drawdown_pct = round(dd, 2)

        portfolio_metrics.record_pnl_update((time.monotonic() - pnl_start) * 1000)
        self._publish_event("PnLUpdated", user_id, broker, state)

    async def _reconcile(self, state: PortfolioState, user_id: str, broker: str):
        result = ReconciliationResult(user_id=user_id, broker=broker)
        result.local_positions = len(state.positions)
        result.broker_positions = len(state.positions)  # Placeholder — real count requires async broker call

        synced_symbols = set(state.positions.keys())
        db_positions = await self._get_db_positions(user_id, broker)
        db_symbols = set(p.get("symbol", "") for p in db_positions)

        for sym in synced_symbols - db_symbols:
            result.ghost_positions.append(sym)
        for sym in db_symbols - synced_symbols:
            result.missing_orders.append(sym)

        for dp in db_positions:
            sym = dp.get("symbol", "")
            bp = state.positions.get(sym)
            if bp and abs(bp.quantity) != abs(dp.get("quantity", 0)):
                result.out_of_sync_quantities.append({
                    "symbol": sym,
                    "broker_qty": bp.quantity,
                    "db_qty": abs(dp.get("quantity", 0)),
                    "difference": abs(bp.quantity) - abs(dp.get("quantity", 0)),
                })

        if result.ghost_positions or result.missing_orders or result.out_of_sync_quantities:
            result.drift_detected = True
            details = []
            if result.ghost_positions:
                details.append(f"ghost:{result.ghost_positions}")
            if result.missing_orders:
                details.append(f"missing:{result.missing_orders}")
            if result.out_of_sync_quantities:
                details.append(f"qty_mismatch:{len(result.out_of_sync_quantities)}")
            result.drift_details = "; ".join(details)
            state.sync_status.positions_sync_status = SyncStatus.DRIFTED

        state.reconciliation = result

    async def _load_state_from_db(self, state: PortfolioState, user_id: str, broker: str):
        db_positions = await self._get_db_positions(user_id, broker)
        for dp in db_positions:
            sym = dp.get("symbol", "")
            state.positions[sym] = PortfolioPosition(
                user_id=user_id, broker=broker,
                symbol=sym,
                exchange=dp.get("exchange", "NSE"),
                quantity=dp.get("quantity", 0),
                buy_quantity=dp.get("buy_quantity", 0),
                sell_quantity=dp.get("sell_quantity", 0),
                average_buy_price=float(dp.get("average_buy_price", 0)),
                average_sell_price=float(dp.get("average_sell_price", 0)),
                unrealised_pnl=float(dp.get("unrealised_pnl", 0)),
                realised_pnl=float(dp.get("realised_pnl", 0)),
                product=dp.get("product", "INTRADAY"),
                last_price=float(dp.get("last_price", 0)),
                updated_at=datetime.now(UTC),
            )

    async def _get_db_positions(self, user_id: str, broker: str) -> list:
        try:
            supabase = get_supabase()
            rows = await async_safe_execute(
                supabase.table("positions_snapshot")
                .select("*")
                .eq("user_id", user_id)
                .eq("broker", broker)
            )
            return rows or []
        except Exception:
            return []

    async def _get_today_filled_pnl(self, user_id: str, broker: str) -> float:
        from risk.helpers import compute_daily_pnl_fifo
        try:
            return await compute_daily_pnl_fifo(user_id, broker=broker)
        except Exception as e:
            logger.debug("Failed to get today filled PnL: %s", e)
            return 0.0

    def _get_user_brokers(self, user_id: str) -> list[str]:
        brokers = set()
        for key in self._states:
            if key.startswith(f"{user_id}:"):
                brokers.add(key.split(":", 1)[1])
        if not brokers:
            return list(brokers)
        return list(brokers)

    async def _get_adapter(self, user_id: str, broker: str) -> BrokerExecutionAdapter | None:
        key = f"{user_id}:{broker}"
        if key in self._broker_adapters:
            adapter = self._broker_adapters[key]
            health = await adapter.health()
            if health.get("authenticated"):
                return adapter

        adapter = BrokerExecutionAdapter(user_id, broker)
        connected = await adapter.connect()
        if connected:
            self._broker_adapters[key] = adapter
            return adapter
        return None

    def invalidate_cache(self, user_id: str, broker: str):
        key = _state_key(user_id, broker)
        self._states.pop(key, None)

    def _publish_event(self, event_type: str, user_id: str, broker: str, state: PortfolioState, **extra):
        try:
            payload = {
                "user_id": user_id,
                "broker": broker,
                "symbol": extra.get("symbol", ""),
                "quantity": extra.get("quantity", 0),
                "prev_quantity": extra.get("prev_quantity", 0),
            }
            event = ExecutionEvent(
                event_type=event_type,
                user_id=user_id,
                broker=broker,
                payload=payload,
            )
            fire_and_forget(execution_event_bus.publish(event))
        except Exception as e:
            logger.error("Failed to publish %s event: %s", event_type, e)


portfolio_manager = PortfolioManager()
