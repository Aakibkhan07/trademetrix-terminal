# Trade Metrix — Options BUYING Strategies Pack (NIFTY + SENSEX)

**Scope:** Options **buying** only (CE/PE kharidna, bechna nahi) — automated, NIFTY (NSE) + SENSEX (BSE), Aakib ke personal Fyers/Dhan account ke liye.

**Structure:** Part A specs → Part B reference implementation (momentum buyer) → Part C OpenCode/DeepSeek build prompt.

> **Buyer reality check (ye sabse important hai):** Option buying mein risk defined hai (max loss = premium), par iska matlab "safe" nahi. Retail F&O losers ki majority **option buyers** hi hote hain — kyunki **theta har din premium khaata hai** aur win-rate typically **low** hoti hai (~35–45%). Buying ka edge sirf 3 cheezon se aata hai: **(1) timing** (breakout/momentum ke saath entry, flat market mein bilkul nahi), **(2) fast exits + trailing** (profit turant book, premium evaporate ho jaata hai), aur **(3) theta time-stop** (agar trade time pe kaam nahi kar raha → nikal jao, poora din bleed mat karo). In teeno ke bina buying = slow bleed.

---

## Buying vs Selling — engine kya alag karega

| Cheez | Selling (pichla pack) | **Buying (ye pack)** |
|---|---|---|
| Risk | Undefined tail-risk | Defined = premium paid ✅ |
| Enemy | Bada directional move | **Theta decay + low win-rate** |
| Margin | SPAN+Exposure block hota hai | Sirf cash outlay (premium) |
| Strike | ATM/OTM sell | **ATM ya slightly ITM buy** (higher delta, kam theta drag) |
| Exit discipline | SL + basket target | **Trailing stop + THETA TIME-STOP** (non-negotiable) |
| IV | High IV sell achha | **High IV buy = trap (IV crush)** — low/expanding IV behtar |

---

## Key runtime facts (hardcode NAHI — instrument master se resolve)

| Cheez | Current (Jul 2026) | Rule |
|---|---|---|
| NIFTY weekly expiry | Tuesday | Runtime resolve (Sept 2025 mein Thu→Tue change hua tha) |
| SENSEX weekly expiry | Thursday | Runtime resolve |
| Lot size / strike step | NIFTY vs SENSEX alag, badalte hain | Instrument master se |
| Liquidity | SENSEX < NIFTY (wider spreads) | Buyer ke liye entry/exit slippage zyada → wider budget |

**Strike selection default:** ATM ya **1 strike ITM** (delta ~0.55–0.65). OTM sirf expiry-day lottery ke liye — theta usme sabse tezi se khaata hai.

---

## PART A — Strategy Specs

### Common rules (sab pe apply)

| Rule | Value |
|---|---|
| Timezone | Asia/Kolkata; NSE **aur** BSE holiday calendar |
| Risk per trade | 1% capital — premium-stop se sizing (neeche formula) |
| Premium outlay cap | Ek trade mein ≤ 10% capital premium mein (cash tie-up limit) |
| Daily loss cap | Existing **RiskGuard** se (naya code nahi) |
| Orders | Sirf **OrderManager** (PAPER/LIVE) — direct broker call nahi |
| Instruments | ATM/expiry/lot/step **runtime resolve** |
| **Theta time-stop** | Har buyer strategy mein mandatory (details per-strategy) |
| IV filter | IV percentile bahut high ho toh entry skip (IV-crush se bacho) |
| State | Redis `strategy:{id}:{date}` — restart-safe, order-tag dedupe |
| Kill switch | RiskGuard fire → position turant flat + halt |

**Sizing (buying):**
```
risk_amt          = capital * 1%
premium_risk/lot  = (entry_premium - sl_premium) * lot_size
lots              = floor(risk_amt / premium_risk_per_lot)
# extra cap: lots ka total premium outlay <= 10% capital; warna trim/skip
```

---

### B1 — Intraday Momentum Breakout Buyer *(workhorse — reference Part B mein)*

- **Index:** NIFTY ya SENSEX, nearest weekly expiry
- **Bars:** 5-min. Opening Range (OR) = 9:15–9:30 high/low (underlying)
- **Bullish entry:** 5-min close > OR-high **AND** volume > 1.5× last-20-bar avg → **buy CE** (ATM/1-ITM)
- **Bearish entry:** mirror → **buy PE**
- **SL (premium):** entry premium ka 30% (`sl_prem = P0 × 0.70`)
- **Target:** 1.5R (R = premium risk). **+1R pe** SL → breakeven
- **Trailing:** breakeven ke baad, peak premium se 25% giveback pe exit
- **Theta time-stop:** entry ke 30 min baad agar progress < 0.5R → exit
- **Structure invalidation:** underlying wapas OR ke andar close ho → exit (momentum fail)
- **Limits:** max 2 trades/day, ek direction ek baar, no entry after 14:30, square-off 15:10

### B2 — Trend-Rider Buyer (bigger moves ride karne ke liye)

- **Index:** NIFTY ya SENSEX, 5-min bars
- **Bullish:** EMA9 > EMA21 **AND** price > VWAP **AND** ADX(14) > 20 → buy CE (ATM/1-ITM)
- **Bearish:** mirror → buy PE
- **SL (premium):** 30–35% of premium (trends mein thoda wider)
- **Trail:** underlying pe **Supertrend(10,3)** ya ATR trail — jab tak trend intact, hold; flip pe exit
- **Theta time-stop:** agar 40 min mein premium entry se neeche + trend weak (ADX < 20) → exit
- **Limits:** max 2 trades/day, no entry after 14:00 (trends ko room chahiye), square-off 15:10
- Sabse achha strong-trend din pe; sideways din pe B1 se zyada bleed karega — isliye ADX filter tight rakho

### B3 — Long Straddle / Strangle (volatility expansion — event/breakout din)

- **Index:** NIFTY ya SENSEX weekly
- **Entry:** ATM CE + PE dono **BUY** (strangle = OTM offset) — jab **badi move expected** ho (range compression, pre-breakout, low IV)
- **IV gate (mandatory):** IV percentile **low/mid** pe hi lagao — high IV pe IV-crush se dono legs marte hain
- **Exit:** koi ek leg strongly profit (2–3×) → doosri leg cut, winner trail; ya combined premium −40% (dono ka loss cap) → dono exit
- **Theta time-stop:** yahi strategy sabse zyada bleed karti hai — agar move nahi aayi (combined premium flat) `time_stop_min` (e.g. 45 min) mein → dono exit
- ⚠️ **Sabse risky buyer play.** Move na aaye toh dono legs theta se marte hain. Chhoti size, event-day selective, ya bilkul optional

---

## PART B — Reference Implementation (B1 Momentum Breakout Buyer)

> Buyer-specific mechanics dikhata hai: strike selection, premium-based SL/target, **peak-trailing stop**, aur **theta time-stop**. B2/B3 isi interface (`on_start_of_day / on_bar / to_state / from_state`) ko follow karein.

```python
# strategies/momentum_buyer.py
"""Intraday momentum option BUYER for NIFTY / SENSEX weekly options.

Buys a directional ATM/ITM option on an opening-range breakout, manages purely on
option premium with a peak-trailing stop, and — critically for buyers — enforces a
THETA TIME-STOP so a non-performing long doesn't bleed all day.

Integration contract (same interface as engine's other strategies):
  - Orders ONLY via OrderManager (PAPER/LIVE handled there)
  - Risk   ONLY via RiskGuard (pre-trade + kill switch)
  - Instruments (ATM, nearest weekly expiry, lot size, strike step) resolved at
    RUNTIME from instrument service — never hardcoded
  - Live option LTP via quote provider
  - State persisted to Redis via to_state()/from_state()
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import time, datetime
from enum import Enum
from typing import Optional

# TODO(agent): wire to real repo modules
# from core.order_manager import OrderManager
# from core.risk_guard import RiskGuard
# from core.instruments import InstrumentService
# from core.quotes import QuoteProvider


@dataclass
class BuyerConfig:
    strategy_id: str = "momo_buyer_nifty_v1"
    index: str = "NIFTY"              # "NIFTY" | "SENSEX"
    capital: float = 0.0
    or_start: time = time(9, 15)
    or_end: time = time(9, 30)
    last_entry: time = time(14, 30)
    square_off: time = time(15, 10)
    vol_mult: float = 1.5
    vol_lookback: int = 20
    itm_offset_steps: int = 0        # 0 = ATM; 1 = one strike ITM (higher delta)
    risk_per_trade_pct: float = 1.0
    max_outlay_pct: float = 10.0     # max premium cash tie-up per trade
    sl_pct: float = 30.0             # premium stop = entry * (1 - sl_pct/100)
    rr_target: float = 1.5
    trail_giveback_pct: float = 25.0 # after breakeven armed, exit on giveback from peak
    time_stop_min: int = 30          # theta time-stop window
    time_stop_min_R: float = 0.5     # need >= this R progress by time_stop_min
    max_trades_per_day: int = 2


class Phase(str, Enum):
    BUILDING_OR = "building_or"
    ARMED = "armed"
    IN_TRADE = "in_trade"
    DONE = "done"


class MomentumBuyer:
    def __init__(self, cfg: BuyerConfig, order_manager, risk_guard, instruments, quotes):
        self.cfg = cfg
        self.om, self.rg, self.inst, self.q = order_manager, risk_guard, instruments, quotes
        self.phase = Phase.BUILDING_OR
        self.or_high = 0.0
        self.or_low = float("inf")
        self.vols: list[float] = []
        self.trades_today = 0
        self.traded_dirs: set[str] = set()
        self.lot_size = 0
        self.step = 0
        self.pos: Optional[dict] = None

    # ---------- lifecycle ----------

    def on_start_of_day(self) -> None:
        self.__init__(self.cfg, self.om, self.rg, self.inst, self.q)
        self.lot_size = self.inst.lot_size(self.cfg.index)      # runtime resolve
        self.step = self.inst.strike_step(self.cfg.index)

    def on_bar(self, bar) -> None:      # underlying 5-min bar: timestamp, ohlc, volume
        t = bar.timestamp.time()

        if self.rg.kill_switch_active():
            return self._flatten("kill_switch")
        if t >= self.cfg.square_off:
            return self._flatten("square_off")

        if self.phase == Phase.BUILDING_OR:
            self._build_or(bar, t)
        elif self.phase == Phase.ARMED and t < self.cfg.last_entry:
            self._check_entry(bar)
        elif self.phase == Phase.IN_TRADE:
            self._manage(bar)

        self.vols.append(bar.volume)
        self.vols = self.vols[-self.cfg.vol_lookback:]

    # ---------- OR ----------

    def _build_or(self, bar, t: time) -> None:
        if t < self.cfg.or_end:
            self.or_high = max(self.or_high, bar.high)
            self.or_low = min(self.or_low, bar.low)
        else:
            self.phase = Phase.ARMED

    # ---------- entry ----------

    def _check_entry(self, bar) -> None:
        if self.trades_today >= self.cfg.max_trades_per_day:
            self.phase = Phase.DONE
            return
        avg = sum(self.vols) / len(self.vols) if self.vols else 0
        vol_ok = avg > 0 and bar.volume > self.cfg.vol_mult * avg
        if not vol_ok:
            return
        if bar.close > self.or_high and "CE" not in self.traded_dirs:
            self._enter("CE", bar.spot)
        elif bar.close < self.or_low and "PE" not in self.traded_dirs:
            self._enter("PE", bar.spot)

    def _enter(self, cepe: str, spot: float) -> None:
        # IV gate — skip buying into inflated IV (crush risk)
        if self.inst.iv_percentile(self.cfg.index) is not None and \
           self.inst.iv_percentile(self.cfg.index) > 85:
            return
        expiry = self.inst.nearest_weekly_expiry(self.cfg.index)   # Tue/Thu auto
        atm = round(spot / self.step) * self.step
        off = self.cfg.itm_offset_steps * self.step
        strike = (atm - off) if cepe == "CE" else (atm + off)      # ITM direction
        symbol = self.inst.option_symbol(self.cfg.index, expiry, strike, cepe)

        p0 = self.q.ltp(symbol)
        if p0 <= 0:
            return
        sl_prem = p0 * (1 - self.cfg.sl_pct / 100)
        r_points = p0 - sl_prem
        risk_amt = self.cfg.capital * self.cfg.risk_per_trade_pct / 100
        lots = math.floor(risk_amt / (r_points * self.lot_size)) if r_points > 0 else 0
        # cap by premium outlay
        max_lots_outlay = math.floor(
            (self.cfg.capital * self.cfg.max_outlay_pct / 100) / (p0 * self.lot_size))
        lots = min(lots, max_lots_outlay)
        if lots < 1:
            return
        if not self.rg.pre_trade_check(self.cfg.strategy_id, cepe, lots):
            return

        qty = lots * self.lot_size
        self.om.place(strategy_id=self.cfg.strategy_id, symbol=symbol, side="BUY",
                      qty=qty, order_type="MARKET", tag=f"{self.cfg.strategy_id}:entry")
        self.pos = dict(cepe=cepe, symbol=symbol, entry=p0, sl=sl_prem,
                        target=p0 + self.cfg.rr_target * r_points, r=r_points,
                        lots=lots, qty=qty, peak=p0, be_armed=False,
                        entry_ts=None)  # engine sets entry_ts = bar.timestamp
        self.trades_today += 1
        self.traded_dirs.add(cepe)
        self.phase = Phase.IN_TRADE

    # ---------- management ----------

    def _manage(self, bar) -> None:
        p = self.pos
        if p["entry_ts"] is None:
            p["entry_ts"] = bar.timestamp
        prem = self.q.ltp(p["symbol"])
        p["peak"] = max(p["peak"], prem)

        # +1R -> breakeven
        if not p["be_armed"] and prem >= p["entry"] + p["r"]:
            p["sl"], p["be_armed"] = p["entry"], True

        # peak trailing after breakeven armed
        if p["be_armed"]:
            trail = p["peak"] * (1 - self.cfg.trail_giveback_pct / 100)
            p["sl"] = max(p["sl"], trail)

        # theta time-stop: not enough progress in window -> exit
        held_min = (bar.timestamp - p["entry_ts"]).total_seconds() / 60
        progress_R = (prem - p["entry"]) / p["r"] if p["r"] > 0 else 0
        if held_min >= self.cfg.time_stop_min and progress_R < self.cfg.time_stop_min_R:
            return self._flatten("theta_time_stop")

        # structure invalidation: underlying back inside OR
        back_inside = (bar.close < self.or_high) if p["cepe"] == "CE" \
            else (bar.close > self.or_low)
        if not p["be_armed"] and back_inside:
            return self._flatten("structure_invalidation")

        # premium SL / target
        if prem <= p["sl"]:
            return self._flatten("stop_loss" if not p["be_armed"] else "trail_stop")
        if prem >= p["target"]:
            return self._flatten("target")

    def _flatten(self, reason: str) -> None:
        if self.pos:
            p = self.pos
            self.om.place(strategy_id=self.cfg.strategy_id, symbol=p["symbol"],
                          side="SELL", qty=p["qty"], order_type="MARKET",
                          tag=f"{self.cfg.strategy_id}:exit:{reason}")
            self.pos = None
        if reason in ("square_off", "kill_switch"):
            self.phase = Phase.DONE
        elif self.phase == Phase.IN_TRADE:
            self.phase = (Phase.ARMED
                          if self.trades_today < self.cfg.max_trades_per_day
                          else Phase.DONE)

    # ---------- persistence ----------

    def to_state(self) -> dict:
        pos = dict(self.pos) if self.pos else None
        if pos and pos.get("entry_ts"):
            pos["entry_ts"] = pos["entry_ts"].isoformat()
        return dict(phase=self.phase.value, or_high=self.or_high, or_low=self.or_low,
                    vols=self.vols, trades_today=self.trades_today,
                    traded_dirs=list(self.traded_dirs), lot_size=self.lot_size,
                    step=self.step, pos=pos)

    def from_state(self, s: dict) -> None:
        self.phase = Phase(s["phase"])
        self.or_high, self.or_low = s["or_high"], s["or_low"]
        self.vols, self.trades_today = s["vols"], s["trades_today"]
        self.traded_dirs = set(s["traded_dirs"])
        self.lot_size, self.step = s["lot_size"], s["step"]
        self.pos = s["pos"]
        if self.pos and self.pos.get("entry_ts"):
            self.pos["entry_ts"] = datetime.fromisoformat(self.pos["entry_ts"])
```

---

## PART C — Master Build Prompt (paste into OpenCode / DeepSeek)

Pura block copy karo. Spec file (`options_buying_strategies_pack.md`) repo `docs/` mein rakho.

````text
# ROLE
Implementation engineer for Trade Metrix Terminal (Python FastAPI, Supabase
Postgres + RLS, Redis, Docker Compose on VPS behind Caddy, Fyers v3 / Dhan v2 via
BaseBroker ABC, OrderManager with PAPER/LIVE, RiskGuard with kill switch + daily
loss cap). Implement OPTIONS-BUYING-ONLY automated strategies for NIFTY (NSE) and
SENSEX (BSE) per `options_buying_strategies_pack.md` (Part A specs, Part B ref).

# OPERATING PROTOCOL (non-negotiable)
1. READ FIRST, CODE SECOND. Inventory the engine before writing: OrderManager,
   RiskGuard, BaseBroker, strategy runner, normalized Pydantic models, Redis
   helpers, instrument/symbol service, quote/websocket provider, holiday calendar,
   and any IV / option-greeks source. Output a FILE MAP (path + one-line purpose)
   and STOP for confirmation.
2. NO FABRICATION. If a needed module/endpoint/table doesn't exist, say so and
   propose where to add it. Never invent imports, symbols, or schema.
3. NO PARALLEL PATHS. Extend the existing strategy framework; work only in the
   canonical repo directory.
4. NO DIRECT BROKER CALLS from strategies. Orders via OrderManager, risk via
   RiskGuard. Strategies never know PAPER vs LIVE.
5. RUNTIME RESOLUTION ONLY — never hardcode ATM strike, nearest weekly expiry,
   expiry WEEKDAY, lot size, strike step. NIFTY and SENSEX weeklies expire on
   DIFFERENT weekdays and this has changed before via circular — resolve from the
   instrument master, never assume.
6. Asia/Kolkata; respect BOTH NSE and BSE holiday calendars.
7. Secrets from env only; never in code or logs.

# BUYER-SPECIFIC CONTRACTS (this is options BUYING, not selling)
- Strike selection: ATM or itm_offset_steps ITM (CE => lower strike, PE => higher
  strike). Resolve strike from spot at signal via instrument service.
- Sizing: risk_per_trade_pct off the PREMIUM stop distance, AND cap total premium
  outlay at max_outlay_pct of capital (buying uses cash, not margin). No SPAN calc.
- Management on OPTION PREMIUM: initial premium SL, R-multiple target, breakeven at
  +1R, then PEAK-TRAILING stop (giveback % from peak).
- THETA TIME-STOP is mandatory on every buyer strategy: if premium hasn't made
  >= time_stop_min_R by time_stop_min minutes, exit. A non-performing long must not
  be held through decay.
- IV gate: if an IV percentile / IV-rank source exists, SKIP entries into very high
  IV (crush risk). If no IV source exists, flag it and proceed without the gate but
  log a warning — do NOT fabricate IV numbers.
- Structure invalidation (B1): exit if the underlying closes back inside the OR
  before breakeven is armed.

# PINNED CONTRACTS
- Strategy interface: conform to the repo's if present; else create
  strategies/base.py with on_start_of_day(), on_bar(bar), to_state(),
  from_state(state) exactly as the Part B reference.
- Instruments: option_symbol(index, expiry, strike, cepe), nearest_weekly_expiry(
  index), lot_size(index), strike_step(index), and (optional) iv_percentile(index).
  Add any missing method to the instrument service; do not inline exchange
  assumptions.
- Cost model (backtest) for OPTIONS: brokerage (flat/order), STT (buyer pays STT on
  exercised ITM at expiry — model intraday exit vs expiry ITM correctly), exchange
  txn charges (NSE vs BSE differ), SEBI turnover fee, GST, stamp duty, and
  slippage. Buyers cross the spread on BOTH entry and exit — model 1 tick/leg for
  NIFTY, WIDER for SENSEX (thinner liquidity). If cost model missing, add costs.py.
- Config: per-strategy in Supabase strategy_configs with env fallback. PAPER is
  default. LIVE requires BOTH env TM_LIVE_TRADING=true AND per-strategy DB flag
  live_enabled=true.

# SCOPE (options buying only)
- B1 Momentum Breakout Buyer: port Part B reference into the real engine.
- B2 Trend-Rider Buyer: EMA9/21 + VWAP + ADX(14) directional buy, Supertrend/ATR
  trail on the underlying, theta time-stop on weak trend. Indicators incremental.
- B3 Long Straddle/Strangle (volatility expansion): ATM (or OTM) CE+PE buy with a
  MANDATORY IV gate and aggressive theta time-stop; treat as high-risk/optional.
- Backtest wiring: run all three on NIFTY and SENSEX with the options cost model.

# PHASES & DEFINITION OF DONE
Phase 1 — Discovery: FILE MAP + confirmed integration points (instrument service,
  quote provider, IV source presence/absence). STOP.
Phase 2 — base interface + B1 + unit tests: OR build, strike selection (mock
  instrument service with different weekdays for NIFTY vs SENSEX), premium sizing +
  outlay cap, breakeven arm, peak-trailing, THETA TIME-STOP, structure
  invalidation, restart restore. DoD: pytest green + sample PAPER session log.
Phase 3 — B2 + B3 + tests (trend filter correctness; long-straddle IV gate + time-
  stop; winner-trail-cut-loser logic). DoD: pytest green.
Phase 4 — backtests for B1/B2/B3 on NIFTY + SENSEX with full cost model; PAPER
  wired end-to-end on VPS. DoD: backtest report JSON (gross vs NET after costs; also
  report win-rate and avg win/avg avg loss — buyers live/die on payoff asymmetry) + one
  simulated day in PAPER with logs showing entry, trailing, time-stop, 15:10 flat.
Phase 5 — Ops: structured per-trade logging (strategy_id, symbol, tag, reason,
  held_minutes, R_multiple), kill-switch integration test, end-of-day summary
  (trades, win-rate, gross/NET PnL, costs, theta-stop count) to reporting/n8n hook.
  DoD: docs/RUNBOOK_options_buying.md.

# HARD SAFETY RULES
- Default PAPER. LIVE gate as pinned. On any unhandled exception in a strategy:
  flatten its position, halt that strategy only (error isolation), alert.
- Respect RiskGuard verdicts unconditionally; never retry a blocked order.
Begin with Phase 1 now.
````
