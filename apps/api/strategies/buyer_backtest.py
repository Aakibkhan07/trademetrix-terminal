"""Backtest runner for options-buying strategies.

Feeds historical candles to a BuyerBase strategy instance in backtest_mode,
collects trades, equity curve, and performance metrics.
"""

import logging

from core.models import Candle
from strategies import get_strategy
from strategies.buyer_base import BuyerBase

logger = logging.getLogger(__name__)


class BuyerBacktestEngine:
    def __init__(self, strategy_key: str, config: dict, initial_capital: float = 100000.0):
        config = {**config, "backtest_mode": True, "backtest_initial_capital": initial_capital}
        cls = get_strategy(strategy_key)
        if not cls:
            raise ValueError(f"Unknown strategy: {strategy_key}")
        self.instance: BuyerBase = cls(config)
        self.initial_capital = initial_capital
        self.candles_analyzed = 0

    async def run(self, candles: list[dict | Candle]) -> dict:
        parsed = []
        for c in candles:
            if isinstance(c, Candle):
                parsed.append(c)
            elif isinstance(c, dict):
                parsed.append(Candle(**c))
            else:
                raise TypeError(f"Unsupported candle type: {type(c)}")

        await self.instance.on_start()
        self.candles_analyzed = len(parsed)

        for i, candle in enumerate(parsed):
            try:
                await self.instance.on_candle(candle)
            except Exception as e:
                logger.error("Backtest candle %d error: %s", i, e)

            ts = candle.timestamp.isoformat() if hasattr(candle.timestamp, "isoformat") else str(candle.timestamp)
            self.instance._record_backtest_equity(ts)

        await self.instance.on_stop()
        results = self.instance.get_backtest_results()

        return {
            "strategy_key": self.instance.name,
            "config": self.instance.config,
            "initial_capital": self.initial_capital,
            "final_capital": results["final_capital"],
            "total_pnl": results["total_pnl"],
            "return_pct": results["return_pct"],
            "total_trades": results["total_trades"],
            "winning_trades": results["winning_trades"],
            "losing_trades": results["losing_trades"],
            "win_rate": results["win_rate"],
            "candles_analyzed": self.candles_analyzed,
            "trades": results["trades"],
            "equity_curve": results["equity"],
        }
