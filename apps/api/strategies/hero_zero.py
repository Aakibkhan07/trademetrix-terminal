"""Hero Zero — Expiry Day Buyer.
Buys premium <100 (5-100) on expiry day, not far OTM always, targets 3-5x.
SL 40% on premium, 15m trend + 5m execution, 10 lots, 09:30-15:40."""
import logging
from datetime import date, datetime, timezone, timedelta
from typing import Optional
from core.constants import LOT_SIZES, STRIKE_INTERVALS, get_weekly_expiry
from core.models import Candle, Exchange, NormalizedOrder, OrderSide, OrderType, ProductType
from market.instrument_service import instrument_service
from strategies.base import SignalResult
from strategies.buyer_base import BuyerBase, Phase
logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
EXPIRY_WEEKDAY = {"NIFTY": 1, "BANKNIFTY": 3, "FINNIFTY": 1, "SENSEX": 3, "MIDCPNIFTY": 3}
class HeroZero(BuyerBase):
    name = "hero_zero"
    description = "Expiry Hero Zero — premium <100 buyer, 3-5x target, 40% SL, not far OTM always"
    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.symbol = config.get("symbol", "NIFTY") if config else "NIFTY"
        self.bc.index = self.symbol
        self.bc.sl_pct = 40.0
        self.bc.rr_target = 3.5
        self.bc.rr_min = 2.0
        self.bc.rr_max = 5.0
        self._is_expiry = False
    async def on_start(self) -> None:
        await super().on_start()
        self._is_expiry = self._check_expiry_day()
        if self._is_expiry:
            logger.info("HeroZero %s: EXPIRY DAY active", self.bc.strategy_id)
    def _check_expiry_day(self) -> bool:
        now = datetime.now(IST)
        wd = EXPIRY_WEEKDAY.get(self.bc.index.upper(), 3)
        return now.weekday() == wd
    async def _on_15m(self, candle: Candle) -> Optional[SignalResult]:
        t = candle.timestamp.time()
        if await self._is_kill_switched():
            return await self._handle_signal("kill_switch")
        if t >= self.bc.square_off:
            return await self._handle_signal("square_off")
        if not self._is_expiry:
            return None
        if self.phase == Phase.BUILDING_OR:
            self._build_or(candle, t)
        elif self.phase == Phase.ARMED and t < self.bc.last_entry:
            await self._check_entry(candle)
        elif self.phase == Phase.IN_TRADE:
            await self._manage(candle)
        self.vols.append(candle.volume)
        self.vols = self.vols[-self.bc.vol_lookback:]
        await self._persist()
        return None
    async def on_candle(self, candle: Candle) -> Optional[SignalResult]:
        return await super().on_candle(candle)
    def _build_or(self, bar: Candle, t):
        if t < self.bc.or_end:
            self.or_high = max(self.or_high, bar.high)
            self.or_low = min(self.or_low, bar.low)
        else:
            self.phase = Phase.ARMED
            logger.info("HeroZero OR locked: high=%.2f low=%.2f", self.or_high, self.or_low)
    async def _check_entry(self, bar: Candle) -> None:
        if self.trades_today >= self.bc.max_trades_per_day:
            return
        now = datetime.now(IST)
        if not (9 <= now.hour <= 11):
            return
        expiry = await self._resolve_expiry()
        spot = bar.close
        # Find premium <100 (5-100), not far OTM always — near ATM to 3-5 OTM
        best = None
        best_score = -1
        for dist in [0, 1, 2, 3, 4, 5]:
            for cepe in ["CE", "PE"]:
                step = self.step or STRIKE_INTERVALS.get(self.bc.index, 50)
                atm = round(spot / step) * step
                strike = atm + dist * step if cepe == "CE" else atm - dist * step
                prem = await instrument_service.option_ltp(self.bc.index, expiry, strike, cepe)
                if 5 <= prem < 100:
                    score = prem if cepe == "CE" and spot >= self.or_high else prem if cepe == "PE" and spot <= self.or_low else prem * 0.5
                    if score > best_score:
                        best = (cepe, strike, prem, expiry)
                        best_score = score
        if not best:
            return
        cepe, strike, p0, expiry = best
        # Trend filter: CE only if spot > OR high, PE if < OR low
        if cepe == "CE" and spot < self.or_high:
            return
        if cepe == "PE" and spot > self.or_low:
            return
        sl_prem = p0 * 0.6
        lots, qty, r = self._premium_size(p0, sl_prem, self.lot_size)
        if lots < 1:
            return
        qty = 10 * self.lot_size
        rr = self._get_rr()
        logger.info("HERO ZERO %s spot=%.2f strike=%.0f prem=%.2f qty=%d RR=%.1f", cepe, spot, strike, p0, qty, rr)
        symbol = self._build_symbol(expiry, strike, cepe)
        await self._place_order(symbol, "BUY", qty, f"{self.bc.strategy_id}:hero_zero", premium=p0)
        self.pos = {"cepe": cepe, "symbol": symbol, "strike": strike, "expiry": expiry, "entry": p0, "sl": sl_prem, "target": p0 + rr * (p0 - sl_prem), "r": p0 - sl_prem, "lots": 10, "qty": qty, "peak": p0, "be_armed": False, "entry_ts": None, "held_min": 0, "rr": rr}
        self.trades_today += 1
        self.traded_dirs.add(cepe)
        self.phase = Phase.IN_TRADE
    async def _manage(self, bar: Candle) -> None:
        if not self.pos:
            return
        if self.pos["entry_ts"] is None:
            self.pos["entry_ts"] = bar.timestamp
        prem = await instrument_service.option_ltp(self.bc.index, self.pos["expiry"], self.pos["strike"], self.pos["cepe"])
        if prem <= 0:
            return
        self._current_premium = prem
        self._update_trail(prem)
        if self._check_theta_time_stop(bar):
            return await self._flatten("theta_time_stop")
        if prem <= self.pos["sl"]:
            return await self._flatten("hero_zero_sl")
        if prem >= self.pos["target"]:
            return await self._flatten("hero_zero_target")
        if self._check_structure_invalidation(bar):
            return await self._flatten("structure_invalidation")
    async def _flatten(self, reason: str) -> None:
        if not self.pos:
            return
        p = self.pos
        await self._place_order(p["symbol"], "SELL", p["qty"], f"{self.bc.strategy_id}:exit:{reason}", premium=getattr(self, "_current_premium", None))
        self.pos = None
        self.phase = Phase.DONE if reason in ("square_off", "kill_switch") else Phase.ARMED
    async def _handle_signal(self, reason: str) -> Optional[SignalResult]:
        await self._flatten(reason)
        await self._persist()
        return None
