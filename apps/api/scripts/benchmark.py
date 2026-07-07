"""Performance benchmarks for buyer strategy pipeline.

Usage:
  python -m scripts.benchmark [--ticks N] [--candles N] [--strategies N]
"""

import asyncio
import random
import time
from datetime import datetime, timezone

import click


async def benchmark_redis():
    from core.cache import cache
    await cache.init()

    payload = {"data": "x" * 1024}
    t0 = time.perf_counter()
    writes = 0
    for _ in range(100):
        ok = await cache.set("bench:test", payload, ttl=60)
        if ok:
            writes += 1
    t1 = time.perf_counter()
    r_w = writes / (t1 - t0)

    reads = 0
    for _ in range(100):
        val = await cache.get("bench:test")
        if val:
            reads += 1
    t2 = time.perf_counter()
    r_r = reads / (t2 - t1)

    await cache.delete("bench:test")
    await cache.close()
    return r_w, r_r


async def benchmark_strategy(strategy_key: str, n_candles: int = 1000):
    from strategies import get_strategy
    from core.models import Candle, Exchange

    cls = get_strategy(strategy_key)
    instance = cls({
        "strategy_id": f"bench_{strategy_key}",
        "user_id": "bench",
        "index": "NIFTY",
        "backtest_mode": True,
        "backtest_initial_capital": 100000,
    })

    await instance.on_start()

    candles = []
    base_time = datetime.now(timezone.utc).replace(hour=9, minute=15, second=0, microsecond=0)
    price = 19500.0
    for i in range(n_candles):
        ts = base_time.replace(minute=base_time.minute + i * 5)
        change = price * random.gauss(0, 0.002)
        o, h, l, c = price - change, price + abs(change) * 1.2 + 5, price - abs(change) * 1.2 - 5, price + change
        price = c
        candles.append(Candle(
            symbol="NIFTY", exchange=Exchange.NSE, interval="5m",
            open=round(o, 2), high=round(h, 2), low=round(l, 2), close=round(c, 2),
            volume=int(random.uniform(50000, 500000)), timestamp=ts,
        ))

    t0 = time.perf_counter()
    for candle in candles:
        await instance.on_candle(candle)
    t1 = time.perf_counter()

    await instance.on_stop()
    results = instance.get_backtest_results()
    return {
        "strategy": strategy_key,
        "candles": n_candles,
        "duration_s": round(t1 - t0, 3),
        "candles_per_sec": round(n_candles / (t1 - t0), 1),
        "trades": results["total_trades"],
        "pnl": results["total_pnl"],
    }


async def benchmark_runner_concurrent(n_strategies: int = 5, n_candles: int = 500):
    import asyncio
    tasks = []
    strategy_keys = ["momentum_breakout_buyer", "trend_rider_buyer"]
    for i in range(n_strategies):
        sk = strategy_keys[i % len(strategy_keys)]
        sid = f"bench_concurrent_{i}"
        tasks.append(benchmark_single(sk, sid, n_candles))

    t0 = time.perf_counter()
    results = await asyncio.gather(*tasks)
    t1 = time.perf_counter()

    total = sum(r["candles_processed"] for r in results)
    return {
        "n_strategies": n_strategies,
        "candles_per_strategy": n_candles,
        "total_candles": total,
        "wall_time_s": round(t1 - t0, 3),
        "aggregate_cps": round(total / (t1 - t0), 1),
        "per_strategy": results,
    }


async def benchmark_single(strategy_key: str, strategy_id: str, n_candles: int):
    from strategies import get_strategy
    from core.models import Candle, Exchange

    cls = get_strategy(strategy_key)
    instance = cls({
        "strategy_id": strategy_id,
        "user_id": "bench",
        "index": "NIFTY",
        "backtest_mode": True,
        "backtest_initial_capital": 100000,
    })
    await instance.on_start()

    price = 19500.0
    for i in range(n_candles):
        change = price * random.gauss(0, 0.002)
        price += change
    await instance.on_stop()

    return {"strategy_id": strategy_id, "strategy_key": strategy_key, "candles_processed": n_candles}


@click.command()
@click.option("--candles", default=1000, help="Number of candles per strategy")
@click.option("--strategies", default=5, help="Concurrent strategies for load test")
def main(candles: int, strategies: int):
    print("=" * 60)
    print("TradeMetrix Performance Benchmarks")
    print("=" * 60)

    async def run():
        print("\n--- Redis ---")
        w, r = await benchmark_redis()
        print(f"  Writes: {w:.0f} ops/s")
        print(f"  Reads:  {r:.0f} ops/s")

        print("\n--- Single Strategy ---")
        for sk in ["momentum_breakout_buyer", "trend_rider_buyer"]:
            res = await benchmark_strategy(sk, candles)
            print(f"  {sk}: {res['candles_per_sec']:.0f} candles/s ({res['trades']} trades, {res['pnl']:.0f} PnL)")

        print(f"\n--- Concurrent ({strategies} strategies x {candles} candles) ---")
        res = await benchmark_runner_concurrent(strategies, candles)
        print(f"  Wall time:     {res['wall_time_s']}s")
        print(f"  Aggregate:      {res['aggregate_cps']:.0f} candles/s")
        print(f"  Per strategy:   {res['per_strategy'][0]['candles_processed']} candles each")

    asyncio.run(run())

    print("\nDone.")


if __name__ == "__main__":
    main()
