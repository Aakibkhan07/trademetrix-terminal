# Backtest Engine Benchmark — Phase D (research only, no implementation)

Date: 2026-08-05 · Status: RESEARCH/DRAFT — pending approval, NO code changes
Scope: benchmark Trademetrix Backtest Engine vs GoCharting, AlgoTest, TradingView, Tradetron across 8 capabilities.
Evaluated: the backtest EXPERIENCE only (not live trading/execution, not broker quality).

## 0. Method

- **Trademetrix side**: capabilities verified from shipped code — Phase 5 (v0.2.0-rc.6), Phase A (v1.5.10), Phase B (v1.5.11), Phase C (v1.6.0). Current suite 915 passed, 1 xfailed; all shipped to prod (`apps/api/backtest/*`, `apps/web/app/backtest/page.tsx`).
- **Competitor side**: official docs / platform pages only (sources cited inline per claim). No live accounts were used.
- **Classification per capability**: `Already Better` (we ship something the competitor lacks), `Equal` (comparable feature), `Missing` (absent in our engine), `Not Required` (no user value for a strategy-backtest product).

---

## 1. Benchmark Report — Capability Matrix

Legend: ✅ shipped natively · ⚠️ partial / third-party / unverified · ❌ not offered

| # | Capability | Trademetrix | GoCharting | AlgoTest | TradingView | Tradetron |
|---|---|---|---|---|---|---|
| 1 | Analytics (post-run stats) | ✅ 14-KPI grid, equity, drawdown, weekday/hour/month distributions, expectancy, RR ratios, alpha/beta (252d), risk analytics (accepted/rejected/halts, rejections-by-rule, capital/exposure/drawdown curves) | ⚠️ trade summary on strategy charts; no risk analytics | ⚠️ detailed report + drawdown; no rule-level risk | ⚠️ strategy-tester stats (net profit, max DD, win-rate); no risk simulation | ✅ net-cost A–F graded report, equity curve, drawdowns, cost lab |
| 2 | Replay (animated run) | ✅ event-driven candle-step replay engine, speeds 1x/2x/5x/10x/100x/MAX (`ReplaySpeed`, `backtest/models.py:16-32`), per-speed candle delays | ❌ no replay found in docs | ❌ no replay found in docs | ✅ Bar Replay (manual step, strategy re-evaluates per step) | ❌ no replay |
| 3 | Trade drill-down | ✅ paginated trade log + enriched per-trade fields (entry/exit reason, slippage, charges, taxes, cost_total, risk_amount, RR, duration), entry/exit markers on equity chart | ✅ signal overlays on price chart; no per-trade cost breakdown | ⚠️ trade list, click-to-chart for options legs | ✅ click trade in list → shows entry/exit on price chart | ✅ per-leg trade detail in report |
| 4 | Portfolio (multi-symbol) backtesting | ❌ single symbol per run | ❌ | ❌ | ❌ | ❌ |
| 5 | Multi-strategy comparison | ✅ `/compare` API (≤10 run ids, side-by-side metrics) | ❌ not found in docs | ❌ not found in docs | ✅ multiple strategies on one chart, separate tester results | ⚠️ multiple strategies run; no explicit comparison UI |
| 6 | Walk Forward Analysis | ✅ `walk_forward` optimizer method — train on prior fold (grid), evaluate on current fold via `candle_slice` (`optimizer.py:180`) | ❌ | ⚠️ WFA recommended in guidance blog; native feature unverified | ❌ native (Pineify third-party adds it) | ❌ |
| 7 | Monte Carlo | ✅ 2000 bootstrap paths over trade PnLs → p5/p25/p50/p75/p95, probability of profit (`optimizer.py:214`) | ❌ | ✅ Monte Carlo Drawdown — 10,000 simulations with percentile selector (e.g. 95th) | ❌ native (Pineify third-party) | ✅ Monte Carlo in report |
| 8 | Optimization (param search) | ✅ grid search (≤512 combos) + one-factor-at-a-time sensitivity (±20%) + WFA | ❌ not found in docs | ⚠️ param optimization in builder (unverified in docs) | ❌ native (Pineify third-party: grid/GA/WFA) | ❌ no automated search |

### Summary of classification

| Capability | Classification | Rationale |
|---|---|---|
| 1 Analytics | **Already Better** | Our rule-level risk analytics (rejection reasons, per-rule counts, risk timeline, capital/exposure curves) exist in NO competitor backtest. Tradetron's A–F net-cost grade is the closest rival and is cost-only. |
| 2 Replay | **Equal** | TradingView Bar Replay is interactive/manual; ours has speed control but no manual stepping. Different strengths, same capability. |
| 3 Trade drill-down | **Equal** | Our per-trade DATA (costs, reasons, risk, RR) is richer than all four, but on-chart trade visualization is only partial (equity-curve markers, not price-chart annotations). |
| 4 Portfolio backtesting | **Missing** (market-wide: Not Required) | No competitor offers it either. No evidence of user demand in this segment; defer. |
| 5 Multi-strategy comparison | **Equal** | TradingView supports multi-strategy charts; our `/compare` is explicit run-level comparison. |
| 6 Walk Forward Analysis | **Already Better** | Only AlgoTest possibly matches (unverified); TradingView/Tradetron/GoCharting lack it natively. |
| 7 Monte Carlo | **Equal** | AlgoTest (10k sims + percentile UI) and Tradetron (report) match us; ours is 2k paths inside the optimizer, not surfaced per-run. |
| 8 Optimization | **Already Better** | Only AlgoTest possibly matches (unverified); the other three lack native parameter search. |

**Scoreboard: 3 Already Better · 4 Equal · 1 Missing (Not Required market-wide)**

---

## 2. Gap Analysis

Ranked by (competitive gap × user value):

| Gap | Status | Notes |
|---|---|---|
| G1. Per-trade on-chart visualization | Gap vs TradingView/GoCharting | We annotate the equity curve only. Users cannot see where a trade happened on the price chart or click a trade → chart. Closes drill-down to Already Better. |
| G2. Monte Carlo surfaced in the run report | Gap vs AlgoTest/Tradetron | Machinery exists (`monte_carlo` optimizer method, 2000 paths, percentiles). Not visible in the run result/UI; no percentile selector. |
| G3. Comparison UI | Gap vs TradingView | `/compare` API exists; UI tab exists but is run-id-textbox based (Phase 5). No visual side-by-side. |
| G4. WFA surfaced + guarded | Gap vs our own optimizer | `walk_forward` exists but requires ≥2× window candles, unvalidated params can error; no UI exposure, no docs. AlgoTest visibility unknown. |
| G5. Portfolio backtesting | Not Required near-term | Zero market support; high complexity (multi-symbol accounting, correlation). Defer. |
| G6. Trade drill-down data richness parity | Already exceeded | Our per-trade cost/tax/reason/RR fields exceed all four competitors. No action. |

---

## 3. Prioritized Roadmap

| Rank | Item | Closes | Effort | Rationale |
|---|---|---|---|---|
| P1 | Clickable trades on a price chart (click trade → highlight entry/exit candles; keep enriched trade table) | G1 | M | Largest visible parity gap vs TradingView/GoCharting; direct user-facing win. |
| P2 | Surface Monte Carlo in run report (percentile band on equity curve + summary KPIs; reuse `monte_carlo` optimizer path) | G2 | S–M | Machinery exists; AlgoTest/Tradetron already market it. Cheap, high value. |
| P3 | Visual compare UI (chart overlay of equity curves + metric table; reuse `/compare`) | G3 | S | API exists; UI-only. |
| P4 | WFA UX + guard rails (fold count/coverage validation, UI picker, doc) | G4 | S–M | Already shipped under the hood; needs polish + docs to be credible. |
| P5 | Portfolio backtesting | G5 | XL | Defer — not offered by anyone, no demand signal. |

---

## 4. Estimated Complexity

Rough relative effort (S ≤ 1 day · M 2–4 days · L 1–2 weeks · XL > 2 weeks), per existing patterns (hot-deploy, test suite, prod smoke):

| Item | Backend | Frontend | Tests | Total | Risk |
|---|---|---|---|---|---|
| P1 price-chart trade drill-down | S (candles+trades already in payload; need candle slice around trade times) | M (new lightweight-charts PriceSeries + marker click handling; lightweight-charts v5 click API) | S (payload contract) | **M** | Medium — chart API interactions |
| P2 Monte Carlo in report | S (reuse `_run_combo`/`_monte_carlo` on result trades) | S (band series on existing chart) | S | **S–M** | Low — machinery proven |
| P3 compare UI | S (existing `/compare`; may add `downsample_pairs` reuse) | S (multi-series overlay) | S | **S** | Low |
| P4 WFA UX | S (validation errors → route 400s) | S (method/params UI exists) | S | **S–M** | Low |
| P5 portfolio backtesting | XL | L | L | **XL** | High — deferred |

---

## 5. Expected User Value

| Item | Value | Who benefits | Evidence base |
|---|---|---|---|
| P1 price-chart drill-down | High — converts a "backtest report" into an inspectable story; the #1 action users take after a run is "why did this trade happen". TradingView/GoCharting both offer it; its absence is the clearest feature gap. | Strategy builders, beta testers | Competitor parity (TV/GoCharting); Phase A trade enrichment already gives us the data to render it. |
| P2 Monte Carlo | High — directly answers "will this strategy survive a different order of outcomes?"; AlgoTest (10k sims + percentile picker) and Tradetron (report MC) show market acceptance. | All strategy authors | Competitor parity; our optimizer already implements 2000-path MC. |
| P3 compare UI | Medium — A/B of strategies is a daily workflow; TradingView multi-strategy tester sets the expectation. | Strategy authors, admin | Competitor parity. |
| P4 WFA UX | Medium — institutional credibility (out-of-sample honesty); only we and possibly AlgoTest have it natively — shipping it well converts Already Better into a marketable differentiator. | Advanced authors, institutions | Our own shipped engine. |
| P5 portfolio backtesting | Low now — nobody offers it; demand unproven. Revisit post-beta with user feedback. | — | Market scan (zero implementations). |

**Recommended first implementation candidate: P1 (price-chart trade drill-down), then P2 (Monte Carlo in report).** Both are parity-plus moves on two Already-Better/Equal axes, reuse shipped machinery, and are independently shippable.

---

### Sources (competitor evidence)
- GoCharting: gocharting.com strategy/formula charts + LipiScript docs (strategy backtest on price, options strategies; no WFA/MC/replay found).
- AlgoTest: docs.algotest.in — Monte Carlo Drawdown (10,000 simulations, percentile selection), options Strategy Builder; WFA referenced in guidance material (native status unverified).
- TradingView: in-chart Strategy Tester + Bar Replay, Pine Script; properties (capital, order size, commission, slippage); no native optimizer/MC/WFA (Pineify third-party adds grid/WFA/MC/GA).
- Tradetron: stateful event-driven minutely backtest (vs vectorised), net-cost A–F graded report, equity curve, drawdowns, Monte Carlo, cost lab, option premium/OI fills.
- Trademetrix: shipped code (this repo) — `apps/api/backtest/{models,manager,optimizer,replay_engine,performance,risk,execution}.py`, `routes/v1_backtest.py`, `apps/web/app/backtest/page.tsx`; CHANGELOG v1.5.10–v1.6.0.
