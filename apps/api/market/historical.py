import logging
from typing import Any

from core.models import Candle
from market.cache import market_cache

logger = logging.getLogger(__name__)


class HistoricalDataEngine:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

    async def get_historical(
        self,
        symbol: str,
        exchange: str = "NSE",
        interval: str = "15m",
        days: int = 7,
        user_id: str | None = None,
    ) -> list[dict]:
        cache_key = f"historical:{symbol}:{exchange}:{interval}:{days}"
        ttl = self._interval_ttl(interval)
        cached = market_cache.get_quote(cache_key)
        if cached:
            return cached.get("candles", [])

        candles = await self._fetch_from_broker(symbol, exchange, interval, days, user_id)
        if not candles:
            candles = self._synthesize(symbol, days, interval)

        market_cache.put_quote(cache_key, {"candles": candles})
        return candles

    async def get_supported_intervals(self, broker: str = "") -> list[str]:
        base = ["1m", "5m", "15m", "30m", "60m", "1d"]
        if broker == "fyers":
            return base + ["2m", "3m", "10m", "20m", "120m", "180m", "240m", "360m", "480m", "720m", "960m"]
        return base

    async def _fetch_from_broker(
        self, symbol: str, exchange: str, interval: str, days: int, user_id: str | None
    ) -> list[dict]:
        if not user_id:
            return []
        from core.db import async_supabase, get_supabase
        from core.security import decrypt_broker_credentials

        import time

        try:
            supabase = get_supabase()
            cred = await async_supabase(lambda: supabase.table("broker_credentials").select("*").eq("user_id", user_id).eq("broker", "fyers").single().execute())
            if not cred.data:
                return []

            row = cred.data
            client_id = decrypt_broker_credentials(row["encrypted_api_key"])
            raw_token = decrypt_broker_credentials(row["encrypted_access_token"])
            if not raw_token:
                return []

            fyers_symbol = self._map_symbol(symbol, exchange)
            fyers_interval = self._map_interval(interval)

            now = int(time.time())
            start_ts = str(now - days * 86400)

            from brokers.fyers_adapter import FyersAdapter

            adapter = FyersAdapter()
            await adapter.authenticate({"client_id": client_id, "access_token": raw_token})
            candles = await adapter.get_historical(fyers_symbol, fyers_interval, start_ts, str(now))
            if candles:
                logger.info("Fetched %d candles from Fyers for %s", len(candles), fyers_symbol)
                return [self._candle_to_dict(c) for c in candles]
        except Exception as e:
            logger.warning("Broker historical fetch failed: %s", e)
        return []

    def _synthesize(self, symbol: str, days: int, interval: str) -> list[dict]:
        import random
        from datetime import UTC, datetime, timedelta

        candles = []
        base_price = random.uniform(500, 5000)
        now = datetime.now(UTC)
        interval_min = self._parse_interval_minutes(interval)
        total = days * 24 * 60 // interval_min
        price = base_price
        for i in range(total):
            ts = now - timedelta(minutes=(total - i) * interval_min)
            change = price * random.uniform(-0.015, 0.015)
            o = price
            h = o + abs(change) * random.uniform(0.5, 1.5)
            low = o - abs(change) * random.uniform(0.5, 1.5)
            c = o + change
            price = c
            candles.append({
                "symbol": symbol,
                "exchange": "NSE",
                "interval": interval,
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(low, 2),
                "close": round(c, 2),
                "volume": random.randint(10000, 500000),
                "timestamp": ts.isoformat(),
                "oi": random.randint(100000, 5000000),
            })
        return candles

    def _interval_ttl(self, interval: str) -> int:
        mins = self._parse_interval_minutes(interval)
        if mins <= 1:
            return 60
        if mins <= 5:
            return 300
        if mins <= 60:
            return 600
        return 3600

    def _parse_interval_minutes(self, interval: str) -> int:
        interval = interval.lower().strip()
        if interval.endswith("min"):
            return int(interval.replace("min", ""))
        if interval.endswith("h"):
            return int(interval.replace("h", "")) * 60
        if interval.endswith("d"):
            return int(interval.replace("d", "")) * 1440
        if interval.endswith("m"):
            return int(interval.replace("m", ""))
        try:
            return int(interval)
        except ValueError:
            return 15

    def _map_symbol(self, symbol: str, exchange: str) -> str:
        mapping = {
            "NIFTY": "NSE:NIFTY50-INDEX",
            "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
            "FINNIFTY": "NSE:FINNIFTY-INDEX",
            "SENSEX": "BSE:SENSEX-INDEX",
        }
        if symbol.upper() in mapping:
            return mapping[symbol.upper()]
        if ":" in symbol:
            return symbol
        return f"{exchange}:{symbol}"

    def _map_interval(self, interval: str) -> str:
        mins = self._parse_interval_minutes(interval)
        fyers_map = {
            1: "1", 2: "2", 3: "3", 5: "5", 10: "10", 15: "15", 20: "20",
            30: "30", 60: "60", 120: "120", 180: "180", 240: "240",
            360: "360", 480: "480", 720: "720", 960: "960", 1440: "D",
        }
        return fyers_map.get(mins, "15")

    def _candle_to_dict(self, c: Candle) -> dict:
        return {
            "symbol": c.symbol,
            "exchange": c.exchange.value if hasattr(c.exchange, "value") else str(c.exchange),
            "interval": c.interval,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "timestamp": c.timestamp.isoformat() if hasattr(c.timestamp, "isoformat") else str(c.timestamp),
            "oi": c.oi,
        }


historical_engine = HistoricalDataEngine()
