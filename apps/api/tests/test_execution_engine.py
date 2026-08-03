"""Tests for the Execution Engine v1.0 package (execution_engine/).

Covers the canonical domain bus, state machine, FIFO lot engine, trade ledger,
position manager, P&L engine, portfolio engine, facade and metrics wiring.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models import NormalizedOrder, OrderResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clean_engine():
    """Reset engine singletons and bus subscriptions between tests."""
    from execution_engine.events import ExecutionDomain, LoggingSink, execution_bus
    from execution_engine.init import reset_execution_engine

    from execution_engine import (
        pnl_engine,
        portfolio_engine,
        position_manager,
        trade_manager,
    )
    from execution_engine.metrics import execution_metrics

    reset_execution_engine()
    execution_bus.reset_subscribers()
    execution_bus.subscribe(ExecutionDomain.ORDER, LoggingSink())
    execution_bus.clear()
    trade_manager.ledger.clear()
    for mgr in (position_manager, pnl_engine, portfolio_engine):
        mgr.clear()
    for mgr in (trade_manager, position_manager, pnl_engine, portfolio_engine, execution_metrics):
        mgr._installed = False
    yield
    execution_bus.clear()


def make_order(symbol="NIFTY", side="BUY", quantity=65, price=71.75, broker="paper") -> NormalizedOrder:
    from core.models import Exchange, OrderSide, OrderType, ProductType

    return NormalizedOrder(
        user_id="u1",
        broker=broker,
        symbol=symbol,
        exchange=Exchange.NSE,
        side=OrderSide(side),
        order_type=OrderType.MARKET,
        product=ProductType.INTRADAY,
        quantity=quantity,
        price=price,
        is_paper=True,
    )


def fill_event(coid, side, qty, price, broker="paper", symbol="NIFTY", **payload):
    from execution_engine.events import ExecutionEventType, order_event

    p = {"strategy_id": "s1", "source": "engine", "is_paper": True, "commission": 1.0}
    p.update(payload)
    return order_event(
        ExecutionEventType.ORDER_FILLED,
        user_id="u1",
        broker=broker,
        order_id=f"oms-{coid}",
        client_order_id=coid,
        correlation_id=coid,
        symbol=symbol,
        side=side,
        quantity=qty,
        avg_price=price,
        filled_quantity=qty,
        payload=p,
    )


# ---------------------------------------------------------------------------
# Canonical state machine
# ---------------------------------------------------------------------------
class TestStateMachine:
    def test_normalize_canonical_and_alias(self):
        from execution_engine.state_machine import OrderState, normalize

        assert normalize("PARTIAL") is OrderState.PARTIALLY_FILLED
        assert normalize("partially_filled") is OrderState.PARTIALLY_FILLED
        assert normalize("FILLED") is OrderState.FILLED
        assert normalize(OrderState.PARTIAL) is OrderState.PARTIALLY_FILLED
        assert normalize("BOGUS") is None
        assert normalize(None) is None

    def test_valid_transitions(self):
        from execution_engine.state_machine import OrderState, state_machine

        assert state_machine.can_transition(OrderState.NEW, OrderState.QUEUED)
        assert state_machine.can_transition(OrderState.PENDING, OrderState.FILLED)
        assert state_machine.can_transition(OrderState.PENDING, OrderState.REJECTED)
        assert not state_machine.can_transition(OrderState.FILLED, OrderState.PENDING)
        assert not state_machine.can_transition(OrderState.NEW, OrderState.FILLED)

    def test_transition_rejects_illegal(self):
        from execution_engine.state_machine import OrderState, state_machine

        assert state_machine.transition(OrderState.NEW, OrderState.FILLED) is OrderState.NEW

    def test_terminal_and_active(self):
        from execution_engine.state_machine import state_machine

        assert state_machine.is_terminal("FILLED")
        assert not state_machine.is_terminal("PARTIAL")
        assert not state_machine.is_terminal("PENDING")


# ---------------------------------------------------------------------------
# FIFO lot engine
# ---------------------------------------------------------------------------
class TestFifoLots:
    def test_buy_sell_realizes_positive_pnl(self):
        from execution_engine.fifo import FifoLots

        lots = FifoLots()
        assert lots.apply("BUY", 65, 71.75) == 0.0
        assert lots.apply("SELL", 40, 73.0) == 50.0
        assert lots.net_quantity == 25
        assert lots.average_price("BUY") == 71.75

    def test_short_sell_and_buy_back(self):
        from execution_engine.fifo import FifoLots

        lots = FifoLots()
        assert lots.apply("SELL", 40, 73.0) == 0.0
        assert lots.apply("BUY", 25, 71.0) == 50.0  # (73 - 71) * 25
        assert lots.short_quantity == 15

    def test_fifo_ordering(self):
        from execution_engine.fifo import FifoLots

        lots = FifoLots()
        lots.apply("BUY", 65, 71.75)
        lots.apply("BUY", 35, 70.25)
        # FIFO: first 40 shares close against the 71.75 lot
        assert lots.apply("SELL", 40, 73.0) == 50.0
        remaining = lots.snapshot()
        assert remaining["net_quantity"] == 60
        assert round(remaining["average_buy_price"], 2) == 70.88  # (25*71.75 + 35*70.25) / 60

    def test_full_round_trip_pnl(self):
        from execution_engine.fifo import FifoLots

        lots = FifoLots()
        lots.apply("BUY", 65, 71.75)
        lots.apply("BUY", 35, 70.25)
        lots.apply("SELL", 40, 73.0)
        assert lots.apply("SELL", 60, 74.5) == 217.5  # 25*2.75 + 35*4.25
        assert lots.net_quantity == 0
        assert not lots.is_open

    def test_reversal_opens_opposite_lot(self):
        from execution_engine.fifo import FifoLots

        lots = FifoLots()
        lots.apply("BUY", 10, 100.0)
        lots.apply("SELL", 15, 110.0)
        assert lots.short_quantity == 5
        assert lots.net_quantity == -5

    def test_unrealized_pnl(self):
        from execution_engine.fifo import FifoLots

        lots = FifoLots()
        lots.apply("BUY", 10, 100.0)
        assert lots.unrealized_pnl(110.0) == 100.0
        lots.apply("SELL", 10, 120.0)
        assert lots.unrealized_pnl(120.0) == 0.0

    def test_invalid_side(self):
        from execution_engine.fifo import FifoLots

        with pytest.raises(ValueError):
            FifoLots().apply("HOLD", 1, 1.0)


# ---------------------------------------------------------------------------
# Canonical domain bus
# ---------------------------------------------------------------------------
class TestExecutionEngineBus:
    def test_publish_dispatches_inline_pre_startup(self):
        from execution_engine.events import ExecutionEngineBus, ExecutionEngineEvent, ExecutionEventType

        bus = ExecutionEngineBus()
        seen = []

        def handler(event):
            seen.append(event)

        bus.subscribe(ExecutionEventType.ORDER_FILLED, handler)
        bus.publish(ExecutionEngineEvent(type=ExecutionEventType.ORDER_FILLED, user_id="u1"))
        assert len(seen) == 1
        assert bus.last_sequence == 1

    def test_sequence_and_ring_buffer(self):
        from execution_engine.events import ExecutionEngineBus, ExecutionEngineEvent, ExecutionEventType

        bus = ExecutionEngineBus(max_buffered=3)
        for _ in range(5):
            bus.publish(ExecutionEngineEvent(type=ExecutionEventType.ORDER_SUBMITTED))
        assert bus.last_sequence == 5
        assert bus.buffered == 3

    def test_subscriber_scoped_to_domain(self):
        from execution_engine.events import (
            ExecutionDomain,
            ExecutionEngineBus,
            ExecutionEngineEvent,
            ExecutionEventType,
        )

        bus = ExecutionEngineBus()
        seen = []

        def handler(event):
            seen.append(event.type)

        bus.subscribe(ExecutionDomain.ORDER, handler)
        bus.publish(ExecutionEngineEvent(type=ExecutionEventType.ORDER_SUBMITTED))
        bus.publish(ExecutionEngineEvent(type=ExecutionEventType.TRADE_EXECUTED, domain=ExecutionDomain.TRADE))
        assert seen == [ExecutionEventType.ORDER_SUBMITTED]
        bus.unsubscribe(ExecutionDomain.ORDER, handler)
        bus.publish(ExecutionEngineEvent(type=ExecutionEventType.ORDER_SUBMITTED))
        assert len(seen) == 1

    def test_started_bus_dispatches_async_handlers(self):
        from execution_engine.events import ExecutionEngineBus, ExecutionEngineEvent, ExecutionEventType

        bus = ExecutionEngineBus()
        events = []

        async def handler(event):
            await asyncio.sleep(0)
            events.append(event.type)

        async def run():
            bus.subscribe(ExecutionEventType.ORDER_FILLED, handler)
            bus.start(asyncio.get_running_loop())
            await bus.apublish(ExecutionEngineEvent(type=ExecutionEventType.ORDER_FILLED))
            await asyncio.sleep(0.05)
            await bus.stop()

        asyncio.run(run())
        assert events == [ExecutionEventType.ORDER_FILLED]

    def test_started_bus_thread_safe_publish(self):
        import threading

        from execution_engine.events import ExecutionEngineBus, ExecutionEngineEvent, ExecutionEventType

        bus = ExecutionEngineBus()
        events = []

        async def handler(event):
            events.append(event.type)

        async def run():
            bus.subscribe(ExecutionEventType.ORDER_FILLED, handler)
            bus.start(asyncio.get_running_loop())
            t = threading.Thread(target=bus.publish, args=(ExecutionEngineEvent(type=ExecutionEventType.ORDER_FILLED),))
            t.start()
            t.join()
            await asyncio.sleep(0.1)
            await bus.stop()

        asyncio.run(run())
        assert events == [ExecutionEventType.ORDER_FILLED]

    def test_recent_returns_ordered_dicts(self):
        from execution_engine.events import ExecutionEngineBus, ExecutionEngineEvent, ExecutionEventType

        bus = ExecutionEngineBus()
        bus.publish(ExecutionEngineEvent(type=ExecutionEventType.ORDER_SUBMITTED, user_id="u1"))
        bus.publish(ExecutionEngineEvent(type=ExecutionEventType.ORDER_FILLED, user_id="u1"))
        recent = bus.recent(10)
        assert [e["event"] for e in recent] == ["order.submitted", "order.filled"]
        assert recent[0]["sequence"] == 1 and recent[0]["user_id"] == "u1"


# ---------------------------------------------------------------------------
# Trade manager
# ---------------------------------------------------------------------------
class TestTradeManager:
    @pytest.mark.asyncio
    async def test_records_trade_and_publishes(self):
        from execution_engine import execution_bus, trade_manager
        from execution_engine.trades import trade_event

        trade_manager.install()
        await execution_bus.apublish(fill_event("c1", "BUY", 65, 71.75))
        assert trade_manager.count("u1") == 1
        trade = trade_manager.list_trades("u1")[0]
        assert trade.symbol == "NIFTY" and trade.quantity == 65 and trade.price == 71.75
        assert trade.commission == 1.0 and trade.charges == 1.0
        events = [e["event"] for e in execution_bus.recent(10)]
        assert "trade.executed" in events

    @pytest.mark.asyncio
    async def test_ignores_non_fill_events(self):
        from execution_engine import execution_bus, trade_manager
        from execution_engine.events import ExecutionEventType, order_event

        trade_manager.install()
        await execution_bus.apublish(order_event(ExecutionEventType.ORDER_REJECTED, user_id="u1", message="nope"))
        assert trade_manager.count("u1") == 0

    @pytest.mark.asyncio
    async def test_skips_zero_price_fill(self):
        from execution_engine import execution_bus, trade_manager

        trade_manager.install()
        await execution_bus.apublish(fill_event("c2", "BUY", 10, 0.0))
        assert trade_manager.count("u1") == 0

    @pytest.mark.asyncio
    async def test_optional_durable_store(self):
        from execution_engine import execution_bus
        from execution_engine.trades import TradeLedger, TradeManager

        store = MagicMock()
        store.save = AsyncMock()
        mgr = TradeManager(ledger=TradeLedger(), store=store)
        mgr.install()
        await execution_bus.apublish(fill_event("c3", "BUY", 1, 100.0))
        await asyncio.sleep(0.05)
        assert store.save.called

    def test_totals(self):
        from execution_engine.trades import TradeLedger, TradeRecord

        ledger = TradeLedger()
        ledger.add(TradeRecord(user_id="u1", broker="paper", symbol="NIFTY", side="BUY", quantity=65, price=71.75, charges=5.0))
        ledger.add(TradeRecord(user_id="u1", broker="paper", symbol="NIFTY", side="SELL", quantity=40, price=73.0, charges=3.0))
        totals = ledger.totals("u1")
        assert totals["paper:NIFTY"]["quantity"] == 105
        assert totals["paper:NIFTY"]["trades"] == 2
        assert totals["paper:NIFTY"]["charges"] == 8.0


# ---------------------------------------------------------------------------
# Position manager
# ---------------------------------------------------------------------------
class TestPositionManager:
    @pytest.mark.asyncio
    async def test_open_update_close_lifecycle(self):
        from execution_engine import execution_bus, position_manager, trade_manager

        trade_manager.install()
        position_manager.install()
        await execution_bus.apublish(fill_event("c1", "BUY", 65, 71.75))
        pos = position_manager.get_position("u1", "paper", "NIFTY")
        assert pos.quantity == 65 and pos.side == "LONG" and pos.is_open
        events = [e["event"] for e in execution_bus.recent(10)]
        assert "position.opened" in events

        await execution_bus.apublish(fill_event("c2", "BUY", 35, 70.25))
        pos = position_manager.get_position("u1", "paper", "NIFTY")
        assert pos.quantity == 100 and round(pos.average_price, 2) == 71.22
        assert "position.updated" in [e["event"] for e in execution_bus.recent(10)]

        await execution_bus.apublish(fill_event("c3", "SELL", 40, 73.0))
        pos = position_manager.get_position("u1", "paper", "NIFTY")
        assert pos.quantity == 60 and pos.realised_pnl == 50.0

        await execution_bus.apublish(fill_event("c4", "SELL", 60, 74.5))
        pos = position_manager.get_position("u1", "paper", "NIFTY")
        assert pos.quantity == 0 and pos.side == "FLAT" and pos.realised_pnl == 267.5
        events = [e["event"] for e in execution_bus.recent(20)]
        assert "position.closed" in events

    @pytest.mark.asyncio
    async def test_short_position(self):
        from execution_engine import execution_bus, position_manager, trade_manager

        trade_manager.install()
        position_manager.install()
        await execution_bus.apublish(fill_event("c1", "SELL", 40, 73.0))
        pos = position_manager.get_position("u1", "paper", "NIFTY")
        assert pos.side == "SHORT" and pos.quantity == -40

    @pytest.mark.asyncio
    async def test_mark_to_market(self):
        from execution_engine import execution_bus, position_manager, trade_manager

        trade_manager.install()
        position_manager.install()
        await execution_bus.apublish(fill_event("c1", "BUY", 10, 100.0))
        position_manager.mark_to_market("u1", "paper", {"NIFTY": 110.0})
        pos = position_manager.get_position("u1", "paper", "NIFTY")
        assert pos.unrealised_pnl == 100.0
        assert pos.m2m == 100.0

    @pytest.mark.asyncio
    async def test_aggregate_pnl(self):
        from execution_engine import execution_bus, position_manager, trade_manager

        trade_manager.install()
        position_manager.install()
        await execution_bus.apublish(fill_event("c1", "BUY", 10, 100.0))
        await execution_bus.apublish(fill_event("c2", "SELL", 4, 110.0))
        agg = position_manager.aggregate_pnl("u1")
        assert agg["realised_pnl"] == 40.0


# ---------------------------------------------------------------------------
# P&L engine + portfolio engine
# ---------------------------------------------------------------------------
class TestPnLAndPortfolio:
    @pytest.mark.asyncio
    async def test_full_chain(self):
        from execution_engine import (
            execution_bus,
            pnl_engine,
            portfolio_engine,
            position_manager,
            trade_manager,
        )

        pnl_engine._positions = position_manager
        portfolio_engine._positions = position_manager
        portfolio_engine._pnl = pnl_engine
        trade_manager.install()
        position_manager.install()
        pnl_engine.install()
        portfolio_engine.install()

        for f in (fill_event("c1", "BUY", 65, 71.75), fill_event("c2", "BUY", 35, 70.25),
                  fill_event("c3", "SELL", 40, 73.0), fill_event("c4", "SELL", 60, 74.5)):
            await execution_bus.apublish(f)
            await asyncio.sleep(0.05)

        acc = pnl_engine.get_account("u1", "paper")
        assert acc.realised_pnl == 267.5
        assert acc.current_equity == 500267.5
        assert acc.daily_pnl == 267.5

        snap = portfolio_engine.snapshot("u1")
        assert snap.open_positions == 0
        assert snap.realised_pnl == 267.5
        assert snap.user_id == "u1"

        events = [e["event"] for e in execution_bus.recent(50)]
        assert events.count("portfolio.revalued") == 4
        assert events.count("portfolio.snapshot") == 4

    @pytest.mark.asyncio
    async def test_snapshot_not_self_triggering(self):
        """PORTFOLIO_SNAPSHOT must never re-publish itself (regression)."""
        from execution_engine import (
            execution_bus,
            pnl_engine,
            portfolio_engine,
            position_manager,
            trade_manager,
        )

        pnl_engine._positions = position_manager
        portfolio_engine._positions = position_manager
        portfolio_engine._pnl = pnl_engine
        trade_manager.install()
        position_manager.install()
        pnl_engine.install()
        portfolio_engine.install()

        await asyncio.wait_for(execution_bus.apublish(fill_event("c1", "BUY", 1, 100.0)), timeout=2)
        await asyncio.sleep(0.05)
        events = [e["event"] for e in execution_bus.recent(20)]
        assert events.count("portfolio.snapshot") <= 1

    @pytest.mark.asyncio
    async def test_equity_peak_and_drawdown(self):
        from execution_engine import execution_bus, pnl_engine, portfolio_engine, position_manager, trade_manager

        pnl_engine._positions = position_manager
        portfolio_engine._positions = position_manager
        portfolio_engine._pnl = pnl_engine
        trade_manager.install()
        position_manager.install()
        pnl_engine.install()
        portfolio_engine.install()

        # Profit -> equity rises; then a losing trade -> drawdown
        await execution_bus.apublish(fill_event("c1", "BUY", 10, 100.0)); await asyncio.sleep(0.05)
        await execution_bus.apublish(fill_event("c2", "SELL", 10, 110.0)); await asyncio.sleep(0.05)
        await execution_bus.apublish(fill_event("c3", "BUY", 10, 200.0)); await asyncio.sleep(0.05)
        await execution_bus.apublish(fill_event("c4", "SELL", 10, 180.0)); await asyncio.sleep(0.05)

        acc = pnl_engine.get_account("u1", "paper")
        assert acc.realised_pnl == -100.0
        assert acc.peak_equity == 500100.0
        assert acc.current_equity == 499900.0
        assert round(acc.drawdown_pct, 2) > 0

        snap = portfolio_engine.snapshot("u1")
        assert snap.current_equity == 499900.0


# ---------------------------------------------------------------------------
# Facade (ExecutionEngine)
# ---------------------------------------------------------------------------
class TestExecutionEngineFacade:
    @pytest.mark.asyncio
    async def test_submit_filled_publishes_lifecycle(self):
        from execution_engine.engine import ExecutionEngine
        from execution_engine.events import ExecutionEngineBus

        bus = ExecutionEngineBus()
        gateway = AsyncMock(return_value=OrderResult(
            success=True, status="filled", broker_order_id="BROKER-1", filled_qty=65, avg_price=71.75,
            message="filled"))
        engine = ExecutionEngine(bus=bus, gateway=gateway)
        result = await engine.submit("u1", make_order(), source="engine", idempotency_key="k1")
        assert result.success and result.broker_order_id == "BROKER-1"
        events = [e["event"] for e in bus.recent(20)]
        assert events[0] == "order.submitted"
        assert "order.filled" in events
        assert "execution.result" in events
        gateway.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_submit_rejected(self):
        from execution_engine.engine import ExecutionEngine
        from execution_engine.events import ExecutionEngineBus

        bus = ExecutionEngineBus()
        engine = ExecutionEngine(bus=bus, gateway=AsyncMock(
            return_value=OrderResult(success=False, status="rejected", message="risk kill")))
        result = await engine.submit("u1", make_order())
        assert result.status == "rejected"
        assert "order.rejected" in [e["event"] for e in bus.recent(20)]

    @pytest.mark.asyncio
    async def test_submit_duplicate_is_silent(self):
        from execution_engine.engine import ExecutionEngine
        from execution_engine.events import ExecutionEngineBus

        bus = ExecutionEngineBus()
        engine = ExecutionEngine(bus=bus, gateway=AsyncMock(
            return_value=OrderResult(success=False, status="duplicate", message="dup")))
        await engine.submit("u1", make_order(), idempotency_key="k-dup")
        events = [e["event"] for e in bus.recent(20)]
        assert "order.filled" not in events
        assert "order.submitted" in events  # submit event only

    @pytest.mark.asyncio
    async def test_submit_exception_publishes_failed(self):
        from execution_engine.engine import ExecutionEngine
        from execution_engine.events import ExecutionEngineBus

        bus = ExecutionEngineBus()
        engine = ExecutionEngine(bus=bus, gateway=AsyncMock(side_effect=RuntimeError("boom")))
        result = await engine.submit("u1", make_order())
        assert result.status == "error"
        assert "order.failed" in [e["event"] for e in bus.recent(20)]

    @pytest.mark.asyncio
    async def test_cancel_and_modify_delegate_to_oms(self):
        from execution_engine.engine import ExecutionEngine
        from execution_engine.events import ExecutionEngineBus

        bus = ExecutionEngineBus()
        fake_om = MagicMock()
        fake_order = MagicMock()
        fake_order.oms_order_id = "oms-1"
        fake_order.user_id = "u1"
        fake_order.broker = "paper"
        fake_order.client_order_id = "c1"
        fake_order.broker_order_id = "b1"
        fake_order.symbol = "NIFTY"
        fake_order.side = "BUY"
        fake_order.quantity = 10
        fake_order.price = 100.0
        fake_order.message = ""
        fake_order.state.value = "CANCELLED"
        fake_om.cancel_order = AsyncMock(return_value=fake_order)
        fake_om.modify_order = AsyncMock(return_value=fake_order)

        engine = ExecutionEngine(bus=bus, order_manager=fake_om)
        cancelled = await engine.cancel("u1", "oms-1")
        assert cancelled["success"] and cancelled["state"] == "CANCELLED"
        assert "order.cancelled" in [e["event"] for e in bus.recent(20)]

        modified = await engine.modify("u1", "oms-1", {"quantity": 5})
        assert modified["success"]
        assert "order.modified" in [e["event"] for e in bus.recent(20)]

    @pytest.mark.asyncio
    async def test_cancel_not_found(self):
        from execution_engine.engine import ExecutionEngine
        from execution_engine.events import ExecutionEngineBus

        bus = ExecutionEngineBus()
        fake_om = MagicMock()
        fake_om.cancel_order = AsyncMock(return_value=None)
        engine = ExecutionEngine(bus=bus, order_manager=fake_om)
        result = await engine.cancel("u1", "nope")
        assert not result["success"]


# ---------------------------------------------------------------------------
# Metrics wiring
# ---------------------------------------------------------------------------
class TestExecutionMetrics:
    @pytest.mark.asyncio
    async def test_order_counters_update(self):
        from prometheus_client import REGISTRY

        from execution_engine import (
            execution_bus,
            pnl_engine,
            portfolio_engine,
            position_manager,
            trade_manager,
        )
        from execution_engine.metrics import execution_metrics

        pnl_engine._positions = position_manager
        portfolio_engine._positions = position_manager
        portfolio_engine._pnl = pnl_engine
        trade_manager.install()
        position_manager.install()
        pnl_engine.install()
        portfolio_engine.install()
        execution_metrics.install()

        await execution_bus.apublish(fill_event("c1", "BUY", 65, 71.75))
        await execution_bus.apublish(fill_event("c2", "SELL", 40, 73.0))
        await asyncio.sleep(0.05)

        def sample(name, labels):
            metric = REGISTRY.get_sample_value(name, labels)
            return metric if metric is not None else 0.0

        assert sample("execution_engine_trades_executed_total", {"broker": "paper"}) >= 2.0
        assert sample("execution_engine_open_positions", {"broker": "paper"}) == 1.0
        assert sample("execution_engine_realized_pnl", {"broker": "paper"}) == 50.0

    def test_risk_decision_counter(self):
        from prometheus_client import REGISTRY

        from execution_engine import execution_bus
        from execution_engine.events import risk_event
        from execution_engine.metrics import execution_metrics

        execution_metrics.install()
        execution_bus.publish(risk_event(user_id="u1", broker="paper", decision="APPROVED", message="ok"))
        value = REGISTRY.get_sample_value("execution_engine_risk_decisions_total", {"decision": "APPROVED"})
        assert value == 1.0


# ---------------------------------------------------------------------------
# Legacy composition
# ---------------------------------------------------------------------------
class TestLegacyComposition:
    def test_portfolio_manager_publishes_canonical_snapshot(self):
        from execution_engine import execution_bus
        from portfolio.manager import portfolio_manager
        from portfolio.models import PortfolioFunds, PortfolioPnL, PortfolioState

        state = PortfolioState(user_id="u9", broker="paper")
        state.pnl = PortfolioPnL(realised_pnl=123.45, unrealised_pnl=10.0, current_equity=500133.45)
        state.funds = PortfolioFunds(total_margin=500000.0, available_margin=250000.0)
        portfolio_manager._publish_canonical_snapshot(state, "u9", "paper")
        events = [e["event"] for e in execution_bus.recent(5)]
        assert "portfolio.snapshot" in events
        snapshot = next(e for e in execution_bus.recent(5) if e["event"] == "portfolio.snapshot")
        assert snapshot["payload"]["realised_pnl"] == 123.45
        assert snapshot["payload"]["available_margin"] == 250000.0
        assert snapshot["payload"]["source"] == "portfolio_manager"


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
class TestInit:
    @pytest.mark.asyncio
    async def test_init_wires_and_is_idempotent(self):
        from execution_engine import execution_bus
        from execution_engine.init import init_execution_engine, shutdown_execution_engine

        registry = init_execution_engine(asyncio.get_running_loop())
        assert execution_bus.running
        assert set(registry) >= {"bus", "trade_manager", "position_manager", "pnl_engine", "portfolio_engine", "execution_engine"}
        before = execution_bus.subscriber_count()
        init_execution_engine(asyncio.get_running_loop())  # no-op
        assert execution_bus.subscriber_count() == before
        await shutdown_execution_engine()
        assert not execution_bus.running

    @pytest.mark.asyncio
    async def test_init_without_loop_dispatches_inline(self):
        from execution_engine import execution_bus
        from execution_engine.init import init_execution_engine, shutdown_execution_engine

        init_execution_engine()  # running inside asyncio test -> picks up loop
        assert execution_bus.running
        await shutdown_execution_engine()

    @pytest.mark.asyncio
    async def test_shutdown_then_reinit_restarts_bus(self):
        from execution_engine import execution_bus
        from execution_engine.init import init_execution_engine, shutdown_execution_engine

        init_execution_engine(asyncio.get_running_loop())
        assert execution_bus.running
        await shutdown_execution_engine()
        assert not execution_bus.running
        init_execution_engine(asyncio.get_running_loop())
        assert execution_bus.running
        await shutdown_execution_engine()


# ---------------------------------------------------------------------------
# Legacy bus bridge -> engine integration
# ---------------------------------------------------------------------------
class TestLegacyBridge:
    """The production fill path: legacy OMS/paper events -> canonical engine."""

    @pytest.mark.asyncio
    async def test_oms_order_completed_reaches_position(self):
        from execution_engine import pnl_engine, portfolio_engine, position_manager, trade_manager
        from execution_engine.events import bridge_legacy_events
        from execution.event_bus import execution_event_bus
        from execution.models import ExecutionEvent

        pnl_engine._positions = position_manager
        portfolio_engine._positions = position_manager
        portfolio_engine._pnl = pnl_engine
        trade_manager.install()
        position_manager.install()

        bridge_legacy_events()
        await execution_event_bus.publish(ExecutionEvent(
            event_type="OrderCompleted",
            execution_request_id="req-1",
            user_id="u1", broker="fyers", symbol="NIFTY", side="BUY",
            message="filled",
            payload={"quantity": 10, "filled_quantity": 10, "average_price": 71.75,
                     "broker_order_id": "B-1", "oms_order_id": "oms-1",
                     "is_paper": False, "source": "engine", "strategy_id": "s1"},
        ))
        await asyncio.sleep(0.05)
        pos = position_manager.get_position("u1", "fyers", "NIFTY")
        assert pos is not None and pos.quantity == 10
        assert round(pos.average_price, 2) == 71.75

    @pytest.mark.asyncio
    async def test_paper_fill_events_reach_trade_ledger(self):
        from execution_engine import pnl_engine, portfolio_engine, position_manager, trade_manager
        from execution_engine.events import bridge_legacy_events
        from execution.event_bus import execution_event_bus
        from execution.models import ExecutionEvent

        pnl_engine._positions = position_manager
        portfolio_engine._positions = position_manager
        portfolio_engine._pnl = pnl_engine
        trade_manager.install()
        position_manager.install()

        bridge_legacy_events()
        for etype, req_id, payload in (
            ("PaperOrderFilled", "paper-1",
             {"order_id": "paper-1", "quantity": 10, "price": 73.0,
              "fill": {"order_id": "paper-1", "filled_quantity": 4, "filled_price": 73.25}}),
            ("PaperOrderPartiallyFilled", "paper-2",
             {"order_id": "paper-2", "quantity": 10, "price": 74.0,
              "fill": {"order_id": "paper-2", "filled_quantity": 3, "filled_price": 74.1}}),
        ):
            await execution_event_bus.publish(ExecutionEvent(
                event_type=etype,
                execution_request_id=req_id,
                user_id="u1", broker="paper", symbol="NIFTY", side="SELL",
                message="paper bridge",
                payload=payload,
            ))
        await asyncio.sleep(0.05)
        assert trade_manager.count("u1") == 2
        pos = position_manager.get_position("u1", "paper", "NIFTY")
        assert pos is not None and pos.quantity == -7

    @pytest.mark.asyncio
    async def test_unmapped_legacy_events_are_ignored(self):
        from execution_engine import pnl_engine, portfolio_engine, position_manager, trade_manager
        from execution_engine.events import bridge_legacy_events
        from execution.event_bus import execution_event_bus
        from execution.models import ExecutionEvent

        pnl_engine._positions = position_manager
        portfolio_engine._positions = position_manager
        portfolio_engine._pnl = pnl_engine
        trade_manager.install()
        position_manager.install()

        bridge_legacy_events()
        await execution_event_bus.publish(ExecutionEvent(
            event_type="PaperPositionUpdated", execution_request_id="x1",
            user_id="u1", broker="paper", symbol="NIFTY", side="BUY",
            payload={"order_id": "x1"},
        ))
        await execution_event_bus.publish(ExecutionEvent(
            event_type="OrderSent", execution_request_id="x2",
            user_id="u1", broker="paper", symbol="NIFTY", side="BUY",
            payload={},
        ))
        await asyncio.sleep(0.05)
        assert trade_manager.count("u1") == 0
        assert position_manager.get_position("u1", "paper", "NIFTY") is None

    def test_bridge_wiring_is_idempotent(self):
        from execution_engine.events import bridge_legacy_events
        from execution.event_bus import execution_event_bus

        bridge_legacy_events()
        before = len(execution_event_bus._subscribers.get("*", []))
        bridge_legacy_events()
        assert len(execution_event_bus._subscribers.get("*", [])) == before
