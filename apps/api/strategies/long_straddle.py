"""B3 — Long Straddle / Strangle (volatility expansion).

Buys ATM CE + PE (or OTM for strangle) when a big move is expected (range
compression, pre-breakout, low IV). Exits when one leg wins 2-3x (cut loser,
trail winner) or combined premium drops -40%. IV gate required.

⚠️ HIGHEST RISK buyer strategy. Both legs bleed theta if no move materializes.
Small size, event-day selective only.
"""
import logging
from typing import Optional

from core.models import Candle
from market.instrument_service import instrument_service
from strategies.base import SignalResult
from strategies.buyer_base import BuyerBase, Phase

logger = logging.getLogger(__name__)


class LongStraddle(BuyerBase):
    name = "long_straddle"
    description = "ATM CE+PE buy for volatility expansion with IV gate and theta time-stop"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.pos_ce: Optional[dict] = None
        self.pos_pe: Optional[dict] = None
        self._entry_ts = None
        self.bc.max_trades_per_day = 1
        self.bc.time_stop_min = int(self.config.get("time_stop_min", 45))
        self.bc.sl_pct = 0.0

    async def on_start(self) -> None:
        await super().on_start()
        if self.pos:
            ce = self.pos.get("ce")
            pe = self.pos.get("pe")
            self.pos_ce = ce
            self.pos_pe = pe
            if ce and ce.get("entry_ts"):
                self._entry_ts = ce["entry_ts"]
            elif pe and pe.get("entry_ts"):
                self._entry_ts = pe["entry_ts"]

    async def on_candle(self, candle: Candle) -> Optional[SignalResult]:
        t = candle.timestamp.time()

        if await self._is_kill_switched():
            return await self._flatten_both("kill_switch")
        if t >= self.bc.square_off:
            return await self._flatten_both("square_off")

        if self.phase == Phase.BUILDING_OR:
            self.phase = Phase.ARMED

        if self.phase != Phase.ARMED and self.phase != Phase.IN_TRADE:
            return None

        if self.phase == Phase.IN_TRADE:
            await self._manage(candle)
        elif self.trades_today < 1 and t < self.bc.last_entry:
            await self._check_entry(candle)

        await self._persist()
        return None

    async def _check_entry(self, bar: Candle) -> None:
        pct = instrument_service.iv_percentile(self.bc.index)
        if pct is not None and pct > 70:
            logger.info("IV gate skip straddle: percentile=%.1f", pct)
            return

        expiry = await self._resolve_expiry()
        spot = bar.close
        atm = round(spot / self.step) * self.step
        offset = 0
        symbol_ce = instrument_service.option_symbol(self.bc.index, expiry, atm, "CE")
        symbol_pe = instrument_service.option_symbol(self.bc.index, expiry, atm, "PE")
        p_ce = await instrument_service.option_ltp(self.bc.index, expiry, atm, "CE")
        p_pe = await instrument_service.option_ltp(self.bc.index, expiry, atm, "PE")
        combined = p_ce + p_pe
        if combined <= 0:
            return

        risk_amt = self.bc.capital * self.bc.risk_per_trade_pct / 100.0
        lots_ce = max(1, int(risk_amt / (p_ce * self.lot_size))) if p_ce > 0 else 0
        lots_pe = max(1, int(risk_amt / (p_pe * self.lot_size))) if p_pe > 0 else 0
        if lots_ce < 1 or lots_pe < 1:
            return

        outlay = (lots_ce * p_ce + lots_pe * p_pe) * self.lot_size
        max_ok = self.bc.capital * self.bc.max_outlay_pct / 100.0
        scale = min(1.0, max_ok / outlay) if outlay > max_ok else 1.0
        if scale < 0.5:
            return
        lots_ce = max(1, int(lots_ce * scale))
        lots_pe = max(1, int(lots_pe * scale))
        qty_ce = lots_ce * self.lot_size
        qty_pe = lots_pe * self.lot_size

        logger.info(
            "STRADDLE ENTRY spot=%.2f ATM=%.0f CE=%.2f(%d) PE=%.2f(%d) combined=%.2f",
            spot, atm, p_ce, qty_ce, p_pe, qty_pe, combined,
        )

        self._entry_ts = bar.timestamp
        leg_target = self.config.get("leg_target_multiple", 2.5)
        loss_cap = 1.0 - self.config.get("combined_loss_pct", 40) / 100.0

        await self._place_order(symbol_ce, "BUY", qty_ce, f"{self.bc.strategy_id}:straddle:ce", premium=p_ce)
        self.pos_ce = {
            "symbol": symbol_ce, "strike": atm, "expiry": expiry,
            "entry": p_ce, "target": p_ce * leg_target, "peak": p_ce,
            "be_armed": False, "lots": lots_ce, "qty": qty_ce,
        }

        await self._place_order(symbol_pe, "BUY", qty_pe, f"{self.bc.strategy_id}:straddle:pe", premium=p_pe)
        self.pos_pe = {
            "symbol": symbol_pe, "strike": atm, "expiry": expiry,
            "entry": p_pe, "target": p_pe * leg_target, "peak": p_pe,
            "be_armed": False, "lots": lots_pe, "qty": qty_pe,
        }

        self.pos = {"ce": self.pos_ce, "pe": self.pos_pe, "entry_combined": combined, "loss_cap_mult": loss_cap}
        self.trades_today = 1
        self.phase = Phase.IN_TRADE

    async def _manage(self, bar: Candle) -> None:
        if not self.pos_ce or not self.pos_pe:
            return

        p_ce = await instrument_service.option_ltp(self.bc.index, self.pos_ce["expiry"], self.pos_ce["strike"], "CE")
        p_pe = await instrument_service.option_ltp(self.bc.index, self.pos_pe["expiry"], self.pos_pe["strike"], "PE")
        combined = p_ce + p_pe
        self._current_premium = combined
        self._current_premium_ce = p_ce
        self._current_premium_pe = p_pe

        for leg, prem, name in [(self.pos_ce, p_ce, "CE"), (self.pos_pe, p_pe, "PE")]:
            if leg is None:
                continue
            leg["peak"] = max(leg["peak"], prem)
            if not leg.get("be_armed") and prem >= leg["target"]:
                leg["be_armed"] = True
                leg["sl"] = leg["entry"]
            if leg.get("be_armed"):
                trail = leg["peak"] * 0.75
                leg["sl"] = max(leg.get("sl", 0), trail)

        # Winner trail, loser cut
        entry_combined = self.pos.get("entry_combined", 1.0)
        if combined < entry_combined * self.pos.get("loss_cap_mult", 0.6):
            logger.info("Straddle combined loss cap hit: %.2f / %.2f", combined, entry_combined)
            return await self._flatten_both("combined_loss_cap")

        held = (bar.timestamp - self._entry_ts).total_seconds() / 60.0 if self._entry_ts else 0
        if held >= self.bc.time_stop_min:
            progress_ce = (p_ce - self.pos_ce["entry"]) / self.pos_ce["entry"] if self.pos_ce["entry"] > 0 else 0
            progress_pe = (p_pe - self.pos_pe["entry"]) / self.pos_pe["entry"] if self.pos_pe["entry"] > 0 else 0
            if progress_ce < 0.5 and progress_pe < 0.5:
                logger.info("Straddle theta time-stop: held=%.1fmin CE=%.2f%% PE=%.2f%%", held, progress_ce * 100, progress_pe * 100)
                return await self._flatten_both("theta_time_stop")

        for leg, prem, name in [(self.pos_ce, p_ce, "CE"), (self.pos_pe, p_pe, "PE")]:
            if leg is None:
                continue
            sl = leg.get("sl", 0)
            if sl > 0 and prem <= sl:
                await self._flatten_leg(name, f"{name}_trail_stop" if leg.get("be_armed") else f"{name}_stop_loss")

        # Target hit on one leg -> cut the other, trail the winner
        for leg_hit, name_hit, prem_hit, other_leg, other_name in [
            (self.pos_ce, "CE", p_ce, self.pos_pe, "PE"),
            (self.pos_pe, "PE", p_pe, self.pos_ce, "CE"),
        ]:
            if leg_hit is None or other_leg is None:
                continue
            if prem_hit >= leg_hit["target"] and other_leg.get("qty", 0) > 0:
                logger.info("Straddle %s hit target=%.2f — cutting %s", name_hit, prem_hit, other_name)
                await self._flatten_leg(other_name, f"{other_name}_cut_winner")
                if other_name == "CE":
                    self.pos_ce = None
                else:
                    self.pos_pe = None
                break

    async def _flatten_leg(self, name: str, reason: str) -> None:
        leg = self.pos_ce if name == "CE" else self.pos_pe
        if leg and leg.get("qty", 0) > 0:
            p_leg = getattr(self, "_current_premium_ce" if name == "CE" else "_current_premium_pe", 0.0)
            await self._place_order(leg["symbol"], "SELL", leg["qty"], f"{self.bc.strategy_id}:straddle:exit:{reason}", premium=p_leg)
            leg["qty"] = 0

    async def _flatten_both(self, reason: str) -> None:
        await self._flatten_leg("CE", reason)
        await self._flatten_leg("PE", reason)
        self.pos_ce = None
        self.pos_pe = None
        self.pos = None
        self.phase = Phase.DONE if reason in ("square_off", "kill_switch") else Phase.ARMED

    def to_state(self) -> dict:
        base = super().to_state()
        ce = dict(self.pos_ce) if self.pos_ce else None
        pe = dict(self.pos_pe) if self.pos_pe else None
        if ce and ce.get("entry_ts"):
            ce["entry_ts"] = ce["entry_ts"].isoformat()
        if pe and pe.get("entry_ts"):
            pe["entry_ts"] = pe["entry_ts"].isoformat()
        base.update({
            "pos_ce": ce,
            "pos_pe": pe,
            "_entry_ts": self._entry_ts.isoformat() if self._entry_ts else None,
        })
        return base

    def from_state(self, s: dict) -> None:
        super().from_state(s)
        self.pos_ce = s.get("pos_ce")
        self.pos_pe = s.get("pos_pe")
        et = s.get("_entry_ts")
        self._entry_ts = __import__("datetime").datetime.fromisoformat(et) if et else None
        if self.pos_ce and self.pos_ce.get("entry_ts"):
            self.pos_ce["entry_ts"] = __import__("datetime").datetime.fromisoformat(self.pos_ce["entry_ts"])
        if self.pos_pe and self.pos_pe.get("entry_ts"):
            self.pos_pe["entry_ts"] = __import__("datetime").datetime.fromisoformat(self.pos_pe["entry_ts"])
