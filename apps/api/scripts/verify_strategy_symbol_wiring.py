"""Does the strategy trade the symbol the user asked to backtest?

`run-v2` passes the requested symbol as `BacktestConfig.symbol` and separately passes the
user's form fields as `strategy_params`. Every strategy reads its symbol with
`config.get("symbol", ...)` — where `config` is `strategy_params`. So the symbol the run was
asked for never reaches the strategy, and it falls back to its own default.

If that is what happens, the order carries the fallback symbol while the candles carry the
requested one, which explains all three reported symptoms at once: no `entry_time`/`exit_time`
(`_last_times` is keyed by the order's symbol), a nonsensical entry price, and an implausible
P&L — there is no candle at the symbol being traded.

This asserts the wiring directly rather than inferring it from a backtest's output.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.models import BacktestConfig  # noqa: E402
from strategies import get_strategy  # noqa: E402

REQUESTED = "NSE:NIFTY50-INDEX"

KEYS = ("trend_rider", "macd_cross", "bollinger_bandit", "rsi_mean_reversion", "smc_sniper", "orb_pro")


def main() -> None:
    # Exactly what the route builds when a user submits the form with no strategy params.
    config = BacktestConfig(
        strategy_type="trend_rider",
        strategy_params={},
        symbol=REQUESTED,
        exchange="NSE",
        interval="1d",
        days=365,
    )

    print(f"  BacktestConfig.symbol        : {config.symbol}")
    print(f"  BacktestConfig.strategy_params: {config.strategy_params}")
    print()
    print(f"  {'strategy':<24}{'config.symbol':<20}{'strategy.symbol':<20}{'order symbol would be'}")
    print("  " + "-" * 92)

    mismatched = []
    for key in KEYS:
        strat = get_strategy(key)(config.strategy_params)
        actual = strat.symbol
        flag = "" if actual == config.symbol else "  <-- MISMATCH"
        if actual != config.symbol:
            mismatched.append((key, config.symbol, actual))
        print(f"  {key:<24}{config.symbol:<20}{actual:<20}{actual}{flag}")

    print()
    if mismatched:
        print(f"  {len(mismatched)} of {len(KEYS)} strategies trade a symbol the run was not asked for.")
        print("  The candles are loaded for config.symbol; the order is placed for strategy.symbol.")
        print("  Those keys never meet, so:")
        print("    - _last_times[strategy.symbol] is never populated -> entry_time/exit_time empty")
        print("    - the fill engine has no candle at strategy.symbol -> price is not the traded series")
    else:
        print("  every strategy honours config.symbol")


if __name__ == "__main__":
    main()
