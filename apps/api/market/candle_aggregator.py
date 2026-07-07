"""Shared CandleAggregator — ticks to OHLCV candles."""

from datetime import UTC, datetime
from core.models import Candle, Exchange, Tick

CANDLE_INTERVAL_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "60m": 3600}


class CandleAggregator:
    def __init__(self, symbol: str, interval: str):
        self.symbol = symbol
        self.interval_seconds = CANDLE_INTERVAL_SECONDS.get(interval, 900)
        self.open = 0.0
        self.high = 0.0
        self.low = float("inf")
        self.close = 0.0
        self.volume = 0
        self.oi = 0
        self._period_start = 0
        self._count = 0

    def add_tick(self, tick: Tick) -> Candle | None:
        ts = tick.timestamp.timestamp() if isinstance(tick.timestamp, datetime) else tick.timestamp
        period = int(ts / self.interval_seconds) * self.interval_seconds

        if self._period_start == 0:
            self._period_start = period
            self.open = tick.last_price

        if period != self._period_start:
            candle = self._build_candle(ts)
            self._period_start = period
            self.open = tick.last_price
            self.high = tick.last_price
            self.low = tick.last_price
            self.close = tick.last_price
            self.volume = tick.volume
            self.oi = tick.oi
            self._count = 1
            return candle

        self.high = max(self.high, tick.last_price)
        self.low = min(self.low, tick.last_price)
        self.close = tick.last_price
        self.volume += tick.volume
        if tick.oi:
            self.oi = tick.oi
        self._count += 1
        return None

    def _build_candle(self, ts_now: float) -> Candle:
        return Candle(
            symbol=self.symbol,
            exchange=Exchange.NSE,
            interval=f"{self.interval_seconds // 60}m" if self.interval_seconds >= 60 else f"{self.interval_seconds}s",
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=float(self.volume),
            timestamp=datetime.fromtimestamp(self._period_start, tz=UTC).isoformat(),
            oi=float(self.oi),
        )
