"""B2 — Trend-Rider Buyer.

Directional option buying on strong trend days.
Entry: EMA9>EMA21 + price>VWAP + ADX>20 (bullish), mirror for bearish.
Exit: Supertrend flip on underlying, or theta time-stop when trend weakens.
"""
import logging
from typing import Optional

from core.models import Candle
from market.instrument_service import instrument_service
from strategies.base import SignalResult
from strategies.buyer_base import BuyerBase, Phase
from strategies.indicators import adx, ema, sma, supertrend, vwap

logger = logging.getLogger(__name__)

TREND_STRONG_ADX = 20
TREND_WEAK_ADX = 20


class TrendRiderBuyer(BuyerBase):
    name = "trend_rider_buyer"
    description = "Options buyer — EMA9/21 + VWAP + ADX trend filter + Supertrend trail"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._candles: list[Candle] = []
        self._max_candles = 60

    async def on_start(self) -> None:
        await super().on_start()
        self._candles.clear()
        # Stretch default params for trend riding
        self.bc.sl_pct = float(self.config.get("sl_pct", 35.0))
        self.bc.time_stop_min = int(self.config.get("time_stop_min", 40))
        self.bc.time_stop_min_R = float(self.config.get("time_stop_min_R", 0.0))
        self.bc.last_entry = self.config.get("last_entry", __import__("datetime").time(14, 0))

    async def on_candle(self, candle: Candle) -> Optional[SignalResult]:
        t = candle.timestamp.time()

        if await self._is_kill_switched():
            return await self._handle_signal("kill_switch")
        if t >= self.bc.square_off:
            return await self._handle_signal("square_off")

        self._candles.append(candle)
        if len(self._candles) > self._max_candles:
            self._candles.pop(0)

        if self.phase == Phase.IN_TRADE:
            await self._manage(candle)
        elif self.phase == Phase.ARMED and t < self.bc.last_entry:
            if self.trades_today < self.bc.max_trades_per_day:
                await self._check_entry(candle)

        # Initial armed phase — transition from BUILDING_OR after first candle
        if self.phase == Phase.BUILDING_OR:
            self.phase = Phase.ARMED

        await self._persist()
        return None

    async def _handle_signal(self, reason: str) -> Optional[SignalResult]:
        await self._flatten(reason)
        await self._persist()
        return None

    def _has_indicators(self) -> bool:
        return len(self._candles) >= 22

    async def _check_entry(self, bar: Candle) -> None:
        if not self._has_indicators():
            return

        prices = [c.close for c in self._candles]
        fast = ema(prices, 9)
        slow = ema(prices, 21)
        v = vwap([(c.close, c.volume) for c in self._candles])
        dx = adx(self._candles, 14)

        if dx < TREND_STRONG_ADX:
            return

        # IV gate
        if await self._check_iv_gate():
            return

        if fast > slow and bar.close > v and "CE" not in self.traded_dirs:
            await self._enter("CE", bar.close)
        elif fast < slow and bar.close < v and "PE" not in self.traded_dirs:
            await self._enter("PE", bar.close)

    async def _enter(self, cepe: str, spot: float) -> None:
        expiry = await self._resolve_expiry()
        strike = await self._resolve_strike(spot, cepe)
        symbol = self._build_symbol(expiry, strike, cepe)

        p0 = await instrument_service.option_ltp(self.bc.index, expiry, strike, cepe)
        if p0 <= 0:
            return

        sl_prem = p0 * (1 - self.bc.sl_pct / 100.0)
        lots, qty, r_points = self._premium_size(p0, sl_prem, self.lot_size)
        if lots < 1:
            return

        logger.info(
            "ENTER %s spot=%.2f strike=%.0f prem=%.2f lots=%d EMA=%.1f/%.1f ADX=%.1f",
            cepe, spot, strike, p0, lots, ema([c.close for c in self._candles], 9),
            ema([c.close for c in self._candles], 21),
            adx(self._candles, 14),
        )
        await self._place_order(symbol, "BUY", qty, f"{self.bc.strategy_id}:entry", premium=p0)

        self.pos = {
            "cepe": cepe, "symbol": symbol, "strike": strike, "expiry": expiry,
            "entry": p0, "sl": sl_prem, "target": p0 + self.bc.rr_target * r_points,
            "r": r_points, "lots": lots, "qty": qty, "peak": p0,
            "be_armed": False, "entry_ts": None, "held_min": 0,
        }
        self.trades_today += 1
        self.traded_dirs.add(cepe)
        self.phase = Phase.IN_TRADE

    async def _manage(self, bar: Candle) -> None:
        if not self.pos:
            return
        if self.pos["entry_ts"] is None:
            self.pos["entry_ts"] = bar.timestamp

        prem = await instrument_service.option_ltp(
            self.bc.index, self.pos["expiry"], self.pos["strike"], self.pos["cepe"],
        )
        if prem <= 0:
            return

        self._current_premium = prem
        self._update_trail(prem)

        # Theta time-stop: no progress OR trend weakened
        if self._check_theta_time_stop(bar):
            return await self._flatten("theta_time_stop")

        # Supertrend flip on underlying — trend reversal exit
        if self._has_indicators():
            _, trend_up = supertrend(self._candles, 10, 3.0)
            cepe = self.pos["cepe"]
            trend_bullish = trend_up if cepe == "CE" else not trend_up
            if not trend_bullish:
                logger.info("Supertrend flip exit for %s", cepe)
                return await self._flatten("supertrend_flip")

        # Premium SL / target
        if prem <= self.pos["sl"]:
            return await self._flatten("stop_loss" if not self.pos.get("be_armed") else "trail_stop")
        if prem >= self.pos["target"]:
            return await self._flatten("target")

    def _check_theta_time_stop(self, bar: Candle) -> bool:
        if not self.pos or self.pos.get("entry_ts") is None:
            return False
        held = (bar.timestamp - self.pos["entry_ts"]).total_seconds() / 60.0
        self.pos["held_min"] = held
        progress_R = 0.0
        if self.pos.get("r", 0) > 0:
            progress_R = (self._current_premium - self.pos["entry"]) / self.pos["r"]
        dx = adx(self._candles, 14) if self._has_indicators() else 0
        weak_trend = dx < TREND_WEAK_ADX if self._has_indicators() else True
        if held >= self.bc.time_stop_min and (progress_R < self.bc.time_stop_min_R or weak_trend):
            logger.info(
                "Theta time-stop: held=%.1fmin progress=%.2fR ADX=%.1f",
                held, progress_R, dx,
            )
            return True
        return False

    def to_state(self) -> dict:
        base = super().to_state()
        base["candle_count"] = len(self._candles)
        return base

    def from_state(self, s: dict) -> None:
        super().from_state(s)
        # Candles can't be restored from state (no bar data in Redis)
        self._candles.clear()
