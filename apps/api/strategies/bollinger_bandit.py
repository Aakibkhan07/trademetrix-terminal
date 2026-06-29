import math

from core.constants import LOT_SIZES
from core.models import (
    Candle, Exchange, NormalizedOrder, OrderSide, OrderType, ProductType, Tick,
)
from strategies.base import BaseStrategy, SignalResult


class BollingerBandit(BaseStrategy):
    name = "bollinger_bandit"
    description = "Bollinger Bands mean reversion - fades touches of outer bands"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.symbol = config.get("symbol", "NIFTY")
        self.quantity = config.get("quantity", LOT_SIZES.get(self.symbol, 75))
        self.period = config.get("period", 20)
        self.std_dev = config.get("std_dev", 2.0)
        self._prices: list[float] = []

    async def on_start(self) -> None:
        self._prices.clear()

    async def on_stop(self) -> None:
        pass

    async def on_tick(self, tick: Tick) -> SignalResult | None:
        return None

    async def on_candle(self, candle: Candle) -> SignalResult | None:
        self._prices.append(candle.close)
        if len(self._prices) < self.period + 1:
            return None

        sma = self._sma(self._prices, self.period)
        std = self._std(self._prices, self.period)
        upper = sma + self.std_dev * std
        lower = sma - self.std_dev * std
        prev_close = self._prices[-2]
        curr_close = self._prices[-1]

        side = None
        reason = ""

        if prev_close <= lower and curr_close > lower:
            side = OrderSide.BUY
            reason = f"Price bounced off lower band at {lower:.1f}"
        elif prev_close >= upper and curr_close < upper:
            side = OrderSide.SELL
            reason = f"Price rejected off upper band at {upper:.1f}"

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
    def _sma(prices: list[float], period: int) -> float:
        return sum(prices[-period:]) / period

    @staticmethod
    def _std(prices: list[float], period: int) -> float:
        mean = sum(prices[-period:]) / period
        variance = sum((p - mean) ** 2 for p in prices[-period:]) / period
        return math.sqrt(variance)
