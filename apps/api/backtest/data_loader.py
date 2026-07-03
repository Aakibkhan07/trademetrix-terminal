import csv
import json
import logging
import os
from datetime import datetime
from typing import Any

from core.models import Candle, Exchange
from market.historical import historical_engine

logger = logging.getLogger(__name__)


class BacktestDataLoader:
    def __init__(self):
        self._cache: dict[str, list[dict]] = {}

    async def load(
        self,
        symbol: str,
        exchange: str = "NSE",
        interval: str = "15m",
        days: int = 60,
        user_id: str | None = None,
        source: str = "auto",
        file_path: str = "",
    ) -> list[dict]:
        cache_key = f"{symbol}:{exchange}:{interval}:{days}:{source}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if source == "csv" and file_path:
            candles = self._load_csv(file_path, symbol, exchange, interval)
        elif source == "json" and file_path:
            candles = self._load_json(file_path, symbol, exchange, interval)
        elif source == "parquet" and file_path:
            candles = self._load_parquet(file_path, symbol, exchange, interval)
        else:
            candles = await historical_engine.get_historical(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                days=days,
                user_id=user_id,
            )

        candles.sort(key=lambda c: c.get("timestamp", ""))
        self._cache[cache_key] = candles
        logger.info("Loaded %d candles for %s %s", len(candles), symbol, interval)
        return candles

    def _load_csv(self, file_path: str, symbol: str, exchange: str, interval: str) -> list[dict]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"CSV file not found: {file_path}")
        candles = []
        with open(file_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                candles.append(self._normalize_row(row, symbol, exchange, interval))
        logger.info("Loaded %d candles from CSV: %s", len(candles), file_path)
        return candles

    def _load_json(self, file_path: str, symbol: str, exchange: str, interval: str) -> list[dict]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"JSON file not found: {file_path}")
        with open(file_path, "r") as f:
            data = json.load(f)
        raw_candles = data if isinstance(data, list) else data.get("candles", [])
        candles = []
        for row in raw_candles:
            candles.append(self._normalize_row(row, symbol, exchange, interval))
        logger.info("Loaded %d candles from JSON: %s", len(candles), file_path)
        return candles

    def _load_parquet(self, file_path: str, symbol: str, exchange: str, interval: str) -> list[dict]:
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas is required to load parquet files. Install with: pip install pandas")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Parquet file not found: {file_path}")
        df = pd.read_parquet(file_path)
        candles = []
        for _, row in df.iterrows():
            candles.append(self._normalize_row(row.to_dict(), symbol, exchange, interval))
        logger.info("Loaded %d candles from Parquet: %s", len(candles), file_path)
        return candles

    def _normalize_row(self, row: dict, symbol: str, exchange: str, interval: str) -> dict:
        ts = row.get("timestamp") or row.get("date") or row.get("time") or ""
        if isinstance(ts, datetime):
            ts = ts.isoformat()
        elif hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        else:
            ts = str(ts)

        return {
            "symbol": row.get("symbol", symbol),
            "exchange": row.get("exchange", exchange),
            "interval": row.get("interval", interval),
            "open": float(row.get("open", 0)),
            "high": float(row.get("high", 0)),
            "low": float(row.get("low", 0)),
            "close": float(row.get("close", 0)),
            "volume": int(float(row.get("volume", 0))),
            "timestamp": ts,
            "oi": int(float(row.get("oi", 0))),
        }

    def to_candle(self, d: dict) -> Candle:
        exchange = d.get("exchange", "NSE")
        if isinstance(exchange, str):
            exchange = Exchange(exchange)
        ts = d.get("timestamp", "")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return Candle(
            symbol=d.get("symbol", ""),
            exchange=exchange,
            interval=d.get("interval", ""),
            open=float(d.get("open", 0)),
            high=float(d.get("high", 0)),
            low=float(d.get("low", 0)),
            close=float(d.get("close", 0)),
            volume=int(float(d.get("volume", 0))),
            timestamp=ts,
            oi=int(float(d.get("oi", 0))),
        )

    def invalidate_cache(self, key: str | None = None) -> None:
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()


backtest_data_loader = BacktestDataLoader()
