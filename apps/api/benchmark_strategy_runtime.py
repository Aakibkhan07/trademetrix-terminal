"""Strategy Runtime v1.0 — micro-benchmarks.

Measures the hot paths of the runtime in isolation:
1. tick-throughput   — dispatch_tick -> bounded queue -> _process_tick (EVERY_TICK)
2. candle-eval       — closed-candle evaluation latency (signal + order path)
3. fanout            — N workers on one symbol sharing one tick stream
4. dedup overhead    — repeated identical candle replay (seen-set guard)

Run:  PYTHONPATH=/app .venv/bin/python benchmark_strategy_runtime.py
"""
from __future__ import annotations

import asyncio
import datetime
import json
import time

from core.models import Candle, Exchange, NormalizedOrder, OrderResult, OrderSide, OrderType, ProductType, Tick
from strategies.base import SignalResult

USER = "benchmark-user"
N_TICKS = 50_000
N_CANDLES = 10_000
N_FANOUT_WORKERS = 10
N_FANOUT_TICKS = 10_000


class BenchStrategy:
    """Signals on every closed candle (worst-case: full signal + order path)."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._memory = {}
        self._candle_counter = 0

    async def on_start(self) -> None:
        pass

    async def on_stop(self) -> None:
        pass

    async def on_tick(self, tick: Tick) -> SignalResult | None:
        return None

    async def on_candle(self, candle: Candle) -> SignalResult | None:
        self._candle_counter += 1
        return SignalResult(
            reason="bench",
            orders=[NormalizedOrder(
                symbol=candle.symbol, exchange=Exchange.NSE, side=OrderSide.BUY,
                order_type=OrderType.MARKET, product=ProductType.INTRADAY,
                quantity=10,
            )],
        )


async def _fake_load(sid, symbol):
    return BenchStrategy({"symbol": symbol, "strategy_id": sid})


async def _fake_execute(user_id, order, source=""):
    return OrderResult(success=True, broker_order_id="b", status="filled", filled_qty=order.quantity, avg_price=100.0)


def _tick(ts: float, close: float) -> Tick:
    return Tick(
        symbol="NIFTY", exchange=Exchange.NSE, last_price=close,
        bid=close - 0.1, ask=close + 0.1, volume=100, oi=0,
        timestamp=datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc),
        broker="paper",
    )


async def _setup_manager():
    import strategy_runtime.workers as workers_module

    workers_module.load_strategy = _fake_load
    import engine.gate as gate_mod

    gate_mod.execute_order = _fake_execute

    # isolate pure runtime cost: audits (builder logs -> DB) and legacy-bus
    # event publishes are integration overhead, not runtime hot paths
    import builder.logs as logs_mod

    async def _noop_record(*args, **kwargs):
        return None

    logs_mod.record = _noop_record
    import strategy_runtime.manager as mgr_mod

    mgr_mod._publish_runtime_event = lambda *a, **k: None

    from strategy_runtime.manager import strategy_runtime_manager
    from strategy_runtime.observability import runtime_observability
    from strategy_runtime.models import StrategySpec, StrategyTrigger

    mgr = strategy_runtime_manager
    runtime_observability._running.clear()
    mgr._registry._records.clear()
    mgr._dispatcher._handlers.clear()
    mgr._dispatcher._workers.clear()
    mgr.configure_state_store(None)
    return mgr, StrategySpec, StrategyTrigger


async def bench_ticks(mgr, StrategySpec, StrategyTrigger) -> dict:
    spec = StrategySpec(
        strategy_id="bench-tick", user_id=USER, symbol="NIFTY", interval="15m",
        timeframes=["15m"], trigger=StrategyTrigger.EVERY_TICK, warmup=False,
    )
    await mgr.start_strategy(spec)
    worker = (await mgr._registry.get("bench-tick")).worker
    start = time.monotonic()
    base = datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc)
    for i in range(N_TICKS):
        worker.dispatch_tick(_tick(base.timestamp() + i * 0.001, 100.0 + (i % 7)))
        if i % 256 == 0:
            await asyncio.sleep(0)  # let the worker breathe (real world yields)
    while worker.record.stats["ticks_processed"] < N_TICKS:
        await asyncio.sleep(0.005)
    elapsed = time.monotonic() - start
    processed = worker.record.stats["ticks_processed"]
    dropped = worker.record.stats["dropped_ticks"]
    await mgr.stop_strategy("bench-tick", USER)
    return {
        "ticks_dispatched": N_TICKS,
        "ticks_processed": processed,
        "dropped": dropped,
        "elapsed_s": round(elapsed, 3),
        "ticks_per_sec": round(processed / elapsed),
    }


async def bench_candles(mgr, StrategySpec, StrategyTrigger) -> dict:
    spec = StrategySpec(
        strategy_id="bench-candle", user_id=USER, symbol="NIFTY", interval="15m",
        timeframes=["15m"], trigger=StrategyTrigger.CANDLE_CLOSE, warmup=False,
    )
    await mgr.start_strategy(spec)
    worker = (await mgr._registry.get("bench-candle")).worker
    start = time.monotonic()
    base = datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc)
    for i in range(N_CANDLES):
        candle = Candle(
            symbol="NIFTY", exchange=Exchange.NSE, interval="15m",
            open=100, high=101, low=99, close=100.5 + (i % 5),
            volume=1000, timestamp=(base + datetime.timedelta(minutes=15 * i)).isoformat(), oi=0,
        )
        await worker._handle_candle("15m", candle)
    elapsed = time.monotonic() - start
    await mgr.stop_strategy("bench-candle", USER)
    return {
        "candles": N_CANDLES,
        "elapsed_s": round(elapsed, 3),
        "evals_per_sec": round(N_CANDLES / elapsed),
        "avg_latency_ms": worker.record.stats.get("avg_latency_ms", 0),
        "orders": worker.record.stats.get("orders_placed", 0),
    }


async def bench_fanout(mgr, StrategySpec, StrategyTrigger) -> dict:
    from market.data_socket import shared_socket

    base = datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc)
    for i in range(N_FANOUT_WORKERS):
        await mgr.start_strategy(StrategySpec(
            strategy_id=f"bench-fan-{i:02d}", user_id=USER, symbol="NIFTY", interval="15m",
            timeframes=["15m"], trigger=StrategyTrigger.CANDLE_CLOSE, warmup=False,
        ))
    workers = [(await mgr._registry.get(f"bench-fan-{i:02d}")).worker for i in range(N_FANOUT_WORKERS)]
    expected = N_FANOUT_TICKS
    start = time.monotonic()
    for i in range(expected):
        await shared_socket.broadcast_tick(_tick(base.timestamp() + i * 0.001, 100.0 + (i % 7)))
    while any(w.record.stats["ticks_processed"] < expected for w in workers):
        await asyncio.sleep(0.005)
    elapsed = time.monotonic() - start
    per_worker = [w.record.stats["ticks_processed"] for w in workers]
    dropped = [w.record.stats["dropped_ticks"] for w in workers]
    for i in range(N_FANOUT_WORKERS):
        await mgr.stop_strategy(f"bench-fan-{i:02d}", USER)
    return {
        "workers": N_FANOUT_WORKERS,
        "ticks_fanned_out": expected,
        "elapsed_s": round(elapsed, 3),
        "ticks_per_sec": round(expected / elapsed),
        "min_worker_ticks": min(per_worker),
        "max_worker_ticks": max(per_worker),
        "worker_drop_total": sum(dropped),
    }


async def bench_dedup(mgr, StrategySpec, StrategyTrigger) -> dict:
    spec = StrategySpec(
        strategy_id="bench-dedup", user_id=USER, symbol="NIFTY", interval="15m",
        timeframes=["15m"], trigger=StrategyTrigger.CANDLE_CLOSE, warmup=False,
    )
    await mgr.start_strategy(spec)
    worker = (await mgr._registry.get("bench-dedup")).worker
    candle = Candle(
        symbol="NIFTY", exchange=Exchange.NSE, interval="15m",
        open=100, high=101, low=99, close=101.0, volume=1000,
        timestamp=datetime.datetime(2026, 8, 4, 9, 15, tzinfo=datetime.timezone.utc).isoformat(), oi=0,
    )
    start = time.monotonic()
    for _ in range(N_CANDLES):
        await worker._handle_candle("15m", candle)  # same candle every time
    elapsed = time.monotonic() - start
    await mgr.stop_strategy("bench-dedup", USER)
    return {
        "replays": N_CANDLES,
        "evaluations": worker.record.stats.get("candles_processed", 0),
        "orders": worker.record.stats.get("orders_placed", 0),
        "elapsed_s": round(elapsed, 3),
        "replays_per_sec": round(N_CANDLES / elapsed),
    }


async def main() -> None:
    mgr, Spec, Trigger = await _setup_manager()
    results = {
        "tick_throughput": await bench_ticks(mgr, Spec, Trigger),
        "candle_evaluation": await bench_candles(mgr, Spec, Trigger),
        "multi_strategy_fanout": await bench_fanout(mgr, Spec, Trigger),
        "seen_candle_dedup": await bench_dedup(mgr, Spec, Trigger),
    }
    print(json.dumps(results, indent=2))
    try:
        with open("/tmp/strategy_runtime_bench.json", "w") as f:
            json.dump(results, f, indent=2)
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
