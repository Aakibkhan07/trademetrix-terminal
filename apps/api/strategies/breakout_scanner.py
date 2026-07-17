from core.constants import LOT_SIZES
from core.models import (
    Candle, Exchange, NormalizedOrder, OrderSide, OrderType, ProductType, Tick,
)
from strategies.base import BaseStrategy, SignalResult
from strategies.indicators import sma, atr


class BreakoutScanner(BaseStrategy):
    name = "breakout_scanner"
    description = "Detects consolidation breakouts with ATR-based volatility expansion and volume confirmation"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.symbol = config.get("symbol", "NIFTY")
        self.quantity = config.get("quantity", LOT_SIZES.get(self.symbol, 75))
        self.lookback = config.get("lookback", 20)
        self.atr_mult = config.get("atr_mult", 2.0)
        self._candles: list[Candle] = []

    async def on_start(self) -> None:
        self._candles.clear()

    async def on_stop(self) -> None:
        pass

    async def on_tick(self, tick: Tick) -> SignalResult | None:
        return None

    async def on_candle(self, candle: Candle) -> SignalResult | None:
        self._candles.append(candle)
        if len(self._candles) > 100:
            self._candles.pop(0)
        if len(self._candles) < self.lookback + 2:
            return None

        atr_val = atr(self._candles, 14)
        if atr_val <= 0:
            return None

        recent = self._candles[-self.lookback:-1]
        high_range = max(c.high for c in recent)
        low_range = min(c.low for c in recent)
        range_pct = (high_range - low_range) / low_range * 100
        price = candle.close

        if range_pct > 5:
            return None

        avg_vol = sma([c.volume for c in self._candles[-self.lookback:-1]], self.lookback)
        vol_surge = avg_vol > 0 and candle.volume > avg_vol * 1.5
        range_width = high_range - low_range

        if price > high_range + atr_val * 0.5 and vol_surge:
            order = NormalizedOrder(
                symbol=self.symbol, exchange=Exchange.NSE, side=OrderSide.BUY,
                order_type=OrderType.MARKET, product=ProductType.INTRADAY,
                quantity=self.quantity, strategy_id=self.config.get("strategy_id"),
            )
            return SignalResult(orders=[order], reason=f"Bullish breakout above {high_range:.1f} resistance, vol {candle.volume:.0f} vs avg {avg_vol:.0f}")

        if price < low_range - atr_val * 0.5 and vol_surge:
            order = NormalizedOrder(
                symbol=self.symbol, exchange=Exchange.NSE, side=OrderSide.SELL,
                order_type=OrderType.MARKET, product=ProductType.INTRADAY,
                quantity=self.quantity, strategy_id=self.config.get("strategy_id"),
            )
            return SignalResult(orders=[order], reason=f"Bearish breakdown below {low_range:.1f} support, vol {candle.volume:.0f} vs avg {avg_vol:.0f}")

        return None
