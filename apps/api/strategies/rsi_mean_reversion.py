
from core.constants import LOT_SIZES
from core.models import (
    Candle, Exchange, NormalizedOrder, OrderSide, OrderType, ProductType, Tick,
)
from strategies.base import BaseStrategy, SignalResult


class RSIMeanReversion(BaseStrategy):
    name = "rsi_mean_reversion"
    description = "RSI-based mean reversion - buys oversold, sells overbought"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.symbol = config.get("symbol", "NIFTY")
        self.quantity = config.get("quantity", LOT_SIZES.get(self.symbol, 75))
        self.period = config.get("period", 14)
        self.oversold = config.get("oversold", 30)
        self.overbought = config.get("overbought", 70)
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

        rsi = self._rsi(self._prices, self.period)
        prev_rsi = self._rsi(self._prices[:-1], self.period)

        side = None
        reason = ""

        if prev_rsi <= self.oversold and rsi > self.oversold:
            side = OrderSide.BUY
            reason = f"RSI oversold bounce: {prev_rsi:.1f} -> {rsi:.1f}"
        elif prev_rsi >= self.overbought and rsi < self.overbought:
            side = OrderSide.SELL
            reason = f"RSI overbought reversal: {prev_rsi:.1f} -> {rsi:.1f}"

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

    def _rsi(self, prices: list[float], period: int) -> float:
        if len(prices) < period + 1:
            return 50.0
        gains, losses = 0.0, 0.0
        for i in range(-period, 0):
            change = prices[i] - prices[i - 1]
            if change >= 0:
                gains += change
            else:
                losses -= change
        avg_gain = gains / period
        avg_loss = losses / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
