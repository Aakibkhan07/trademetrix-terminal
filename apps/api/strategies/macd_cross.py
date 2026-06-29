
from core.constants import LOT_SIZES
from core.models import (
    Candle, Exchange, NormalizedOrder, OrderSide, OrderType, ProductType, Tick,
)
from strategies.base import BaseStrategy, SignalResult


class MACDCross(BaseStrategy):
    name = "macd_cross"
    description = "MACD line / signal line crossover strategy"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.symbol = config.get("symbol", "NIFTY")
        self.quantity = config.get("quantity", LOT_SIZES.get(self.symbol, 75))
        self.fast = config.get("fast", 12)
        self.slow = config.get("slow", 26)
        self.signal = config.get("signal", 9)
        self._prices: list[float] = []

    async def on_start(self) -> None:
        self._prices.clear()

    async def on_stop(self) -> None:
        pass

    async def on_tick(self, tick: Tick) -> SignalResult | None:
        return None

    async def on_candle(self, candle: Candle) -> SignalResult | None:
        self._prices.append(candle.close)
        if len(self._prices) < self.slow + self.signal + 1:
            return None

        macd_line = self._ema(self._prices, self.fast) - self._ema(self._prices, self.slow)
        signal_line = self._ema(self._prices, self.signal)

        prev_macd = self._ema(self._prices[:-1], self.fast) - self._ema(self._prices[:-1], self.slow)
        prev_signal = self._ema(self._prices[:-1], self.signal)

        side = None
        reason = ""

        if prev_macd <= prev_signal and macd_line > signal_line:
            side = OrderSide.BUY
            reason = f"MACD bullish crossover: {macd_line:.1f} > {signal_line:.1f}"
        elif prev_macd >= prev_signal and macd_line < signal_line:
            side = OrderSide.SELL
            reason = f"MACD bearish crossover: {macd_line:.1f} < {signal_line:.1f}"

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
