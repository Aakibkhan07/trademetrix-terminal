from datetime import datetime, timedelta, timezone

from core.constants import LOT_SIZES
from core.models import (
    Candle,
    Exchange,
    NormalizedOrder,
    OrderSide,
    OrderType,
    ProductType,
    Tick,
)
from strategies.base import BaseStrategy, SignalResult

IST = timezone(timedelta(hours=5, minutes=30))


class ORBPro(BaseStrategy):
    name = "orb_pro"
    description = "Opening Range Breakout — trades breakouts from the first 15-min range"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.symbol = config.get("symbol", "BANKNIFTY")
        self.quantity = config.get("quantity", LOT_SIZES.get(self.symbol, 25))
        self.range_minutes = config.get("range_minutes", 15)
        self.breakout_buffer = config.get("breakout_buffer", 0.001)
        self._range_high: float = 0.0
        self._range_low: float = 0.0
        self._range_set = False
        self._range_start: datetime | None = None
        self._entry_done = False

    async def on_start(self) -> None:
        self._range_high = 0.0
        self._range_low = 0.0
        self._range_set = False
        self._range_start = None
        self._entry_done = False

    async def on_stop(self) -> None:
        pass

    async def on_tick(self, tick: Tick) -> SignalResult | None:
        return None

    async def on_candle(self, candle: Candle) -> SignalResult | None:
        if self._entry_done:
            return None

        now = candle.timestamp or datetime.now(IST)

        if not self._range_set:
            market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
            range_end = market_open.replace(minute=market_open.minute + self.range_minutes)

            if market_open <= now <= range_end:
                if self._range_high == 0 or candle.high > self._range_high:
                    self._range_high = candle.high
                if self._range_low == 0 or candle.low < self._range_low:
                    self._range_low = candle.low
                return None

            if now > range_end and self._range_high > 0:
                self._range_set = True
                return None

            return None

        side = None
        reason = ""

        if candle.close > self._range_high * (1 + self.breakout_buffer):
            side = OrderSide.BUY
            reason = f"ORB breakout above range high {self._range_high:.2f}"
        elif candle.close < self._range_low * (1 - self.breakout_buffer):
            side = OrderSide.SELL
            reason = f"ORB breakdown below range low {self._range_low:.2f}"

        if side:
            self._entry_done = True
            order = NormalizedOrder(
                symbol=self.symbol,
                exchange=Exchange.NSE,
                side=side,
                order_type=OrderType.MARKET,
                product=ProductType.INTRADAY,
                quantity=self.quantity,
                strategy_id=self.config.get("strategy_id"),
            )
            return SignalResult(orders=[order], reason=reason)

        return None
