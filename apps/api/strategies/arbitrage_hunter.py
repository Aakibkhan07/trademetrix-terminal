from core.constants import LOT_SIZES
from core.models import (
    Candle, Exchange, NormalizedOrder, OrderSide, OrderType, ProductType, Tick,
)
from strategies.base import BaseStrategy, SignalResult
from strategies.indicators import sma


class ArbitrageHunter(BaseStrategy):
    name = "arbitrage_hunter"
    description = "Calendar spread arbitrage — trades mispricing between near and far expiry futures"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.symbol = config.get("symbol", "NIFTY")
        self.quantity = config.get("quantity", LOT_SIZES.get(self.symbol, 75))
        self.lookback = config.get("lookback", 30)
        self.entry_std = config.get("entry_std", 2.0)
        self._near_prices: list[float] = []

    async def on_start(self) -> None:
        self._near_prices.clear()

    async def on_stop(self) -> None:
        pass

    async def on_tick(self, tick: Tick) -> SignalResult | None:
        return None

    async def on_candle(self, candle: Candle) -> SignalResult | None:
        self._near_prices.append(candle.close)
        if len(self._near_prices) > 200:
            self._near_prices.pop(0)
        if len(self._near_prices) < self.lookback + 5:
            return None

        price = candle.close
        near_mean = sma(self._near_prices, self.lookback)
        near_std = self._std(self._near_prices[-self.lookback:])
        if near_std == 0:
            return None

        z = (price - near_mean) / near_std
        orders = []

        if z > self.entry_std:
            orders.append(NormalizedOrder(
                symbol=self.symbol, exchange=Exchange.NFO, side=OrderSide.SELL,
                order_type=OrderType.MARKET, product=ProductType.INTRADAY,
                quantity=self.quantity, strategy_id=self.config.get("strategy_id"),
            ))
            return SignalResult(orders=orders, reason=f"Calendar spread z={z:.2f}: short {self.symbol} futures at {price:.1f} (near mean {near_mean:.1f})")

        if z < -self.entry_std:
            orders.append(NormalizedOrder(
                symbol=self.symbol, exchange=Exchange.NFO, side=OrderSide.BUY,
                order_type=OrderType.MARKET, product=ProductType.INTRADAY,
                quantity=self.quantity, strategy_id=self.config.get("strategy_id"),
            ))
            return SignalResult(orders=orders, reason=f"Calendar spread z={z:.2f}: long {self.symbol} futures at {price:.1f} (near mean {near_mean:.1f})")

        return None

    @staticmethod
    def _std(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        return (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
