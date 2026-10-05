"""Why does every backtest-capable strategy produce at most one trade?

Production, measured: 494 candles loaded, and

    trend_rider 1 · macd_cross 1 · bollinger_bandit 1 · rsi_mean_reversion 1 · orb_pro 0
    smc_sniper 1 · intraday_momentum 0 · mean_reversion_pro 0 · breakout_scanner 0
    arbitrage_hunter 1

Five independent signal strategies landing on the same count is a mechanical limit, not weak
signals. This separates the stages — how many signals each strategy emitted, how many orders
that became, and what happened to them — so the ceiling can be attributed to one of them
rather than guessed at.

Read-only: it calls `on_candle` on the strategies and never touches the broker or OMS.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.data_loader import backtest_data_loader as loader  # noqa: E402
from strategies import get_strategy, list_strategies  # noqa: E402

SYMBOL = "NSE:NIFTY50-INDEX"
EXCHANGE = "NSE"
INTERVAL = "1d"
DAYS = 730
# The durable candle store is user-scoped, so an unowned load finds nothing. Measured against
# the account that actually has candles in production.
USER_ID = os.environ.get("DIAG_USER_ID", "")


async def main() -> None:
    candles = await loader.load(
        symbol=SYMBOL,
        exchange=EXCHANGE,
        interval=INTERVAL,
        days=DAYS,
        user_id=USER_ID or None,
    )
    print(f"  candles loaded : {len(candles)}")
    if not candles:
        print("  no candles — nothing below is meaningful")
        return

    closes = [float(c.get("close", 0) or 0) for c in candles]
    stamps = [str(c.get("timestamp", ""))[:10] for c in candles]
    print(f"  close range    : {min(closes):.0f} .. {max(closes):.0f}")
    print(f"  date range     : {stamps[0]} .. {stamps[-1]}")
    print(f"  zero closes    : {sum(1 for c in closes if c == 0)}")
    print()

    print(f"  {'strategy':<24}{'signals':>9}{'orders':>8}  sides")
    print("  " + "-" * 62)

    for key in list_strategies():
        # Mirror manager._setup_strategy exactly: the class takes strategy_params, and
        # the symbol arrives through those params rather than as a constructor argument.
        cls = get_strategy(key)
        strat = cls({"symbol": SYMBOL})
        if strat is None:
            continue
        await strat.on_start()

        signals = 0
        orders = 0
        sides = []
        for raw in candles:
            sig = await strat.on_candle(loader.to_candle(raw))
            if sig and getattr(sig, "orders", None):
                signals += 1
                orders += len(sig.orders)
                sides.extend(getattr(o.side, "value", str(o.side)) for o in sig.orders)

        await strat.on_stop()
        buys = sides.count("BUY")
        sells = sides.count("SELL")
        print(f"  {key:<24}{signals:>9}{orders:>8}  BUY={buys} SELL={sells}")


if __name__ == "__main__":
    asyncio.run(main())
