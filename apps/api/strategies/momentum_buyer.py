"""B1 — Intraday Momentum Breakout Buyer.

Buys ATM/ITM options on opening-range breakout with volume confirmation.
Manages position on option premium: initial SL, R-target, breakeven at +1R,
peak-trailing giveback, theta time-stop, and structure invalidation.
"""
import logging
from typing import Optional

from core.models import Candle
from market.instrument_service import instrument_service
from strategies.base import SignalResult
from strategies.buyer_base import BuyerBase, Phase

logger = logging.getLogger(__name__)


class MomentumBreakoutBuyer(BuyerBase):
    name = "momentum_breakout_buyer"
    description = "Intraday momentum option buyer — OR breakout + volume + premium management"

    async def on_candle(self, candle: Candle) -> Optional[SignalResult]:
        t = candle.timestamp.time()

        # Kill switch check
        if await self._is_kill_switched():
            return await self._handle_signal("kill_switch")
        if t >= self.bc.square_off:
            return await self._handle_signal("square_off")

        # Phase machine
        if self.phase == Phase.BUILDING_OR:
            self._build_or(candle, t)
        elif self.phase == Phase.ARMED and t < self.bc.last_entry:
            await self._check_entry(candle)
        elif self.phase == Phase.IN_TRADE:
            await self._manage(candle)

        # Track volume for confirmation
        self.vols.append(candle.volume)
        self.vols = self.vols[-self.bc.vol_lookback:]

        await self._persist()
        return None

    async def _handle_signal(self, reason: str) -> Optional[SignalResult]:
        await self._flatten(reason)
        await self._persist()
        return None

    # ---------- OR build ----------

    def _build_or(self, bar: Candle, t) -> None:
        if t < self.bc.or_end:
            self.or_high = max(self.or_high, bar.high)
            self.or_low = min(self.or_low, bar.low)
        else:
            self.phase = Phase.ARMED
            logger.info("OR locked: high=%.2f low=%.2f", self.or_high, self.or_low)

    # ---------- entry ----------

    async def _check_entry(self, bar: Candle) -> None:
        if self.trades_today >= self.bc.max_trades_per_day:
            return

        avg_vol = sum(self.vols) / len(self.vols) if self.vols else 0
        if avg_vol <= 0 or bar.volume <= self.bc.vol_mult * avg_vol:
            return

        if bar.close > self.or_high and "CE" not in self.traded_dirs:
            await self._enter("CE", bar.close)
        elif bar.close < self.or_low and "PE" not in self.traded_dirs:
            await self._enter("PE", bar.close)

    async def _enter(self, cepe: str, spot: float) -> None:
        await self._send_radar_alert(f"{cepe} @ {spot}\nOR Breakout + Volume Confirmation")
        if await self._check_iv_gate():
            return

        expiry = await self._resolve_expiry()
        strike = await self._resolve_strike(spot, cepe)
        symbol = self._build_symbol(expiry, strike, cepe)

        p0 = await instrument_service.option_ltp(self.bc.index, expiry, strike, cepe)
        if p0 <= 0:
            logger.warning("Entry skip: zero LTP for %s", symbol)
            return

        sl_prem = p0 * (1 - self.bc.sl_pct / 100.0)
        lots, qty, r_points = self._premium_size(p0, sl_prem, self.lot_size)
        if lots < 1:
            logger.warning("Entry skip: sizing<1 lot prem=%.2f sl=%.2f", p0, sl_prem)
            return

        logger.info("ENTER %s spot=%.2f strike=%.0f prem=%.2f lots=%d qty=%d R=%.2f",
                     cepe, spot, strike, p0, lots, qty, r_points)
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

    # ---------- management ----------

    async def _manage(self, bar: Candle) -> None:
        if not self.pos:
            return

        if self.pos["entry_ts"] is None:
            self.pos["entry_ts"] = bar.timestamp

        # Fetch current premium
        prem = await instrument_service.option_ltp(
            self.bc.index, self.pos["expiry"], self.pos["strike"], self.pos["cepe"],
        )
        if prem <= 0:
            return

        self._current_premium = prem
        self._update_trail(prem)

        # Exit checks
        if self._check_theta_time_stop(bar):
            return await self._flatten("theta_time_stop")
        if self._check_structure_invalidation(bar):
            return await self._flatten("structure_invalidation")
        if prem <= self.pos["sl"]:
            return await self._flatten("stop_loss" if not self.pos.get("be_armed") else "trail_stop")
        if prem >= self.pos["target"]:
            return await self._flatten("target")
