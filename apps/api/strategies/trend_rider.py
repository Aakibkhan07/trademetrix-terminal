
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


class TrendRider(BaseStrategy):
    name = "trend_rider"
    description = "Follows EMA crossover trends with momentum confirmation"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.fast_period = config.get("fast_period", 9)
        self.slow_period = config.get("slow_period", 21)
        self.symbol = config.get("symbol", "NIFTY")
        self.quantity = config.get("quantity", LOT_SIZES.get(self.symbol, 75))
        self._prices: list[float] = []

    async def on_start(self) -> None:
        self._prices.clear()

    async def on_stop(self) -> None:
        pass

    async def on_tick(self, tick: Tick) -> SignalResult | None:
        return None

    async def on_candle(self, candle: Candle) -> SignalResult | None:
        self._prices.append(candle.close)
        if len(self._prices) < self.slow_period + 1:
            return None

        fast_ema = self._ema(self._prices, self.fast_period)
        slow_ema = self._ema(self._prices, self.slow_period)
        prev_fast = self._ema(self._prices[:-1], self.fast_period)
        prev_slow = self._ema(self._prices[:-1], self.slow_period)

        side = None
        reason = ""

        if prev_fast <= prev_slow and fast_ema > slow_ema:
            side = OrderSide.BUY
            reason = f"Bullish crossover: EMA{self.fast_period} crossed above EMA{self.slow_period}"
        elif prev_fast >= prev_slow and fast_ema < slow_ema:
            side = OrderSide.SELL
            reason = f"Bearish crossover: EMA{self.fast_period} crossed below EMA{self.slow_period}"

        if side:
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

    @staticmethod
    def _ema(prices: list[float], period: int) -> float:
        if len(prices) < period:
            return prices[-1]
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        return ema
