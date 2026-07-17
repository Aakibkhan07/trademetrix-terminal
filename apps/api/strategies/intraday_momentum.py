from core.constants import LOT_SIZES
from core.models import (
    Candle, Exchange, NormalizedOrder, OrderSide, OrderType, ProductType, Tick,
)
from strategies.base import BaseStrategy, SignalResult
from strategies.indicators import sma, atr


class IntradayMomentum(BaseStrategy):
    name = "intraday_momentum"
    description = "Fast intraday momentum scalper using VWAP cross, RSI confirmation, and volume thrust"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.symbol = config.get("symbol", "NIFTY")
        self.quantity = config.get("quantity", LOT_SIZES.get(self.symbol, 75))
        self.rsi_period = config.get("rsi_period", 7)
        self._prices: list[float] = []
        self._volume_price: list[tuple[float, float]] = []
        self._volume_thrust = 0

    async def on_start(self) -> None:
        self._prices.clear()
        self._volume_price.clear()
        self._volume_thrust = 0

    async def on_stop(self) -> None:
        pass

    async def on_tick(self, tick: Tick) -> SignalResult | None:
        if tick.last_price and tick.volume:
            self._volume_price.append((tick.last_price, tick.volume))
        if len(self._volume_price) > 200:
            self._volume_price.pop(0)
        if len(self._volume_price) < 20:
            return None

        vwap = self._calc_vwap()
        if vwap == 0:
            return None
        price = tick.last_price

        recent_vols = [v for _, v in self._volume_price[-10:]]
        avg_vol = sum(recent_vols) / len(recent_vols)
        prior_vols = [v for _, v in self._volume_price[-20:-10]]
        prior_avg = sum(prior_vols) / len(prior_vols) if prior_vols else 1
        vol_ratio = avg_vol / prior_avg if prior_avg > 0 else 1

        deviation = (price - vwap) / vwap

        if deviation > 0.002 and vol_ratio > 1.8:
            self._volume_thrust = 1
        elif deviation < -0.002 and vol_ratio > 1.8:
            self._volume_thrust = -1
        elif abs(deviation) < 0.001:
            self._volume_thrust = 0

        return None

    async def on_candle(self, candle: Candle) -> SignalResult | None:
        self._prices.append(candle.close)
        if len(self._prices) > 100:
            self._prices.pop(0)
        if len(self._prices) < self.rsi_period + 2:
            return None

        rsi = self._rsi(self._prices, self.rsi_period)
        prev_rsi = self._rsi(self._prices[:-1], self.rsi_period)
        atr_val = atr([candle], 1) or 0.0
        price = candle.close

        if self._volume_thrust == 1 and prev_rsi < 70 and rsi >= 70:
            order = NormalizedOrder(
                symbol=self.symbol, exchange=Exchange.NSE, side=OrderSide.BUY,
                order_type=OrderType.LIMIT, product=ProductType.INTRADAY,
                quantity=self.quantity, price=price,
                strategy_id=self.config.get("strategy_id"),
            )
            return SignalResult(orders=[order], reason=f"Volume thrust buy: RSI {rsi:.1f}, vol ratio {self._volume_thrust:.1f}")

        if self._volume_thrust == -1 and prev_rsi > 30 and rsi <= 30:
            order = NormalizedOrder(
                symbol=self.symbol, exchange=Exchange.NSE, side=OrderSide.SELL,
                order_type=OrderType.LIMIT, product=ProductType.INTRADAY,
                quantity=self.quantity, price=price,
                strategy_id=self.config.get("strategy_id"),
            )
            return SignalResult(orders=[order], reason=f"Volume thrust sell: RSI {rsi:.1f}, vol ratio {abs(self._volume_thrust):.1f}")

        return None

    def _calc_vwap(self) -> float:
        if not self._volume_price:
            return 0.0
        pv = sum(p * v for p, v in self._volume_price)
        vol = sum(v for _, v in self._volume_price)
        return pv / vol if vol else 0.0

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
