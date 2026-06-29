
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


class SMCSniper(BaseStrategy):
    name = "smc_sniper"
    description = "Smart Money Concepts — detects order blocks and liquidity grabs"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.symbol = config.get("symbol", "NIFTY")
        self.quantity = config.get("quantity", LOT_SIZES.get(self.symbol, 75))
        self.lookback = config.get("lookback", 10)
        self._candles: list[Candle] = []

    async def on_start(self) -> None:
        self._candles.clear()

    async def on_stop(self) -> None:
        pass

    async def on_tick(self, tick: Tick) -> SignalResult | None:
        return None

    async def on_candle(self, candle: Candle) -> SignalResult | None:
        self._candles.append(candle)
        if len(self._candles) < self.lookback:
            return None

        if len(self._candles) > self.lookback * 2:
            self._candles = self._candles[-self.lookback:]

        result = self._detect_order_block()
        if result:
            return result

        result = self._detect_liquidity_grab()
        if result:
            return result

        return None

    def _detect_order_block(self) -> SignalResult | None:
        if len(self._candles) < 5:
            return None

        last = self._candles[-1]
        prev = self._candles[-2]
        prev2 = self._candles[-3]

        bullish_ob = (
            prev2.low < prev.low
            and prev.high > prev2.high
            and last.close > prev.high
            and prev.close < prev.open
        )
        bearish_ob = (
            prev2.high > prev.high
            and prev.low < prev2.low
            and last.close < prev.low
            and prev.close > prev.open
        )

        if bullish_ob:
            order = NormalizedOrder(
                symbol=self.symbol,
                exchange=Exchange.NSE,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                product=ProductType.INTRADAY,
                quantity=self.quantity,
                strategy_id=self.config.get("strategy_id"),
            )
            return SignalResult(
                orders=[order],
                reason=f"Bullish order block detected at {prev.low:.2f}",
            )

        if bearish_ob:
            order = NormalizedOrder(
                symbol=self.symbol,
                exchange=Exchange.NSE,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                product=ProductType.INTRADAY,
                quantity=self.quantity,
                strategy_id=self.config.get("strategy_id"),
            )
            return SignalResult(
                orders=[order],
                reason=f"Bearish order block detected at {prev.high:.2f}",
            )

        return None

    def _detect_liquidity_grab(self) -> SignalResult | None:
        if len(self._candles) < 6:
            return None

        recent = self._candles[-3:]
        prior = self._candles[-6:-3]

        prior_high = max(c.high for c in prior)
        prior_low = min(c.low for c in prior)

        grab_high = any(c.high > prior_high for c in recent[:2]) and recent[-1].close < prior_high
        grab_low = any(c.low < prior_low for c in recent[:2]) and recent[-1].close > prior_low

        if grab_high:
            order = NormalizedOrder(
                symbol=self.symbol,
                exchange=Exchange.NSE,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                product=ProductType.INTRADAY,
                quantity=self.quantity,
                strategy_id=self.config.get("strategy_id"),
            )
            return SignalResult(
                orders=[order],
                reason=f"Liquidity grab above resistance {prior_high:.2f}, reversal SELL",
            )

        if grab_low:
            order = NormalizedOrder(
                symbol=self.symbol,
                exchange=Exchange.NSE,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                product=ProductType.INTRADAY,
                quantity=self.quantity,
                strategy_id=self.config.get("strategy_id"),
            )
            return SignalResult(
                orders=[order],
                reason=f"Liquidity grab below support {prior_low:.2f}, reversal BUY",
            )

        return None
