"""`StrategyWorker.drain()` is the condition-based wait the sleeping tests needed.

The strategy-runtime tests used to wait for the worker by sleeping:

    await _emit_closed_candle(...)   # includes await asyncio.sleep(0.05)
    await asyncio.sleep(0.5)         # in the max-daily-trades test
    assert status["stats"]["orders_placed"] == 1

AGENTS.md records that race being diagnosed — "the test checked status before the worker
processed all ticks" — and then *fixed* by lengthening the sleep. That is a bigger guess,
not a fix. On a loaded machine 0.5s is as likely to be too short as 0.05s, so the failure
moved to a slower day rather than going away.

The root cause was a product-code gap, not a test habit: `StrategyWorker._queue` is a real
`asyncio.Queue`, but `_run` never called `task_done()`. `Queue.unfinished_tasks` therefore
never returned to zero, `queue.join()` — the standard wait — could never complete, and every
caller had to guess a duration instead.

These tests assert the **effect**, because a `drain()` that returned immediately, or one
that only waited for the queue to be empty (ignoring the tick currently being evaluated),
would look correct and reintroduce the exact flake it was written to remove.
"""
import asyncio
import datetime

import pytest

from core.models import Exchange, Tick
from strategy_runtime import workers as workers_module

# Reuse the runtime harness rather than rebuilding it — the fake strategy, the spec
# builder and the manager fixture are all that is needed to get a live worker.
from tests.test_strategy_runtime import (  # noqa: F401
    SID_A,
    SYMBOL,
    USER,
    FakeStrategy,
    _clean_runtime,
    _spec,
)

from tests.test_strategy_runtime import _tick


async def _broadcast_pair(close, ts):
    """Broadcast the two ticks that close one candle — and no sleep.

    `MultiTimeframeDispatcher` emits the previous period's candle when a tick of the *next*
    period arrives, so a single tick closes nothing and `on_candle` never runs. Both tests
    below depend on the evaluation actually happening, so they send the pair themselves
    rather than reusing `_emit_closed_candle`, which sleeps 0.05s per call and would hide
    the in-flight window they are trying to observe.
    """
    from market.data_socket import shared_socket

    ts_dt = datetime.datetime.fromisoformat(ts)
    flush = (ts_dt + datetime.timedelta(minutes=15)).isoformat()
    await shared_socket.broadcast_tick(_tick(close=close, ts=ts, price=close - 0.5))
    await shared_socket.broadcast_tick(_tick(close=close, ts=flush, price=close))


def _worker(mgr):
    """The single live worker for this fixture's symbol.

    `TickDispatcher._workers` is keyed by **symbol** and holds a set, not by strategy id —
    so a sid lookup silently raises `KeyError` and an indexing shortcut would just as
    quietly grab the wrong worker once two strategies share a symbol.
    """
    workers = mgr._dispatcher._workers[SYMBOL]
    assert len(workers) == 1, f"expected one worker, got {len(workers)}"
    return next(iter(workers))


def _slow_on_candle(seconds: float):
    """A strategy whose evaluation takes real wall-clock time.

    This is what makes the race observable. Without an artificial delay the worker almost
    always finishes inside `sleep(0)`, so a broken `drain()` would pass by luck and the
    regression test would be worthless.
    """

    class SlowStrategy(FakeStrategy):
        async def on_candle(self, candle):
            await asyncio.sleep(seconds)
            return await super().on_candle(candle)

    return SlowStrategy


async def _emit(mgr, sid, close, ts):
    """Broadcast one tick pair that closes a candle, then wait for real completion."""
    from market.data_socket import shared_socket

    ts_dt = datetime.datetime.fromisoformat(ts)
    flush = (ts_dt + datetime.timedelta(minutes=15)).isoformat()
    await shared_socket.broadcast_tick(_tick(close=close, ts=ts, price=close - 0.5))
    await shared_socket.broadcast_tick(_tick(close=close, ts=flush, price=close))
    worker = _worker(mgr)
    assert await worker.drain(timeout=5.0) is True


@pytest.fixture
def _patch_strategy(monkeypatch):
    """Install a strategy class for `load_strategy`."""

    def _install(cls):
        async def _load(strategy_id, symbol):
            return cls({"symbol": symbol, "strategy_id": strategy_id})

        monkeypatch.setattr(workers_module, "load_strategy", _load)

    return _install


@pytest.mark.asyncio
async def test_drain_waits_for_an_evaluation_slower_than_any_sleep(
    _clean_runtime, _patch_strategy
):
    """The whole point: a 0.2s evaluation must still be fully accounted for.

    The old code slept a fixed 0.05s per candle. Against a strategy that takes 0.2s this
    asserts before the worker has finished, so `candles_processed` is 0 and the test fails
    on a slow machine. Nothing here sleeps at all.
    """
    _patch_strategy(_slow_on_candle(0.2))
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))

    await _emit(mgr, SID_A, 101.0, "2026-08-04T09:15:00+05:30")

    status = await mgr.get_status(SID_A, USER)
    assert status["stats"]["candles_processed"] == 1
    assert status["stats"]["orders_placed"] == 1


@pytest.mark.asyncio
async def test_drain_covers_the_in_flight_tick_not_just_the_queue(
    _clean_runtime, _patch_strategy
):
    """A tick already `get()`-ed is out of the queue but still being evaluated.

    This is the subtle half. Waiting for `queue.empty()` alone would return `True` here the
    instant the worker pulled the tick off the queue — before `on_candle` had run — so the
    assertion below would see `candles_processed == 0` and the caller would have no idea the
    number it is about to trust is not final.
    """
    _patch_strategy(_slow_on_candle(0.15))
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))

    worker = _worker(mgr)
    await _broadcast_pair(101.0, "2026-08-04T09:15:00+05:30")

    # Let the worker take the ticks off the queue and start evaluating. The strategy
    # sleeps 0.15s, so this lands mid-evaluation with the queue already empty.
    await asyncio.sleep(0.05)
    assert worker._queue.empty(), "precondition: the ticks are out of the queue"

    assert await worker.drain(timeout=5.0) is True
    assert worker.record.stats["candles_processed"] == 1


@pytest.mark.asyncio
async def test_drain_returns_true_when_there_is_nothing_to_wait_for(_clean_runtime):
    """An idle worker must not block — `drain()` is called unconditionally."""
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))
    worker = _worker(mgr)

    assert await worker.drain(timeout=0.5) is True


@pytest.mark.asyncio
async def test_drain_reports_false_instead_of_hanging_when_the_worker_is_gone(
    _clean_runtime,
):
    """A dead worker with queued ticks cannot drain, and must say so.

    Returning `False` rather than blocking forever is the property that makes `drain()`
    safe in a test teardown or a shutdown path. A hang is worse than a wrong number: it
    burns the whole CI job instead of failing one assertion.
    """
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))
    worker = _worker(mgr)

    await worker.stop()  # cancels _run, so nothing will ever call task_done again

    worker._queue.put_nowait(_tick(close=101.0, ts="2026-08-04T09:15:00+05:30"))
    assert await worker.drain(timeout=0.5) is False


@pytest.mark.asyncio
async def test_drain_reports_false_when_a_live_worker_is_too_slow(
    _clean_runtime, _patch_strategy
):
    """The timeout is a backstop, and it must report the timeout rather than raise.

    `asyncio.wait_for` raises `TimeoutError` on expiry; a caller waiting for a worker's
    numbers to be meaningful wants a boolean. Letting the exception escape would turn a
    slow-but-correct worker into a crash.
    """
    _patch_strategy(_slow_on_candle(1.5))
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))

    worker = _worker(mgr)
    await _broadcast_pair(101.0, "2026-08-04T09:15:00+05:30")

    assert await worker.drain(timeout=0.05) is False
    # Still processing — the false was about the wait, not about a failure.
    assert worker.is_alive() is True


@pytest.mark.asyncio
async def test_queue_accounting_returns_to_zero_after_a_candle(_clean_runtime):
    """`task_done()` must be paired with every `put`, or the accounting drifts.

    The pairing is the mechanism `drain()` rests on, and a drift is invisible from outside:
    `drain()` would simply never return. Asserting `unfinished_tasks` directly makes the
    invariant checkable instead of implied.
    """
    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))
    worker = _worker(mgr)

    await _emit(mgr, SID_A, 101.0, "2026-08-04T09:15:00+05:30")
    await _emit(mgr, SID_A, 102.0, "2026-08-04T09:30:00+05:30")

    assert worker._queue._unfinished_tasks == 0


@pytest.mark.asyncio
async def test_a_failing_evaluation_does_not_leak_queue_accounting(
    _clean_runtime, monkeypatch
):
    """A strategy that raises must not leave `unfinished_tasks` stuck above zero.

    This is the `finally` in `_run`. Without it the first exception unbalances the counter
    for the rest of the process, and every later `drain()` — in this test, in another test,
    or on a worker reused after a reconnect — waits for a tick that will never be marked
    done.
    """

    class ExplodingStrategy(FakeStrategy):
        async def on_candle(self, candle):
            raise RuntimeError("boom")

    async def _load(strategy_id, symbol):
        return ExplodingStrategy({"symbol": symbol, "strategy_id": strategy_id})

    monkeypatch.setattr(workers_module, "load_strategy", _load)

    mgr = _clean_runtime
    await mgr.start_strategy(_spec(SID_A))
    worker = _worker(mgr)

    from market.data_socket import shared_socket

    await shared_socket.broadcast_tick(
        Tick(
            symbol=SYMBOL,
            exchange=Exchange.NSE,
            last_price=101.0,
            bid=101.0,
            ask=101.0,
            volume=1,
            oi=0,
            timestamp=datetime.datetime.fromisoformat("2026-08-04T09:30:00+05:30"),
            broker="paper",
        )
    )
    # Wait for the worker's own failure handling to run.
    for _ in range(50):
        await asyncio.sleep(0.02)
        if worker._queue._unfinished_tasks == 0:
            break

    assert worker._queue._unfinished_tasks == 0, "task_done must fire even on exception"
