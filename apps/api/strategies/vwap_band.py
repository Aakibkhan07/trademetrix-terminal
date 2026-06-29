
from core.constants import LOT_SIZES
from core.models import (
    Candle, Exchange, NormalizedOrder, OrderSide, OrderType, ProductType, Tick,
)
from strategies.base import BaseStrategy, SignalResult


class VWAPBand(BaseStrategy):
    name = "vwap_band"
    description = "VWAP mean reversion with deviation bands"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.symbol = config.get("symbol", "NIFTY")
        self.quantity = config.get("quantity", LOT_SIZES.get(self.symbol, 75))
        self.dev_threshold = config.get("dev_threshold", 0.005)
        self._volume_price: list[tuple[float, float]] = []

    async def on_start(self) -> None:
        self._volume_price.clear()

    async def on_stop(self) -> None:
        pass

    async def on_tick(self, tick: Tick) -> SignalResult | None:
        if tick.last_price and tick.volume:
            self._volume_price.append((tick.last_price, tick.volume))
        if len(self._volume_price) < 20:
            return None

        vwap = self._calc_vwap()
        price = tick.last_price
        deviation = (price - vwap) / vwap if vwap else 0

        side = None
        reason = ""

        if deviation <= -self.dev_threshold:
            side = OrderSide.BUY
            reason = f"Price {deviation*100:.2f}% below VWAP {vwap:.1f} - mean reversion buy"
        elif deviation >= self.dev_threshold:
            side = OrderSide.SELL
            reason = f"Price {deviation*100:.2f}% above VWAP {vwap:.1f} - mean reversion sell"

        if side:
            order = NormalizedOrder(
                symbol=tick.symbol.split(":")[-1] if ":" in tick.symbol else tick.symbol,
                exchange=Exchange.NSE,
                side=side,
                order_type=OrderType.MARKET,
                product=ProductType.INTRADAY,
                quantity=self.quantity,
                strategy_id=self.config.get("strategy_id"),
            )
            return SignalResult(orders=[order], reason=reason)

        return None

    async def on_candle(self, candle: Candle) -> SignalResult | None:
        return None

    def _calc_vwap(self) -> float:
        if not self._volume_price:
            return 0.0
        pv_sum = sum(p * v for p, v in self._volume_price)
        v_sum = sum(v for _, v in self._volume_price)
        return pv_sum / v_sum if v_sum else 0.0
