"""Does the strategy trade the symbol the run was actually requested for?

`BacktestConfig.symbol` and `BacktestConfig.strategy_params` are two different
fields. Strategies read their symbol with `config.get("symbol", <default>)` from
their own params dict, so unless the run's symbol is merged into that dict the
strategy trades its default (`NIFTY`, or `BANKNIFTY` for orb_pro) while the fill
engine holds candles for the requested instrument.

This exercises the real `BacktestManager._setup_strategy` rather than
constructing strategies directly, because the wiring under test lives in the
manager, not in the strategy classes.

    python scripts/verify_strategy_symbol_wiring.py

Exits non-zero if any strategy trades a symbol the run was not asked for.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.manager import backtest_manager  # noqa: E402
from backtest.models import BacktestConfig  # noqa: E402

# Index and derivative display symbols as the app actually carries them, plus an
# equity and an option contract, so the check covers the instrument families the
# backtest surface accepts rather than one index.
CASES = [
    ("trend_rider", "NSE:NIFTY50-INDEX"),
    ("macd_cross", "NSE:NIFTY50-INDEX"),
    ("orb_pro", "NSE:NIFTY50-INDEX"),
    ("bollinger_bandit", "NSE:BANKNIFTY-INDEX"),
    ("rsi_mean_reversion", "NSE:BANKNIFTY-INDEX"),
    ("smc_sniper", "NSE:NIFTY50-INDEX"),
    ("intraday_momentum", "NSE:RELIANCE-EQ"),
    ("mean_reversion_pro", "NSE:FINNIFTY-INDEX"),
    ("breakout_scanner", "NSE:SENSEX-INDEX"),
    ("arbitrage_hunter", "NSE:NIFTY50-INDEX"),
]


async def main() -> int:
    print(f"  {'strategy':<24}{'requested':<26}{'strategy.symbol':<26}{'quantity'}")
    print("  " + "-" * 88)

    mismatched: list[tuple[str, str, str]] = []

    for key, requested in CASES:
        # Exactly what run-v2 builds when a user submits the form with no strategy
        # params — the normal case, and the one that used to break.
        config = BacktestConfig(
            strategy_type=key,
            strategy_params={},
            symbol=requested,
            exchange="NSE",
            interval="1d",
            days=365,
        )
        strategy = await backtest_manager._setup_strategy(config)
        actual = strategy.symbol

        if actual != requested:
            mismatched.append((key, requested, actual))

        flag = "" if actual == requested else "   <-- MISMATCH"
        print(f"  {key:<24}{requested:<26}{actual:<26}{strategy.quantity}{flag}")

    print()
    total = len(CASES)
    if mismatched:
        print(f"  FAIL — {len(mismatched)} of {total} trade a symbol the run was not asked for.")
        return 1

    print(f"  PASS — all {total} strategies trade the requested symbol.")
    print("  The strategy's default is no longer reachable while config.symbol is set,")
    print("  so _last_times is populated for the symbol being traded and the fill")
    print("  engine prices against the series that was actually loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))