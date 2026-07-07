"""Base class for options-buying strategies.

Implements common buyer mechanics:
- Premium-based position sizing (risk% + outlay cap)
- ATM/ITM strike selection
- Premium SL, R-multiple target, breakeven arm, peak-trailing
- Theta time-stop (mandatory for all buyer strategies)
- IV gate (skip high IV entries)
- State persistence to Redis
"""
from __future__ import annotations

import logging
import math
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Optional

from core.cache import cache
from core.models import (
    Candle,
    Exchange,
    InstrumentType,
    NormalizedOrder,
    OptionType,
    OrderSide,
    OrderType,
    ProductType,
)
from core.notifications import send_telegram_alert
from engine.gate import execute_order as gate_execute_order
from engine.gate import generate_client_order_id
from market.instrument_service import instrument_service
from risk.riskguard import RiskGuard
from strategies.base import BaseStrategy, SignalResult

logger = logging.getLogger(__name__)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _option_delta(S: float, K: float, T: float, r: float, sigma: float, cepe: str) -> float:
    if T <= 0 or sigma <= 0.001:
        return 0.5 if cepe == "CE" else -0.5
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    nd1 = _norm_cdf(d1)
    return nd1 if cepe == "CE" else nd1 - 1.0


@dataclass
class BuyerConfig:
    strategy_id: str = ""
    user_id: str = ""
    index: str = "NIFTY"
    capital: float = 0.0
    or_start: time = time(9, 15)
    or_end: time = time(9, 30)
    last_entry: time = time(14, 30)
    square_off: time = time(15, 10)
    vol_mult: float = 1.5
    vol_lookback: int = 20
    itm_offset_steps: int = 0
    target_delta: float = 0.0
    risk_per_trade_pct: float = 1.0
    max_outlay_pct: float = 10.0
    sl_pct: float = 30.0
    rr_target: float = 1.5
    trail_giveback_pct: float = 25.0
    time_stop_min: int = 30
    time_stop_min_R: float = 0.5
    max_trades_per_day: int = 2
    backtest_mode: bool = False
    backtest_initial_capital: float = 100000.0

    @classmethod
    def from_dict(cls, d: dict) -> BuyerConfig:
        clean = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**clean)


class Phase(str, Enum):
    BUILDING_OR = "building_or"
    ARMED = "armed"
    IN_TRADE = "in_trade"
    DONE = "done"


class BuyerBase(BaseStrategy):
    name = "buyer_base"
    description = "Base class for options-buying strategies"

    def __init__(self, config: dict | None = None):
        super().__init__(config or {})
        self.bc = BuyerConfig.from_dict(config or {})
        self.phase = Phase.BUILDING_OR
        self.or_high = 0.0
        self.or_low = float("inf")
        self.vols: list[float] = []
        self.trades_today = 0
        self.traded_dirs: set[str] = set()
        self.lot_size = 0
        self.step = 0
        self.pos: Optional[dict] = None
        self._riskguard: Optional[RiskGuard] = None
        self._today_str = ""
        self._backtest_trades: list[dict] = []
        self._backtest_equity: list[dict] = []
        self._backtest_capital = self.bc.backtest_initial_capital

    @property
    def riskguard(self) -> Optional[RiskGuard]:
        if self._riskguard is None and self.bc.user_id:
            self._riskguard = RiskGuard(self.bc.user_id)
        return self._riskguard

    async def _is_kill_switched(self) -> bool:
        rg = self.riskguard
        if rg:
            return await rg.get_kill_switch_status()
        return False

    async def on_start(self) -> None:
        self.lot_size = instrument_service.lot_size(self.bc.index)
        self.step = instrument_service.strike_step(self.bc.index)
        self._today_str = datetime.now().strftime("%Y%m%d")
        cached = await cache.get(f"buyer:{self.bc.strategy_id}:{self._today_str}")
        if cached:
            self.from_state(cached)
            logger.info(
                "Restored state for %s: phase=%s pos=%s",
                self.bc.strategy_id, self.phase, self.pos is not None,
            )

    async def on_stop(self) -> None:
        await self._persist()

    async def on_tick(self, tick) -> Optional[SignalResult]:
        return None

    @abstractmethod
    async def on_candle(self, candle: Candle) -> Optional[SignalResult]:
        ...

    # ---------- shared helpers ----------

    async def _check_iv_gate(self) -> bool:
        pct = instrument_service.iv_percentile(self.bc.index)
        if pct is not None and pct > 85:
            logger.info("IV gate skip for %s: percentile=%.1f", self.bc.strategy_id, pct)
            return True
        return False

    async def _resolve_strike(self, spot: float, cepe: str) -> float:
        if self.bc.target_delta > 0:
            return await self._resolve_strike_by_delta(spot, cepe)
        atm = round(spot / self.step) * self.step
        offset = self.bc.itm_offset_steps * self.step
        return (atm - offset) if cepe == "CE" else (atm + offset)

    async def _resolve_strike_by_delta(self, spot: float, cepe: str) -> float:
        target = self.bc.target_delta if cepe == "CE" else -self.bc.target_delta
        strikes = await instrument_service.strikes(self.bc.index)
        if not strikes:
            atm = round(spot / self.step) * self.step
            offset = self.bc.itm_offset_steps * self.step
            return (atm - offset) if cepe == "CE" else (atm + offset)
        expiry = await instrument_service.nearest_weekly_expiry(self.bc.index)
        days = await instrument_service.days_to_expiry(self.bc.index, expiry)
        T = max(days, 1) / 365.0
        sigma = instrument_service.iv_percentile(self.bc.index)
        sigma = (sigma / 100.0) if sigma else 0.25
        r = 0.1
        best_strike = strikes[0]
        best_diff = float("inf")
        for k in strikes:
            delta = _option_delta(spot, k, T, r, sigma, cepe)
            diff = abs(delta - target)
            if diff < best_diff:
                best_diff = diff
                best_strike = k
        return best_strike

    async def _resolve_expiry(self) -> str:
        return await instrument_service.nearest_weekly_expiry(self.bc.index)

    def _build_symbol(self, expiry: str, strike: float, cepe: str) -> str:
        return instrument_service.option_symbol(self.bc.index, expiry, strike, cepe)

    def _premium_size(
        self, entry_premium: float, sl_premium: float, lot_size: int,
    ) -> tuple[int, int, float]:
        risk_per_lot = (entry_premium - sl_premium) * lot_size
        if risk_per_lot <= 0:
            return 0, 0, 0.0
        risk_amt = self.bc.capital * self.bc.risk_per_trade_pct / 100.0
        lots = math.floor(risk_amt / risk_per_lot)
        max_outlay = self.bc.capital * self.bc.max_outlay_pct / 100.0
        max_lots = (
            math.floor(max_outlay / (entry_premium * lot_size))
            if entry_premium * lot_size > 0
            else 0
        )
        lots = min(lots, max_lots)
        if lots < 1:
            return 0, 0, 0.0
        r_points = entry_premium - sl_premium
        return lots, lots * lot_size, r_points

    async def _place_order(self, symbol: str, side: str, qty: int, tag: str, premium: float | None = None) -> None:
        if self.bc.backtest_mode:
            self._record_backtest_trade(symbol, side, qty, tag, premium)
            return
        order = NormalizedOrder(
            symbol=symbol,
            exchange=Exchange.NFO,
            side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            product=ProductType.INTRADAY,
            quantity=qty,
            strategy_id=self.bc.strategy_id,
            user_id=self.bc.user_id,
            instrument_type=InstrumentType.OPT,
        )
        order.client_order_id = generate_client_order_id(
            self.bc.user_id, symbol, side,
            source="strategy", strategy_id=self.bc.strategy_id,
        )
        try:
            result = await gate_execute_order(self.bc.user_id, order, source="strategy")
            if result.success:
                logger.info(
                    "Order placed: %s %d %s tag=%s status=%s",
                    symbol, qty, side, tag, result.status,
                )
                if not self.bc.backtest_mode:
                    await send_telegram_alert(
                        f"🟢 <b>Trade Entry</b>\n{self.bc.strategy_id}\n{symbol} {side} {qty}\ntag: {tag}"
                    )
            else:
                logger.warning(
                    "Order failed: %s tag=%s msg=%s", symbol, tag, result.message,
                )
        except Exception as e:
            logger.error("Order exception %s tag=%s: %s", symbol, tag, e)

    async def _flatten(self, reason: str) -> None:
        if not self.pos:
            return
        p = self.pos
        logger.info(
            "Flatten %s reason=%s held=%.1fmin R=%.2f",
            p["symbol"], reason, p.get("held_min", 0), p.get("r", 0),
        )
        await self._place_order(
            p["symbol"], "SELL", p["qty"],
            f"{self.bc.strategy_id}:exit:{reason}",
            premium=getattr(self, "_current_premium", None),
        )
        if not self.bc.backtest_mode:
            pnl = p.get("entry", 0) - getattr(self, "_current_premium", 0)
            await send_telegram_alert(
                f"🔴 <b>Trade Exit</b>\n{self.bc.strategy_id}\n{p['symbol']} SELL {p['qty']}\nreason: {reason}\npnl: {pnl:.2f}"
            )
        self.pos = None
        if reason in ("square_off", "kill_switch"):
            self.phase = Phase.DONE
        else:
            self.phase = (
                Phase.ARMED
                if self.trades_today < self.bc.max_trades_per_day
                else Phase.DONE
            )

    def _check_theta_time_stop(self, bar: Candle) -> bool:
        if not self.pos or self.pos.get("entry_ts") is None:
            return False
        held = (bar.timestamp - self.pos["entry_ts"]).total_seconds() / 60.0
        self.pos["held_min"] = held
        progress_R = 0.0
        if self.pos.get("r", 0) > 0:
            progress_R = (self._current_premium - self.pos["entry"]) / self.pos["r"]
        if held >= self.bc.time_stop_min and progress_R < self.bc.time_stop_min_R:
            logger.info("Theta time-stop: held=%.1fmin progress=%.2fR", held, progress_R)
            return True
        return False

    def _check_structure_invalidation(self, bar: Candle) -> bool:
        if not self.pos or self.pos.get("be_armed", False):
            return False
        cepe = self.pos.get("cepe", "")
        if cepe == "CE" and bar.close < self.or_high:
            return True
        if cepe == "PE" and bar.close > self.or_low:
            return True
        return False

    def _update_trail(self, premium: float) -> None:
        if not self.pos:
            return
        p = self.pos
        p["peak"] = max(p["peak"], premium)
        if not p.get("be_armed", False) and premium >= p["entry"] + p["r"]:
            p["sl"] = p["entry"]
            p["be_armed"] = True
            logger.info("Breakeven armed at %.2f", premium)
        if p.get("be_armed", False):
            trail = p["peak"] * (1 - self.bc.trail_giveback_pct / 100.0)
            p["sl"] = max(p["sl"], trail)

    # ---------- backtesting ----------

    def _record_backtest_trade(self, symbol: str, side: str, qty: int, tag: str, premium: float | None = None) -> None:
        direction = side.upper()
        if premium is None:
            premium = getattr(self, "_current_premium", 0.0)
        cost = premium * qty
        pnl = None
        entry_premium = None

        if direction == "BUY":
            self._backtest_capital -= cost
        else:
            pnl = 0.0
            for t in reversed(self._backtest_trades):
                if t.get("symbol") == symbol and t.get("side") == "BUY" and t.get("pnl") is None:
                    entry_premium = t["premium"]
                    pnl = (premium - entry_premium) * qty
                    t["pnl"] = round(pnl, 2)
                    t["exit_tag"] = tag
                    t["exit_ts"] = datetime.now().isoformat()
                    break
            self._backtest_capital += premium * qty

        trade = {
            "symbol": symbol,
            "side": direction,
            "qty": qty,
            "premium": premium,
            "cost": cost,
            "tag": tag,
            "ts": datetime.now().isoformat(),
            "phase": self.phase.value,
        }
        if pnl is not None:
            trade["pnl"] = round(pnl, 2)
        if entry_premium is not None:
            trade["entry_premium"] = entry_premium
        self._backtest_trades.append(trade)

        capital_info = f"pnl={pnl:.2f}" if pnl is not None else ""
        logger.info("[BT] %s %s %d @%.2f tag=%s capital=%.2f %s", direction, symbol, qty, premium, tag, self._backtest_capital, capital_info)

    def _record_backtest_equity(self, timestamp: str) -> None:
        self._backtest_equity.append({
            "ts": timestamp,
            "capital": round(self._backtest_capital, 2),
            "in_trade": self.pos is not None,
        })

    def get_backtest_results(self) -> dict:
        total_pnl = self._backtest_capital - self.bc.backtest_initial_capital
        wins = [t for t in self._backtest_trades if t.get("pnl", 0) > 0]
        losses = [t for t in self._backtest_trades if t.get("pnl", 0) < 0]
        total_trades = len(self._backtest_trades)
        return {
            "initial_capital": self.bc.backtest_initial_capital,
            "final_capital": round(self._backtest_capital, 2),
            "total_pnl": round(total_pnl, 2),
            "return_pct": round(total_pnl / self.bc.backtest_initial_capital * 100, 2) if self.bc.backtest_initial_capital else 0,
            "total_trades": total_trades,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": round(len(wins) / total_trades * 100, 2) if total_trades else 0,
            "trades": self._backtest_trades,
            "equity": self._backtest_equity,
        }

    # ---------- persistence ----------

    async def _persist(self) -> None:
        if not self._today_str or not self.bc.strategy_id:
            return
        state = self.to_state()
        await cache.set(
            f"buyer:{self.bc.strategy_id}:{self._today_str}",
            state, ttl=86400,
        )

    def to_state(self) -> dict:
        pos = dict(self.pos) if self.pos else None
        if pos and pos.get("entry_ts"):
            pos["entry_ts"] = pos["entry_ts"].isoformat()
        return {
            "phase": self.phase.value,
            "or_high": self.or_high,
            "or_low": self.or_low,
            "vols": self.vols,
            "trades_today": self.trades_today,
            "traded_dirs": list(self.traded_dirs),
            "lot_size": self.lot_size,
            "step": self.step,
            "pos": pos,
        }

    def from_state(self, s: dict) -> None:
        self.phase = Phase(s.get("phase", Phase.BUILDING_OR.value))
        self.or_high = s.get("or_high", 0.0)
        self.or_low = s.get("or_low", float("inf"))
        self.vols = s.get("vols", [])
        self.trades_today = s.get("trades_today", 0)
        self.traded_dirs = set(s.get("traded_dirs", []))
        self.lot_size = s.get("lot_size", 0)
        self.step = s.get("step", 0)
        self.pos = s.get("pos")
        if self.pos and self.pos.get("entry_ts"):
            self.pos["entry_ts"] = datetime.fromisoformat(self.pos["entry_ts"])
