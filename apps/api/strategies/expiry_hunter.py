from datetime import datetime, timedelta, timezone

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

IST = timezone(timedelta(hours=5, minutes=30))


class ExpiryHunter(BaseStrategy):
    name = "expiry_hunter"
    description = "Sells options premium on expiry day — short straddles/strangles on high IV"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.symbol = config.get("symbol", "NIFTY")
        self.quantity = config.get("quantity", 50)
        self.iv_threshold = config.get("iv_threshold", 25.0)
        self.strike_distance = config.get("strike_distance", 2)
        self._iv_estimate: float = 0.0
        self._at_price: float = 0.0
        self._entry_done = False
        self._is_expiry = False

    async def on_start(self) -> None:
        self._iv_estimate = 0.0
        self._at_price = 0.0
        self._entry_done = False
        self._is_expiry = self._check_expiry_day()

    async def on_stop(self) -> None:
        pass

    async def on_tick(self, tick: Tick) -> SignalResult | None:
        return None

    async def on_candle(self, candle: Candle) -> SignalResult | None:
        if self._entry_done or not self._is_expiry:
            return None

        self._at_price = candle.close
        self._iv_estimate = self._estimate_iv(candle)

        if self._iv_estimate < self.iv_threshold:
            return None

        now = datetime.now(IST)
        if now.hour < 10 or now.hour > 14:
            return None

        strike = round(self._at_price / 100) * 100
        ce_strike = strike + self.strike_distance * 100
        pe_strike = strike - self.strike_distance * 100

        self._entry_done = True
        ce_symbol = f"{self.symbol}{ce_strike}CE"
        pe_symbol = f"{self.symbol}{pe_strike}PE"

        orders = [
            NormalizedOrder(
                symbol=ce_symbol,
                exchange=Exchange.NFO,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                product=ProductType.MIS,
                quantity=self.quantity,
                strategy_id=self.config.get("strategy_id"),
                reason=f"Short CE {ce_strike} — expiry day, IV {self._iv_estimate:.1f}%",
            ),
            NormalizedOrder(
                symbol=pe_symbol,
                exchange=Exchange.NFO,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                product=ProductType.MIS,
                quantity=self.quantity,
                strategy_id=self.config.get("strategy_id"),
                reason=f"Short PE {pe_strike} — expiry day, IV {self._iv_estimate:.1f}%",
            ),
        ]

        return SignalResult(orders=orders, reason=f"Expiry short strangle {ce_strike}CE/{pe_strike}PE")

    @staticmethod
    def _check_expiry_day() -> bool:
        now = datetime.now(IST)
        if now.weekday() != 3:
            return False
        return True

    @staticmethod
    def _estimate_iv(candle: Candle) -> float:
        if candle.close == 0:
            return 0
        range_pct = (candle.high - candle.low) / candle.close * 100
        return max(range_pct * 1.5, 15.0)
