"""Strategy Runtime v1.0 — recovery + restart tests.

Simulates a process restart: start strategies, persist checkpoints, reset the
runtime manager singletons ("new process"), then run RuntimeRecovery and assert
deterministic restoration: RUNNING strategies restored (restart counter bumps),
PAUSED restored as paused, already-running (legacy/adopted) strategies adopted
without a second worker, STOPPED/FAILED checkpoints skipped, and recovery is
idempotent (a second run is a no-op). Also verifies the engine-side guard that
prevents the legacy engine recovery from double-starting runtime-owned
strategies.
"""
import asyncio

import pytest

from execution_engine.persistence import (
    KIND_ENGINE,
    KIND_STRATEGY,
    InMemoryCheckpointStore,
    recover_runtime_state,
    runtime_persistence,
)
from strategy_runtime.models import RuntimeState, StrategySpec, StrategyTrigger

USER = "strategy-runtime-recovery-user"
SID_A = "sr-rec-a-000001"
SID_B = "sr-rec-b-000002"
SID_C = "sr-rec-c-000003"


class FakeStrategy:
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._memory = {}

    async def on_start(self) -> None:
        pass

    async def on_stop(self) -> None:
        pass

    async def on_tick(self, tick) -> None:
        return None

    async def on_candle(self, candle) -> None:
        return None


async def _fake_load_strategy(sid, symbol):
    return FakeStrategy({"symbol": symbol, "strategy_id": sid})


async def _fake_execute_order(user_id, order, source=""):
    from core.models import OrderResult

    return OrderResult(success=True, broker_order_id="fake", status="filled")


@pytest.fixture(autouse=True)
def _clean_runtime(monkeypatch):
    from execution_engine.events import ExecutionDomain, LoggingSink, execution_bus
    from execution_engine.init import reset_execution_engine

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
    store = InMemoryCheckpointStore()
    mgr.configure_state_store(store)
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

    monkeypatch.setattr(workers_module, "load_strategy", _fake_load_strategy)
    monkeypatch.setattr("engine.gate.execute_order", _fake_execute_order)

    yield mgr, store

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


def _spec(sid: str, trigger=StrategyTrigger.CANDLE_CLOSE) -> StrategySpec:
    return StrategySpec(
        strategy_id=sid,
        user_id=USER,
        symbol="NIFTY",
        exchange="NSE",
        interval="15m",
        timeframes=["15m"],
        mode="paper",
        is_paper=True,
        broker="paper",
        trigger=trigger,
        warmup=False,
        quantity=10,
        max_positions=1,
    )


async def _simulate_restart(mgr) -> None:
    """Tear down the manager as a new process would see it."""
    from engine.graph_strategy_runner import _running_tasks, _runtime

    for sid in list(_running_tasks):
        task = _running_tasks.pop(sid, None)
        if task and not task.done():
            task.cancel()
    _runtime.clear()
    mgr._registry._records.clear()
    for symbol, handler in list(mgr._dispatcher._handlers.items()):
        try:
            from market.data_socket import shared_socket

            shared_socket.unsubscribe(symbol, handler)
        except Exception:
            pass
    mgr._dispatcher._handlers.clear()
    mgr._dispatcher._workers.clear()


# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_recovery_restores_running_strategy(_clean_runtime):
    mgr, store = _clean_runtime
    assert (await mgr.start_strategy(_spec(SID_A)))["status"] == "started"
    rows = await store.load("strategy_runtime")
    assert any(r.get("key") == SID_A for r in rows)

    await _simulate_restart(mgr)
    from strategy_runtime.recovery import RuntimeRecovery

    result = await RuntimeRecovery(mgr).recover()
    assert result["restored"] == 1
    assert result["errors"] == 0
    assert mgr.runtime_state == RuntimeState.RECOVERED

    status = await mgr.get_status(SID_A, USER)
    assert status["state"] == "RUNNING"
    assert status["worker_active"] is True
    assert status["restart_count"] == 1  # persisted count +1 for the restart
    assert status["symbol"] == "NIFTY"


@pytest.mark.asyncio
async def test_recovery_idempotent(_clean_runtime):
    mgr, store = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))
    await _simulate_restart(mgr)

    from strategy_runtime.recovery import RuntimeRecovery

    first = await RuntimeRecovery(mgr).recover()
    assert first["restored"] == 1
    second = await RuntimeRecovery(mgr).recover()
    assert second["restored"] == 0
    assert second["skipped"] == 1  # already registered -> skip
    assert (await mgr.get_status(SID_A, USER))["state"] == "RUNNING"


@pytest.mark.asyncio
async def test_recovery_skips_stopped_strategies(_clean_runtime):
    mgr, store = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))
    await mgr.stop_strategy(SID_A, USER)
    rows = await store.load("strategy_runtime")
    assert not any(r.get("key") == SID_A for r in rows)  # checkpoint removed on stop

    await _simulate_restart(mgr)
    from strategy_runtime.recovery import RuntimeRecovery

    result = await RuntimeRecovery(mgr).recover()
    assert result["restored"] == 0
    assert (await mgr.get_status(SID_A, USER)) is None


@pytest.mark.asyncio
async def test_recovery_restores_paused_as_paused(_clean_runtime):
    mgr, store = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))
    await mgr.pause_strategy(SID_A, USER, reason="manual")
    rows = await store.load("strategy_runtime")
    assert rows[0]["data"]["state"] == "PAUSED"

    await _simulate_restart(mgr)
    from strategy_runtime.recovery import RuntimeRecovery

    result = await RuntimeRecovery(mgr).recover()
    assert result["restored"] == 1
    assert result["paused"] == 1
    status = await mgr.get_status(SID_A, USER)
    assert status["state"] == "PAUSED"
    assert status["paused_reason"] == "restored_paused"


@pytest.mark.asyncio
async def test_recovery_adopts_already_running_legacy(_clean_runtime):
    mgr, store = _clean_runtime
    # legacy runner already owns the strategy (engine recovery restarted it)
    from engine.graph_strategy_runner import _running_tasks

    parked = asyncio.Event()
    task = asyncio.create_task(parked.wait())
    _running_tasks[SID_A] = task
    # and its runtime checkpoint exists
    await mgr.start_strategy(_spec(SID_A))
    await _simulate_restart(mgr)
    # re-seed the legacy running task in the "new process"
    _running_tasks[SID_A] = asyncio.create_task(parked.wait())

    from strategy_runtime.recovery import RuntimeRecovery

    result = await RuntimeRecovery(mgr).recover()
    assert result["adopted"] == 1
    assert result["restored"] == 0
    record = await mgr._registry.get(SID_A)
    assert record is not None
    assert record.state == RuntimeState.RUNNING
    assert record.worker is None  # legacy keeps executing; no second worker

    task.cancel()
    await _simulate_restart(mgr)


@pytest.mark.asyncio
async def test_engine_recovery_skips_runtime_owned_strategies(_clean_runtime, monkeypatch):
    """The engine's legacy recovery must NOT double-start strategies the
    runtime owns (kind ``strategy_runtime`` checkpoint present)."""
    mgr, store = _clean_runtime
    spec = _spec(SID_A)
    # engine-side STRATEGY checkpoint + runtime checkpoint for the same sid
    await store.upsert(USER, KIND_STRATEGY, SID_A, spec.checkpoint())
    await store.upsert(USER, "strategy_runtime", SID_A, {
        "version": 1, "state": "RUNNING", "restart_count": 2,
        "spec": spec.checkpoint(),
    })

    started: list[str] = []

    async def fake_start(strategy_id, user_id, symbol="NIFTY", interval="15m", is_paper=True):
        started.append(strategy_id)
        return "started"

    monkeypatch.setattr("engine.graph_strategy_runner.start_graph_strategy", fake_start)
    runtime_persistence.configure(store)

    result = await recover_runtime_state()
    assert SID_A in result["strategy_skips"]
    assert started == []  # engine recovery left the runtime-owned strategy alone


@pytest.mark.asyncio
async def test_engine_recovery_restarts_legacy_only(_clean_runtime, monkeypatch):
    mgr, store = _clean_runtime
    spec = _spec(SID_B)
    await store.upsert(USER, KIND_STRATEGY, SID_B, spec.checkpoint())

    started: list[str] = []

    async def fake_start(strategy_id, user_id, symbol="NIFTY", interval="15m", is_paper=True):
        started.append(strategy_id)
        return "started"

    monkeypatch.setattr("engine.graph_strategy_runner.start_graph_strategy", fake_start)
    runtime_persistence.configure(store)

    result = await recover_runtime_state()
    assert started == [SID_B]
    assert result["strategies"] == 1


@pytest.mark.asyncio
async def test_recovery_fail_open_on_broken_store(_clean_runtime):
    mgr, store = _clean_runtime

    class BrokenStore:
        async def load(self, kind):
            raise RuntimeError("store down")

        async def upsert(self, *args, **kwargs):
            raise RuntimeError("store down")

    mgr.configure_state_store(BrokenStore())
    from strategy_runtime.recovery import RuntimeRecovery

    result = await RuntimeRecovery(mgr).recover()
    assert mgr.runtime_state == RuntimeState.RECOVERED  # never blocks startup
    assert result["restored"] == 0  # store reported unreadable -> nothing restored
