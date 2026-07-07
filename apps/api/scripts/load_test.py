"""Load test — simulates high-frequency tick/candle load on buyer strategies.

Usage:
  python -m scripts.load_test [--strategies N] [--ticks N] [--candles N]
"""

import asyncio
import logging
import random
import time
from datetime import datetime, timezone

import click
from core.models import Candle, Exchange, Tick

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def make_tick(symbol: str, price: float) -> Tick:
    return Tick(
        symbol=symbol,
        ltp=price,
        volume=random.randint(1000, 50000),
        bid=price - 0.5,
        ask=price + 0.5,
        high=price + random.random() * 10,
        low=price - random.random() * 10,
        open=price - 2,
        close=price - 1,
        change=random.uniform(-1, 1),
        broker="load_test",
        timestamp=datetime.now(timezone.utc),
    )


async def simulate_ticks(n_ticks: int, symbols: list[str]):
    from market.data_socket import shared_socket
    from market.candle_aggregator import CandleAggregator

    aggregators = {s: CandleAggregator(s, "5m") for s in symbols}
    candle_counts = {s: 0 for s in symbols}

    async def tick_handler(tick: Tick) -> None:
        agg = aggregators.get(tick.symbol)
        if agg:
            candle = agg.add_tick(tick)
            if candle:
                candle_counts[tick.symbol] += 1

    for s in symbols:
        shared_socket.subscribe(s, tick_handler)
    shared_socket.subscribe("*", tick_handler)

    prices = {s: random.uniform(19000, 20000) for s in symbols}
    t0 = time.perf_counter()

    for _ in range(n_ticks):
        for s in symbols:
            prices[s] += random.gauss(0, 2)
            tick = make_tick(s, prices[s])
            await shared_socket.broadcast_tick(tick)

        if _ % 1000 == 0 and _ > 0:
            elapsed = time.perf_counter() - t0
            cps = _ / elapsed
            print(f"  {_} ticks, {cps:.0f} ticks/s, candles: {candle_counts}")

    t1 = time.perf_counter()

    for s in symbols:
        shared_socket.unsubscribe(s, tick_handler)
    shared_socket.unsubscribe("*", tick_handler)

    return {
        "ticks": n_ticks,
        "symbols": len(symbols),
        "duration_s": round(t1 - t0, 3),
        "ticks_per_sec": round(n_ticks / (t1 - t0), 1),
        "candles_generated": candle_counts,
    }


async def simulate_strategies(n_strategies: int, n_candles: int):
    from strategies import get_strategy
    from strategies.buyer_backtest import BuyerBacktestEngine

    results = []

    for i in range(n_strategies):
        sk = "momentum_breakout_buyer" if i % 2 == 0 else "trend_rider_buyer"
        cfg = {
            "strategy_id": f"load_{i}",
            "user_id": "load_test",
            "index": "NIFTY",
            "capital": 100000,
            "backtest_mode": True,
        }
        engine = BuyerBacktestEngine(sk, cfg, 100000)

        candles = []
        base_time = datetime.now(timezone.utc).replace(hour=9, minute=15, second=0, microsecond=0)
        price = 19500.0
        for j in range(n_candles):
            ts = base_time.replace(minute=base_time.minute + j * 5)
            change = price * random.gauss(0, 0.002)
            o, h, l, c = price - change, price + abs(change) * 1.2 + 5, price - abs(change) * 1.2 - 5, price + change
            price = c
            candles.append(Candle(
                symbol="NIFTY", exchange=Exchange.NSE, interval="5m",
                open=round(o, 2), high=round(h, 2), low=round(l, 2), close=round(c, 2),
                volume=int(random.uniform(50000, 500000)), timestamp=ts,
            ))

        result = await engine.run(candles)
        results.append(result)

    total_candles = n_candles * n_strategies
    total_trades = sum(r["total_trades"] for r in results)
    avg_win_rate = sum(r["win_rate"] for r in results) / len(results) if results else 0
    avg_pnl = sum(r["total_pnl"] for r in results) / len(results) if results else 0

    return {
        "n_strategies": n_strategies,
        "candles_per_strategy": n_candles,
        "total_candles": total_candles,
        "total_trades": total_trades,
        "avg_win_rate": round(avg_win_rate, 2),
        "avg_pnl": round(avg_pnl, 2),
    }


@click.command()
@click.option("--strategies", default=10, help="Number of concurrent strategies")
@click.option("--ticks", default=50000, help="Number of ticks to simulate")
@click.option("--candles", default=1000, help="Candles per strategy")
def main(strategies: int, ticks: int, candles: int):
    print("=" * 60)
    print("TradeMetrix Load Test")
    print("=" * 60)

    async def run():
        print(f"\n--- Tick Pipeline ({ticks} ticks, 3 symbols) ---")
        res = await simulate_ticks(ticks, ["NIFTY", "BANKNIFTY", "SENSEX"])
        print(f"  Duration:      {res['duration_s']}s")
        print(f"  Throughput:    {res['ticks_per_sec']:.0f} ticks/s")
        print(f"  Candles:       {res['candles_generated']}")

        print(f"\n--- Strategy Load ({strategies} strategies x {candles} candles) ---")
        t0 = time.perf_counter()
        res = await simulate_strategies(strategies, candles)
        t1 = time.perf_counter()
        print(f"  Duration:      {round(t1 - t0, 3)}s")
        print(f"  Candles/s:     {round(res['total_candles'] / (t1 - t0), 1)}")
        print(f"  Total trades:  {res['total_trades']}")
        print(f"  Avg win rate:  {res['avg_win_rate']}%")
        print(f"  Avg P&L:       {res['avg_pnl']:.2f}")

    asyncio.run(run())
    print("\nDone.")


if __name__ == "__main__":
    main()
