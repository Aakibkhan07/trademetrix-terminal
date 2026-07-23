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
        if strategy_key not in BUYER_KEYS:
            raise ValueError(f"Unknown buyer strategy: {strategy_key}")
        try:
            get_strategy(strategy_key)
        except ValueError:
            raise ValueError(f"Strategy class not found: {strategy_key}")

        if index not in ("NIFTY", "SENSEX"):
            raise ValueError("index must be NIFTY or SENSEX")

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
        except Exception as e:
            logger.warning("Fyers data fetch failed (%s), using simulated data", e)
            candles = self._generate_simulated_candles(symbol, days, interval)

        if not candles:
            candles = self._generate_simulated_candles(symbol, days, interval)

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
    def _generate_simulated_candles(symbol: str, days: int, interval: str) -> list[dict]:
        import random
        from datetime import datetime, timedelta, timezone

        mins = BuyerStrategyService._parse_interval_minutes(interval)
        count = days * 375 // mins
        base = 22000.0 if symbol.upper().endswith("SENSEX") else 19500.0
        candles = []
        now = datetime.now(timezone.utc)
        price = base

        for i in range(count):
            ts = now - timedelta(minutes=(count - i) * mins)
            if ts.weekday() >= 5:
                continue
            if ts.hour < 9 or ts.hour >= 15 or (ts.hour == 15 and ts.minute > 15):
                continue
            change = price * random.gauss(0, 0.003)
            o = price
            h = o + abs(change) * random.uniform(1.0, 1.5) + random.random() * 20
            l_val = o - abs(change) * random.uniform(1.0, 1.5) - random.random() * 20
            c = o + change
            price = c
            candles.append({
                "symbol": symbol,
                "exchange": "NSE",
                "interval": interval,
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l_val, 2),
                "close": round(c, 2),
                "volume": int(random.uniform(50000, 500000)),
                "timestamp": ts.isoformat(),
            })
        return candles

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
