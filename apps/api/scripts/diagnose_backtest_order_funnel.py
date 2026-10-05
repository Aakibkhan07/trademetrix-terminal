"""Where do a backtest's orders go after the strategy emits them?

Production returned one trade for macd_cross on 494 daily candles. The strategy emits an order
on every MACD crossover and has no position awareness, so the ceiling is either the risk
simulator refusing orders or the broker refusing to fill them. `BacktestResult.risk_analytics`
carries the rejection reason per order, so running the real path and printing those attributes
the ceiling instead of guessing.

Read-only: BacktestBroker is in-process, no OMS queue and no broker network call.
"""

import asyncio
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.manager import backtest_manager  # noqa: E402
from backtest.models import BacktestConfig, ReplaySpeed  # noqa: E402

USER_ID = os.environ.get("DIAG_USER_ID", "")


async def main() -> None:
    for key in ("macd_cross", "trend_rider"):
        config = BacktestConfig(
            strategy_type=key,
            symbol="NSE:NIFTY50-INDEX",
            exchange="NSE",
            interval="1d",
            days=730,
            initial_capital=1_000_000.0,
            speed=ReplaySpeed.MAX,
            user_id=USER_ID or None,
            risk_enabled=True,
        )
        result = await backtest_manager.run(config)

        print(f"\n  === {key} ===")
        print(f"  status          : {result.status}")
        print(f"  trades          : {result.total_trades}")
        print(f"  candles         : {len(result.equity_curve)}")

        ra = getattr(result, "risk_analytics", None)
        if ra is None:
            print("  risk_analytics  : absent")
            continue

        print(f"  risk enabled    : {getattr(ra, 'enabled', '?')}")
        print(f"  accepted orders : {getattr(ra, 'accepted_orders', getattr(ra, 'accepted', '?'))}")
        print(f"  rejected orders : {getattr(ra, 'rejected_orders', getattr(ra, 'rejected', '?'))}")

        rej = getattr(ra, "rejections", []) or []
        if rej:
            print(f"  rejection reasons ({len(rej)}):")
            for reason, n in Counter(getattr(r, "reason", "?") for r in rej).most_common(8):
                print(f"    {n:>5}  {reason}")
            print("  first 3 rejections in full:")
            for r in rej[:3]:
                print(
                    f"    rule={getattr(r, 'rule', '?')} | reason={getattr(r, 'reason', '?')}"
                    f" | capital_remaining={getattr(r, 'capital_remaining', '?')}"
                )
        else:
            print("  rejections      : none recorded")


if __name__ == "__main__":
    asyncio.run(main())
