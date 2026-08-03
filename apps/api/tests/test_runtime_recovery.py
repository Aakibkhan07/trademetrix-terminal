"""Runtime Persistence + Recovery — automated restart tests.

Simulates a process restart: build real engine state through the canonical
chain (legacy bus → TradeManager → PositionManager → PnL → Portfolio), persist
a checkpoint, reset the engine singletons (the "new process"), then recover and
assert byte-level deterministic restoration. Also covers idempotency (recovery
twice, re-persist) and strategy checkpoint restart wiring.
"""
import asyncio
import json

import pytest

from execution_engine.fifo import FifoLots
from execution_engine.persistence import (
    InMemoryCheckpointStore,
    enable_execution_persistence,
    recover_runtime_state,
    runtime_persistence,
)

USER = "recovery-test-user-0001"


@pytest.fixture(autouse=True)
def _clean_engine():
    """Isolated engine + persistence state; restore after (mirrors the
    canonical ``_clean_engine`` in test_execution_engine.py)."""
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

    runtime_persistence.configure(None)
    runtime_persistence._installed = False
    runtime_persistence._last_hash.clear()

    from engine.graph_strategy_runner import _running_tasks, _runtime
    for sid in list(_running_tasks):
        task = _running_tasks.pop(sid, None)
        if task and not task.done():
            task.cancel()
    _runtime.clear()

    yield

    runtime_persistence.configure(None)
    execution_bus.clear()
    for sid in list(_running_tasks):
        task = _running_tasks.pop(sid, None)
        if task and not task.done():
            task.cancel()
    _runtime.clear()


async def inject_fills(extra_buy: int = 0):
    """Publish the canonical 3-fill contract (+ optional opening buy) through
    the real legacy bus. Contract: realised PnL = 100, net flat.
    With extra_buy=5 -> open LONG 5 (avg 100, realised 100)."""
    from execution.event_bus import execution_event_bus
    from execution.models import ExecutionEvent
    from execution_engine.init import init_execution_engine

    init_execution_engine()

    def payload(req_id, qty, price, fill_qty):
        return {
            "order_id": req_id, "quantity": qty, "price": price,
            "fill": {"order_id": req_id, "filled_quantity": fill_qty, "filled_price": price},
            "is_paper": True, "strategy_id": "recovery-test", "source": "recovery-test",
        }

    async def pub(etype, req_id, side, qty, price, fill_qty):
        await execution_event_bus.publish(ExecutionEvent(
            event_type=etype, execution_request_id=req_id, user_id=USER,
            broker="paper", symbol="NIFTY", side=side, message="recovery test",
            payload=payload(req_id, qty, price, fill_qty),
        ))

    await pub("PaperOrderPartiallyFilled", "r-part", "SELL", 2, 110.0, 2)
    await pub("PaperOrderFilled", "r-buy", "BUY", 10, 100.0, 10)
    await pub("PaperOrderFilled", "r-sell", "SELL", 8, 110.0, 8)
    if extra_buy:
        await pub("PaperOrderFilled", "r-open", "BUY", extra_buy, 100.0, extra_buy)
    await asyncio.sleep(0.3)


def dump_normalized(user_id: str = USER) -> str:
    """Canonical dump with the wall-clock saved_at stripped (everything else
    must round-trip byte-for-byte)."""
    from execution_engine.persistence import dump_engine_state

    state = dump_engine_state(user_id)
    state.pop("saved_at", None)
    return json.dumps(state, sort_keys=True)


# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_checkpoint_roundtrip_deterministic():
    await inject_fills(extra_buy=5)
    state = dump_normalized()

    store = InMemoryCheckpointStore()
    await store.upsert(USER, "engine", "all", json.loads(state))

    from execution_engine.persistence import restore_engine_state

    restore_engine_state(USER, json.loads(state))
    assert dump_normalized() == state  # byte-identical after restore


@pytest.mark.asyncio
async def test_fifo_serialization_roundtrip():
    f = FifoLots()
    f.apply("BUY", 10, 100.0)
    f.apply("SELL", 4, 110.0)
    f.apply("BUY", 3, 101.0)
    restored = FifoLots.from_lots(f.to_lots())
    assert restored.to_lots() == f.to_lots()
    assert restored.long_quantity == f.long_quantity == 9
    assert restored.unrealized_pnl(120) == f.unrealized_pnl(120)


@pytest.mark.asyncio
async def test_restart_recovery_restores_paper_state():
    await inject_fills(extra_buy=5)
    store = InMemoryCheckpointStore()
    enable_execution_persistence(store)
    await runtime_persistence.persist_engine(USER)
    assert len(await store.load("engine", user_id=USER)) == 1

    before = dump_normalized()

    # ── "process restart": wipe all engine singletons + coordinator ──
    from execution_engine.events import ExecutionDomain, LoggingSink, execution_bus
    from execution_engine import pnl_engine, portfolio_engine, position_manager, trade_manager
    from execution_engine.metrics import execution_metrics
    from execution_engine.init import reset_execution_engine

    reset_execution_engine()
    execution_bus.reset_subscribers()
    execution_bus.subscribe(ExecutionDomain.ORDER, LoggingSink())
    execution_bus.clear()
    trade_manager.ledger.clear()
    for mgr in (position_manager, pnl_engine, portfolio_engine):
        mgr.clear()
    for mgr in (trade_manager, position_manager, pnl_engine, portfolio_engine, execution_metrics):
        mgr._installed = False
    runtime_persistence._installed = False
    runtime_persistence._last_hash.clear()
    enable_execution_persistence(store)  # durable store survives the "restart"

    # ── new process boots → re-init engine, then recovery ──
    from execution_engine.init import init_execution_engine

    init_execution_engine()
    result = await recover_runtime_state()
    assert result["engine_users"] == 1
    assert result["positions"] == 1
    assert result["accounts"] == 1

    assert dump_normalized() == before  # deterministic byte-level restore

    from execution_engine import pnl_engine, portfolio_engine, position_manager

    positions = position_manager.get_positions(USER, broker="paper")
    assert len(positions) == 1
    pos = positions[0]
    assert pos.symbol == "NIFTY"
    assert pos.side == "LONG"
    assert pos.quantity == 5
    assert pos.realised_pnl == 100.0
    assert pos.average_price == 100.0

    acc = pnl_engine.get_account(USER, "paper")
    assert acc.realised_pnl == 100.0
    assert acc.current_equity == 500100.0

    snap = portfolio_engine.snapshot(USER)
    assert snap is not None
    assert snap.open_positions == 1
    assert snap.realised_pnl == 100.0

    # FIFO lots survived: a closing fill realizes against the restored lots.
    from execution.event_bus import execution_event_bus
    from execution.models import ExecutionEvent

    await execution_event_bus.publish(ExecutionEvent(
        event_type="PaperOrderFilled", execution_request_id="r-close", user_id=USER,
        broker="paper", symbol="NIFTY", side="SELL", message="close after restart",
        payload={"order_id": "r-close", "quantity": 5, "price": 110.0,
                 "fill": {"order_id": "r-close", "filled_quantity": 5, "filled_price": 110.0},
                 "is_paper": True, "strategy_id": "recovery-test", "source": "recovery-test"},
    ))
    await asyncio.sleep(0.3)
    assert pnl_engine.get_account(USER, "paper").realised_pnl == pytest.approx(150.0)


@pytest.mark.asyncio
async def test_recovery_idempotent():
    await inject_fills(extra_buy=5)
    store = InMemoryCheckpointStore()
    enable_execution_persistence(store)
    await runtime_persistence.persist_engine(USER)

    from execution_engine import pnl_engine, position_manager

    await recover_runtime_state()
    first = dump_normalized()
    counts_first = (len(position_manager.get_positions(USER)), pnl_engine.get_account(USER, "paper").realised_pnl)

    await recover_runtime_state()
    assert dump_normalized() == first  # second recovery is a no-op
    counts_second = (len(position_manager.get_positions(USER)), pnl_engine.get_account(USER, "paper").realised_pnl)
    assert counts_second == counts_first
    assert len(await store.load("engine", user_id=USER)) == 1  # never duplicated


@pytest.mark.asyncio
async def test_persist_skips_when_state_unchanged():
    await inject_fills(extra_buy=5)
    store = InMemoryCheckpointStore()
    enable_execution_persistence(store)
    await runtime_persistence.persist_engine(USER)
    await runtime_persistence.persist_engine(USER)  # hash guard
    assert len(await store.load("engine", user_id=USER)) == 1


@pytest.mark.asyncio
async def test_recovery_without_store_is_noop():
    await inject_fills(extra_buy=5)
    enable_execution_persistence(None)
    result = await recover_runtime_state()
    assert result["engine_users"] == 0
    assert result["positions"] == 0


@pytest.mark.asyncio
async def test_strategy_checkpoint_persist_and_restart(monkeypatch):
    from engine import graph_strategy_runner as runner

    stats = runner._runtime_stats("strat-recover")
    stats.update({"status": "running", "user_id": USER, "symbol": "NIFTY",
                  "interval": "5m", "mode": "paper", "started_at": "2026-08-03T10:00:00Z"})

    store = InMemoryCheckpointStore()
    enable_execution_persistence(store)
    await runtime_persistence.persist_strategy("strat-recover")
    rows = await store.load("strategy", user_id=USER)
    assert len(rows) == 1
    assert rows[0]["data"]["symbol"] == "NIFTY"
    assert rows[0]["data"]["interval"] == "5m"
    assert rows[0]["data"]["is_paper"] is True

    # ── restart: fresh runner state, recovery must re-start the strategy ──
    runner._runtime.clear()
    runner._running_tasks.clear()

    calls: list[tuple] = []
    async def fake_start(strategy_id, user_id, symbol="NIFTY", interval="15m", is_paper=True):
        calls.append((strategy_id, user_id, symbol, interval, is_paper))
        return "started"

    monkeypatch.setattr(runner, "start_graph_strategy", fake_start)
    result = await recover_runtime_state()
    assert result["strategies"] == 1
    assert calls == [("strat-recover", USER, "NIFTY", "5m", True)]

    # ── stop clears the checkpoint (runner still knows the user) ──
    runner._runtime_stats("strat-recover").update({"user_id": USER})
    await runtime_persistence.delete_strategy("strat-recover")
    assert await store.load("strategy", user_id=USER) == []


@pytest.mark.asyncio
async def test_engine_checkpoint_written_on_portfolio_snapshot():
    store = InMemoryCheckpointStore()
    enable_execution_persistence(store)
    await inject_fills(extra_buy=5)  # init wires the coordinator; snapshot fires

    await asyncio.sleep(0.5)  # let the fire-and-forget writer land
    rows = await store.load("engine", user_id=USER)
    assert len(rows) == 1
    assert rows[0]["data"]["positions"][0]["symbol"] == "NIFTY"
    assert rows[0]["data"]["accounts"][0]["realised_pnl"] == 100.0
    assert "fifos" in rows[0]["data"]