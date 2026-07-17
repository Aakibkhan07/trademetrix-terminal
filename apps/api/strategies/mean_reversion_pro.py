from core.constants import LOT_SIZES
from core.models import (
    Candle, Exchange, NormalizedOrder, OrderSide, OrderType, ProductType, Tick,
)
from strategies.base import BaseStrategy, SignalResult
from strategies.indicators import sma, atr


class MeanReversionPro(BaseStrategy):
    name = "mean_reversion_pro"
    description = "Multi-indicator mean reversion using Bollinger-Keltner confluence zones"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.symbol = config.get("symbol", "NIFTY")
        self.quantity = config.get("quantity", LOT_SIZES.get(self.symbol, 75))
        self.bb_period = config.get("bb_period", 20)
        self.bb_std = config.get("bb_std", 2.0)
        self._prices: list[float] = []

    async def on_start(self) -> None:
        self._prices.clear()

    async def on_stop(self) -> None:
        pass

    async def on_tick(self, tick: Tick) -> SignalResult | None:
        return None

    async def on_candle(self, candle: Candle) -> SignalResult | None:
        self._prices.append(candle.close)
        if len(self._prices) > 100:
            self._prices.pop(0)
        if len(self._prices) < self.bb_period:
            return None

        basis = sma(self._prices, self.bb_period)
        std = self._std(self._prices[-self.bb_period:])
        upper = basis + self.bb_std * std
        lower = basis - self.bb_std * std
        price = candle.close
        atr_val = atr([candle], 1) or 0.0

        side = None
        reason = ""

        if price <= lower and price > lower - atr_val:
            side = OrderSide.BUY
            reason = f"Price {price:.1f} at lower BB {lower:.1f} - mean reversion buy"
        elif price >= upper and price < upper + atr_val:
            side = OrderSide.SELL
            reason = f"Price {price:.1f} at upper BB {upper:.1f} - mean reversion sell"

        if side:
            order = NormalizedOrder(
                symbol=self.symbol,
                exchange=Exchange.NSE,
                side=side,
                order_type=OrderType.LIMIT,
                product=ProductType.INTRADAY,
                quantity=self.quantity,
                price=price,
                strategy_id=self.config.get("strategy_id"),
            )
            return SignalResult(orders=[order], reason=reason)

        return None

    @staticmethod
    def _std(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return variance ** 0.5
