"""Strategy Runtime v1.0 — core lifecycle tests.

Covers: start/stop/pause/resume/restart state transitions, tick fan-out +
candle aggregation (multi-timeframe), strategy isolation (two strategies never
share workers/queues), manual evaluation, session events, broker disconnect/
reconnect, and deterministic no-duplicate evaluation (seen-candle dedup).
"""
import asyncio
import datetime

import pytest

from core.models import (
    Candle,
    Exchange,
    NormalizedOrder,
    OrderResult,
    OrderSide,
    OrderType,
    ProductType,
    Tick,
)
from strategies.base import SignalResult
from strategy_runtime.models import RuntimeState, StrategySpec, StrategyTrigger

USER = "strategy-runtime-test-user"
SID_A = "sr-a-000001"
SID_B = "sr-b-000002"
SYMBOL = "NIFTY"


class FakeStrategy:
    """Deterministic fake GraphStrategy: signals on every closed candle
    whose close > 100 (one MARKET BUY per signal, deduped by the worker)."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._memory = {}
        self.candles_seen = 0
        self.started = False
        self.stopped = False
        self.symbol = config.get("symbol", SYMBOL)
        self.strategy_id = config.get("strategy_id", "")

    async def on_start(self) -> None:
        self.started = True

    async def on_stop(self) -> None:
        self.stopped = True

    async def on_tick(self, tick: Tick) -> SignalResult | None:
        return None

    async def on_candle(self, candle: Candle) -> SignalResult | None:
        self.candles_seen += 1
        if candle.close > 100.0:
            return SignalResult(
                reason="fake-buy",
                orders=[NormalizedOrder(
                    symbol=candle.symbol,
                    exchange=Exchange.NSE,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    product=ProductType.INTRADAY,
                    quantity=10,
                )],
            )
        return None


async def _fake_execute_order(user_id, order, source=""):
    return OrderResult(
        success=True,
        broker_order_id=f"fake-{order.id or order.symbol}",
        status="filled",
        filled_qty=order.quantity,
        avg_price=float(order.price or 100.0),
    )


@pytest.fixture(autouse=True)
def _clean_runtime(monkeypatch):
    """Isolated runtime manager + a fake engine gate.

    pytest-asyncio strict mode gives every test a fresh event loop, so worker
    tasks die with the loop; this fixture only resets the process-wide
    singletons (manager registry, dispatcher, engine, legacy runner stats).
    """
    from execution_engine.events import ExecutionDomain, LoggingSink, execution_bus
    from execution_engine.init import reset_execution_engine
    from execution_engine.persistence import InMemoryCheckpointStore, runtime_persistence

    from strategy_runtime import workers as workers_module

    reset_execution_engine()
    execution_bus.reset_subscribers()
    execution_bus.subscribe(ExecutionDomain.ORDER, LoggingSink())
    execution_bus.clear()

    runtime_persistence.configure(None)
    runtime_persistence._installed = False
    runtime_persistence._last_hash.clear()

    from engine.graph_strategy_runner import _running_tasks, _runtime
    for sid in list(_running_tasks):
        task = _running_tasks.pop(sid, None)
        if task and not task.done():
            task.cancel()
    _runtime.clear()

    from market.data_socket import shared_socket
    from strategy_runtime.manager import strategy_runtime_manager
    from strategy_runtime.observability import runtime_observability

    mgr = strategy_runtime_manager
    runtime_observability._running.clear()
    mgr.configure_state_store(InMemoryCheckpointStore())
    mgr._initialized = False
    mgr._registry._records.clear()
    mgr._broker_states.clear()
    for symbol, handler in list(mgr._dispatcher._handlers.items()):
        try:
            shared_socket.unsubscribe(symbol, handler)
        except Exception:
            pass
    mgr._dispatcher._handlers.clear()
    mgr._dispatcher._workers.clear()

    async def _fake_load_strategy(sid, symbol):
        return FakeStrategy({"symbol": symbol, "strategy_id": sid})

    monkeypatch.setattr(workers_module, "load_strategy", _fake_load_strategy)
    monkeypatch.setattr("engine.gate.execute_order", _fake_execute_order)

    yield mgr

    mgr._registry._records.clear()
    for symbol, handler in list(mgr._dispatcher._handlers.items()):
        try:
            shared_socket.unsubscribe(symbol, handler)
        except Exception:
            pass
    mgr._dispatcher._handlers.clear()
    mgr._dispatcher._workers.clear()
    mgr.configure_state_store(None)
    for sid in list(_running_tasks):
        task = _running_tasks.pop(sid, None)
        if task and not task.done():
            task.cancel()
    _runtime.clear()


def _spec(sid: str, trigger=StrategyTrigger.CANDLE_CLOSE, warmup=False,
          timeframes=None, symbol=SYMBOL, broker="paper") -> StrategySpec:
    return StrategySpec(
        strategy_id=sid,
        user_id=USER,
        symbol=symbol,
        exchange="NSE",
        interval="15m",
        timeframes=timeframes or ["15m"],
        mode="paper",
        is_paper=True,
        broker=broker,
        trigger=trigger,
        warmup=warmup,
        quantity=10,
        max_positions=1,
    )


def _tick(close: float, ts: str, price: float | None = None) -> Tick:
    return Tick(
        symbol=SYMBOL,
        exchange=Exchange.NSE,
        last_price=price or close,
        bid=price or close,
        ask=price or close,
        volume=1000,
        oi=0,
        timestamp=datetime.datetime.fromisoformat(ts),
        broker="paper",
    )


async def _emit_closed_candle(close: float, ts: str) -> None:
    """Drive one FULLY CLOSED candle through the MTF path.

    The shared CandleAggregator emits the PREVIOUS period's candle when a tick
    of the next period arrives, so we send one tick in the candle's own period
    and a flush tick 15m later (which opens the next period's in-progress
    candle — its values are overwritten by the next real candle's ticks).
    """
    from market.data_socket import shared_socket

    ts_dt = datetime.datetime.fromisoformat(ts)
    flush = (ts_dt + datetime.timedelta(minutes=15)).isoformat()
    await shared_socket.broadcast_tick(_tick(close=close, ts=ts, price=close - 0.5))
    await shared_socket.broadcast_tick(_tick(close=close, ts=flush, price=close))
    await asyncio.sleep(0.05)


# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_start_stop_lifecycle(_clean_runtime):
    mgr = _clean_runtime
    out = await mgr.start_strategy(_spec(SID_A))
    assert out["status"] == "started"
    status = await mgr.get_status(SID_A, USER)
    assert status["state"] == "RUNNING"
    assert status["worker_active"] is True

    out = await mgr.start_strategy(_spec(SID_A))
    assert out["status"] == "already_running"

    out = await mgr.stop_strategy(SID_A, USER)
    assert out["status"] == "stopped"
    status = await mgr.get_status(SID_A, USER)
    assert status["state"] == "STOPPED"
    assert status["worker_active"] is False


@pytest.mark.asyncio
async def test_pause_resume_restart(_clean_runtime):
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))
    assert (await mgr.pause_strategy(SID_A, USER))["status"] == "paused"
    assert (await mgr.get_status(SID_A, USER))["state"] == "PAUSED"
    assert (await mgr.resume_strategy(SID_A, USER))["status"] == "resumed"
    assert (await mgr.get_status(SID_A, USER))["state"] == "RUNNING"
    assert (await mgr.restart_strategy(SID_A, USER))["status"] == "restarted"
    status = await mgr.get_status(SID_A, USER)
    assert status["state"] == "RUNNING"
    assert status["restart_count"] == 1


@pytest.mark.asyncio
async def test_state_machine_transition_table():
    from strategy_runtime.state_machine import (
        IllegalTransition,
        can_transition,
        require_transition,
    )

    assert can_transition(RuntimeState.RUNNING, RuntimeState.PAUSED)
    assert can_transition(RuntimeState.PAUSED, RuntimeState.RUNNING)
    assert can_transition(RuntimeState.STOPPED, RuntimeState.STARTING)
    assert not can_transition(RuntimeState.RUNNING, RuntimeState.CREATED)
    assert not can_transition(RuntimeState.RECOVERED, RuntimeState.RUNNING)

    require_transition(RuntimeState.RUNNING, RuntimeState.PAUSED)  # ok
    with pytest.raises(IllegalTransition):
        require_transition(RuntimeState.RECOVERED, RuntimeState.RUNNING)


@pytest.mark.asyncio
async def test_restart_from_stopped(_clean_runtime):
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))
    await mgr.stop_strategy(SID_A, USER)
    assert (await mgr.start_strategy(_spec(SID_A)))["status"] == "started"
    status = await mgr.get_status(SID_A, USER)
    assert status["state"] == "RUNNING"
    assert status["restart_count"] == 0  # fresh start, not a restart


@pytest.mark.asyncio
async def test_candle_close_evaluates_and_executes(_clean_runtime):
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))
    await _emit_closed_candle(close=101.0, ts="2026-08-04T09:15:00+05:30")
    await asyncio.sleep(0.1)
    status = await mgr.get_status(SID_A, USER)
    assert status["stats"]["candles_processed"] == 1
    assert status["stats"]["signals"] == 1
    assert status["stats"]["orders_placed"] == 1
    assert status["stats"]["orders_filled"] == 1


@pytest.mark.asyncio
async def test_no_duplicate_evaluation_same_candle(_clean_runtime):
    """The same closed candle (deduped by timestamp) never evaluates twice —
    no duplicate orders on ticker noise / time triggers / replays."""
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))
    worker = (await mgr._registry.get(SID_A)).worker
    candle = Candle(
        symbol=SYMBOL, exchange=Exchange.NSE, interval="15m",
        open=100.0, high=102.0, low=99.0, close=101.0, volume=100.0,
        timestamp=_timestamp(0), oi=0.0,
    )
    await worker._handle_candle("15m", candle)
    await worker._handle_candle("15m", candle)  # same candle again
    assert worker.record.stats["candles_processed"] == 1
    assert worker.record.stats["signals"] == 1
    assert worker.record.stats["orders_placed"] == 1


@pytest.mark.asyncio
async def test_no_signal_when_condition_false(_clean_runtime):
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))
    await _emit_closed_candle(close=50.0, ts="2026-08-04T09:15:00+05:30")
    await asyncio.sleep(0.05)
    status = await mgr.get_status(SID_A, USER)
    assert status["stats"]["candles_processed"] == 1
    assert status["stats"]["signals"] == 0
    assert status["stats"]["orders_placed"] == 0


@pytest.mark.asyncio
async def test_pause_halts_evaluation_resume_resets_aggregation(_clean_runtime):
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))
    await _emit_closed_candle(close=101.0, ts="2026-08-04T09:15:00+05:30")
    await asyncio.sleep(0.05)
    assert (await mgr.pause_strategy(SID_A, USER))["status"] == "paused"
    await _emit_closed_candle(close=102.0, ts="2026-08-04T09:30:00+05:30")
    await asyncio.sleep(0.05)
    status = await mgr.get_status(SID_A, USER)
    assert status["stats"]["candles_processed"] == 1  # paused -> no new eval

    assert (await mgr.resume_strategy(SID_A, USER))["status"] == "resumed"
    # resume resets MTF so pre-pause candles are never replayed
    await _emit_closed_candle(close=103.0, ts="2026-08-04T09:45:00+05:30")
    await asyncio.sleep(0.05)
    status = await mgr.get_status(SID_A, USER)
    assert status["stats"]["candles_processed"] == 2


@pytest.mark.asyncio
async def test_strategy_isolation_two_strategies(_clean_runtime):
    """Two strategies on the same symbol get separate queues/workers/eval
    locks — stats never cross-contaminate."""
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))
    await mgr.start_strategy(_spec(SID_B))
    await _emit_closed_candle(close=101.0, ts="2026-08-04T09:15:00+05:30")
    await asyncio.sleep(0.1)
    sa = await mgr.get_status(SID_A, USER)
    sb = await mgr.get_status(SID_B, USER)
    assert sa["stats"]["candles_processed"] == 1
    assert sb["stats"]["candles_processed"] == 1
    assert sa["stats"]["orders_placed"] == 1
    assert sb["stats"]["orders_placed"] == 1
    assert sa["strategy_id"] != sb["strategy_id"]

    await mgr.stop_strategy(SID_A, USER)
    assert (await mgr.get_status(SID_A, USER))["state"] == "STOPPED"
    assert (await mgr.get_status(SID_B, USER))["state"] == "RUNNING"


@pytest.mark.asyncio
async def test_multi_timeframe_aggregation(_clean_runtime):
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A, timeframes=["15m", "60m"]))
    # five 15m candles: the 4th closes the flush tick of the 5th
    for i in range(5):
        await _emit_closed_candle(close=101.0 + i, ts=_timestamp(i))
    await asyncio.sleep(0.1)
    status = await mgr.get_status(SID_A, USER)
    assert status["stats"]["candles_processed"] == 5
    assert status["stats"]["signals"] == 5


def _timestamp(i: int) -> str:
    start = datetime.datetime(2026, 8, 4, 9, 15, tzinfo=datetime.timezone.utc)
    return (start + datetime.timedelta(minutes=15 * i)).isoformat()


@pytest.mark.asyncio
async def test_manual_evaluate_dry_run(_clean_runtime):
    """Manual evaluation returns the signal but never places orders."""
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))
    await _emit_closed_candle(close=101.0, ts="2026-08-04T09:15:00+05:30")
    await asyncio.sleep(0.05)
    result = await mgr.manual_evaluate(SID_A, USER)
    assert result["evaluated"] is True
    assert result["signal"] is not None
    status = await mgr.get_status(SID_A, USER)
    assert status["stats"]["orders_placed"] == 1  # candle-path order only


@pytest.mark.asyncio
async def test_broker_disconnect_pauses_and_reconnect_resumes(_clean_runtime):
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A, broker="fyers"))
    await mgr.emit_event("broker_disconnect", payload={"broker": "fyers"})
    status = await mgr.get_status(SID_A, USER)
    assert status["state"] == "PAUSED"
    assert status["paused_reason"] == "broker_disconnect"

    await mgr.emit_event("broker_reconnect", payload={"broker": "fyers"})
    status = await mgr.get_status(SID_A, USER)
    assert status["state"] == "RUNNING"


@pytest.mark.asyncio
async def test_broker_disconnect_only_affects_matching_broker(_clean_runtime):
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A, broker="fyers"))
    await mgr.start_strategy(_spec(SID_B, broker="paper"))
    await mgr.emit_event("broker_disconnect", payload={"broker": "fyers"})
    assert (await mgr.get_status(SID_A, USER))["state"] == "PAUSED"
    assert (await mgr.get_status(SID_B, USER))["state"] == "RUNNING"


@pytest.mark.asyncio
async def test_session_open_starts_market_open_strategies(_clean_runtime):
    mgr = _clean_runtime
    spec = _spec(SID_A, trigger=StrategyTrigger.MARKET_OPEN)
    from strategy_runtime.registry import RuntimeRecord

    await mgr._registry.add(RuntimeRecord(spec))
    await mgr.emit_event("session_open")
    assert (await mgr.get_status(SID_A, USER))["state"] == "RUNNING"


@pytest.mark.asyncio
async def test_session_close_stops_market_close_strategies(_clean_runtime):
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A, trigger=StrategyTrigger.MARKET_CLOSE))
    await mgr.emit_event("session_close")
    assert (await mgr.get_status(SID_A, USER))["state"] == "STOPPED"


@pytest.mark.asyncio
async def test_checkpoint_persisted_and_removed(_clean_runtime):
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))
    rows = await mgr._state_store.load_all()
    assert any(r.get("key") == SID_A for r in rows)
    assert rows[0]["data"]["state"] == "RUNNING"
    await mgr.stop_strategy(SID_A, USER)
    rows = await mgr._state_store.load_all()
    assert not any(r.get("key") == SID_A for r in rows)


@pytest.mark.asyncio
async def test_health_surface(_clean_runtime):
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))
    health = await mgr.health()
    assert health["status"] == "healthy"
    assert health["strategies_running"] == 1
    assert SID_A in health["running_list"]
    assert health["metrics"]["running_count"] == 1


@pytest.mark.asyncio
async def test_user_isolation(_clean_runtime):
    mgr = _clean_runtime
    other = "other-user"
    await mgr.start_strategy(_spec(SID_A))
    assert (await mgr.get_status(SID_A, other)) is None
    assert (await mgr.stop_strategy(SID_A, other))["status"] == "forbidden"
    assert (await mgr.get_status(SID_A, USER))["state"] == "RUNNING"