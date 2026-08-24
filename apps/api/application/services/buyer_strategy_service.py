import logging
from datetime import datetime
from typing import cast

from engine.backtest import fetch_historical_data
from engine.buyer_strategy_runner import BUYER_KEYS, buyer_strategy_runner
from strategies import get_strategy
from strategies.buyer_backtest import BuyerBacktestEngine

logger = logging.getLogger(__name__)


class BuyerStrategyService:
    async def activate(
        self,
        user_id: str,
        strategy_id: str,
        strategy_key: str,
        index: str,
        config: dict,
    ) -> dict:
        from core.capabilities import resolve_capabilities_by_id

        if strategy_key not in BUYER_KEYS:
            raise ValueError(f"Unknown buyer strategy: {strategy_key}")
        try:
            get_strategy(strategy_key)
        except ValueError:
            raise ValueError(f"Strategy class not found: {strategy_key}")

        if index not in ("NIFTY", "SENSEX"):
            raise ValueError("index must be NIFTY or SENSEX")

        caps = await resolve_capabilities_by_id(user_id)
        statuses = await buyer_strategy_runner.get_statuses()
        user_active = sum(
            1 for s in (statuses if isinstance(statuses, list) else statuses.values())
            if s.get("user_id") == user_id and s.get("status") == "RUNNING"
        )
        if user_active >= caps.max_active_strategies:
            raise ValueError(
                f"Your plan allows a maximum of {caps.max_active_strategies} active strategies."
            )

        merged_config = {
            "strategy_id": strategy_id,
            "user_id": user_id,
            "index": index,
            "strategy_key": strategy_key,
            **config,
        }
        success = await buyer_strategy_runner.activate(strategy_id, merged_config, index)
        if not success:
            raise RuntimeError("Failed to activate strategy")
        return {"message": "Strategy activated", "strategy_id": strategy_id}

    async def deactivate(self, strategy_id: str) -> dict:
        success = await buyer_strategy_runner.deactivate(strategy_id)
        if not success:
            raise ValueError("Strategy not found or already inactive")
        return {"message": "Strategy deactivated"}

    async def status(self) -> dict:
        statuses = await buyer_strategy_runner.get_statuses()
        return {"strategies": statuses}

    async def backtest(
        self,
        user_id: str,
        strategy_key: str,
        symbol: str,
        exchange: str,
        interval: str,
        days: int,
        initial_capital: float,
        config: dict,
    ) -> dict:
        if strategy_key not in BUYER_KEYS:
            raise ValueError(f"Unknown buyer strategy: {strategy_key}")
        try:
            get_strategy(strategy_key)
        except ValueError:
            raise ValueError(f"Strategy class not found: {strategy_key}")

        merged_config = {
            "strategy_id": f"bt_{strategy_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "user_id": user_id,
            "index": symbol,
            "capital": initial_capital,
            **config,
        }

        try:
            candles = await fetch_historical_data(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                days=days,
                user_id=user_id,
            )
        except ValueError:
            # Real-data honesty contract (v1.7.0): never backtest on fabricated
            # candles — surface the data gap to the caller (route → 400).
            raise
        except Exception as e:
            raise ValueError(f"No real market data available for {symbol}: {e}") from e

        if not candles:
            raise ValueError(f"No real market data available for {symbol} ({interval}, {days}d)")

        engine = BuyerBacktestEngine(strategy_key, merged_config, initial_capital)
        results = await engine.run(cast(list, candles))

        return {
            "symbol": symbol,
            "strategy": strategy_key,
            "interval": interval,
            "days": days,
            **results,
        }

    @staticmethod
    def _parse_interval_minutes(interval: str) -> int:
        interval = interval.lower().strip()
        try:
            if interval.endswith("min"):
                return int(interval.replace("min", ""))
            if interval.endswith("h"):
                return int(interval.replace("h", "")) * 60
            if interval.endswith("d"):
                return int(interval.replace("d", "")) * 1440
            if interval.endswith("m"):
                return int(interval.replace("m", ""))
            return int(interval)
        except (ValueError, AttributeError):
            return 5
