from core.constants import LOT_SIZES
from core.models import (
    Candle, Exchange, NormalizedOrder, OrderSide, OrderType, ProductType, Tick,
)
from strategies.base import BaseStrategy, SignalResult
from strategies.indicators import sma


class GapUpExpress(BaseStrategy):
    name = "gap_up_express"
    description = "Captures opening gap momentum with pre-market volume spike confirmation"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.symbol = config.get("symbol", "BANKNIFTY")
        self.quantity = config.get("quantity", LOT_SIZES.get(self.symbol, 40))
        self.gap_pct = config.get("gap_pct", 0.3)
        self.volume_threshold = config.get("volume_threshold", 1.5)
        self.prev_close: float | None = None
        self._prices: list[float] = []
        self._volumes: list[float] = []

    async def on_start(self) -> None:
        self._prices.clear()
        self._volumes.clear()
        self.prev_close = None

    async def on_stop(self) -> None:
        pass

    async def on_tick(self, tick: Tick) -> SignalResult | None:
        if not tick.last_price or not tick.volume:
            return None
        if self.prev_close is None:
            return None

        gap = (tick.last_price - self.prev_close) / self.prev_close * 100
        avg_vol = sma(self._volumes, 20) if len(self._volumes) >= 20 else 0
        vol_spike = avg_vol > 0 and tick.volume > avg_vol * self.volume_threshold

        if gap > self.gap_pct and vol_spike:
            order = NormalizedOrder(
                symbol=self.symbol,
                exchange=Exchange.NSE,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                product=ProductType.INTRADAY,
                quantity=self.quantity,
                strategy_id=self.config.get("strategy_id"),
            )
            return SignalResult(orders=[order], reason=f"Gap up {gap:.1f}% with volume spike {tick.volume:.0f} vs avg {avg_vol:.0f}")

        if gap < -self.gap_pct and vol_spike:
            order = NormalizedOrder(
                symbol=self.symbol,
                exchange=Exchange.NSE,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                product=ProductType.INTRADAY,
                quantity=self.quantity,
                strategy_id=self.config.get("strategy_id"),
            )
            return SignalResult(orders=[order], reason=f"Gap down {gap:.1f}% with volume spike {tick.volume:.0f} vs avg {avg_vol:.0f}")

        return None

    async def on_candle(self, candle: Candle) -> SignalResult | None:
        self._prices.append(candle.close)
        self._volumes.append(candle.volume)
        if len(self._prices) > 100:
            self._prices.pop(0)
            self._volumes.pop(0)
        if self.prev_close is None and len(self._prices) >= 2:
            self.prev_close = self._prices[-2]
        return None
