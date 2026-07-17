from core.constants import LOT_SIZES
from core.models import (
    Candle, Exchange, NormalizedOrder, OrderSide, OrderType, ProductType, Tick,
)
from strategies.base import BaseStrategy, SignalResult
from strategies.indicators import sma, atr


class OptionWheel(BaseStrategy):
    name = "option_wheel"
    description = "Cash-secured put / covered call wheel strategy with strike selection via delta approximation"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.symbol = config.get("symbol", "NIFTY")
        self.quantity = config.get("quantity", LOT_SIZES.get(self.symbol, 75))
        self.strike_pct = config.get("strike_pct", 0.03)
        self._prices: list[float] = []
        self.phase: str = config.get("phase", "put_sell")

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
        if len(self._prices) < 20:
            return None

        price = candle.close
        atr_val = atr([candle], 1) or 0.0
        support = sma(self._prices, 20) - atr_val * 2
        resistance = sma(self._prices, 20) + atr_val * 2
        strike_distance = price * self.strike_pct
        orders = []

        if self.phase == "put_sell":
            if price > support + atr_val:
                sp = int(round((price - strike_distance) / 50) * 50)
                orders.append(NormalizedOrder(
                    symbol=self.symbol, exchange=Exchange.NSE, side=OrderSide.SELL,
                    order_type=OrderType.LIMIT, product=ProductType.OPTIONS,
                    quantity=self.quantity, price=sp,
                    strategy_id=self.config.get("strategy_id"),
                ))
                return SignalResult(orders=orders, reason=f"Cash-secured put sell at {sp}, price {price:.1f} above support {support:.1f}")
        elif self.phase == "call_sell":
            if price < resistance - atr_val:
                sc = int(round((price + strike_distance) / 50) * 50)
                orders.append(NormalizedOrder(
                    symbol=self.symbol, exchange=Exchange.NSE, side=OrderSide.SELL,
                    order_type=OrderType.LIMIT, product=ProductType.OPTIONS,
                    quantity=self.quantity, price=sc,
                    strategy_id=self.config.get("strategy_id"),
                ))
                return SignalResult(orders=orders, reason=f"Covered call sell at {sc}, price {price:.1f} below resistance {resistance:.1f}")
        elif self.phase == "stock_own":
            if price < support:
                orders.append(NormalizedOrder(
                    symbol=self.symbol, exchange=Exchange.NSE, side=OrderSide.SELL,
                    order_type=OrderType.MARKET, product=ProductType.INTRADAY,
                    quantity=self.quantity,
                    strategy_id=self.config.get("strategy_id"),
                ))
                return SignalResult(orders=[orders[0]], reason=f"Stop loss: price {price:.1f} broke support {support:.1f}")

        return None
