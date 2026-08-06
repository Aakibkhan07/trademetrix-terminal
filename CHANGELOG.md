## v1.6.8 (2026-08-07) — Live Dashboard: unified `/live` operational cockpit + landing wiring (PRODUCTION VERIFIED)

> Additive frontend feature ONLY — `apps/api` untouched this release (Phase A signal payload was shipped earlier under the v1.6.7 line). No new REST endpoints: the dashboard composes existing OMS/Engine/Paper/Runtime/Marketdata services. No redirects were removed for any existing page.

### What was done
1. **New route `/live` (`apps/web/app/live/page.tsx`)** — three-column cockpit: header (logo→`/live`, LIVE badge, Market OPEN/CLOSED chip, Stream SSE chip, Online chip, Workspace link, user name); left segmented Positions | Orders | Portfolio (live+paper positions with quote-driven change%, engine orders with cancel, portfolio summary incl. engine margins); center symbol chips (indices + your open positions) + `Chart` + Quick Trade; right rail Trading Controls (Emergency Stop w/ confirm dialog, Pause All, collapsible runtime diagnostics) + Live Signals (SignalGenerated SSE feed with filters + runtime seeds). Every widget renders Loading/Empty/Offline/Broker-disconnected/Market-closed via the shared `widget-frame`.
2. **Shared `apps/web/components/live/` (13 files)** — types, use-live-connection, use-live-data, widget-frame, table, market-overview, positions-panel, orders-panel, use-live-feed, signal-card, live-signals, trading-controls. Built entirely on the existing design system + W6 primitives (KpiCard, SkeletonBar, Dialog, Badge/Dot/Chip) — no new CSS.
3. **Landing wiring** — landing page CTAs/nav/footer → `/live`; app-layout Home section → single "Live Dashboard"; logo pixel + admin-route non-admin bounce → `/live`; sign-in + onboarding (CTA + completed-guard) → `/live` for non-admins, `/dashboard` for admins. Portfolio/Workspace/Backtest/etc. remain directly accessible.
4. **Validation** — web `tsc --noEmit` 0 errors, `next lint` 0 new errors, `npm run build` clean (`.env.production` swap + restore); backend suite **963 passed, 1 xfailed** (unchanged by this release).
5. **Deployment** — web hot-deploy (BUILD_ID `YCwC6U2jJMRugxdXVPcI1`); health 200, `/live` + `/` + `/portfolio` 200 public + in-container; **browser smoke on prod 13/13** (fresh users via GoTrue; anonymous → gate, signup → onboarding → CTA → `/live`, login → `/live`, widgets render, logo → `/live`, no page errors); smoke users swept; Redis `global:kill_switch` untouched (ENABLED, 1, TTL -1).

> Monitoring after deploy: none of the dashboard/resource states reported. See AGENTS.md session entry for the reference notes on `/live` composition and the CSS-uppercase smoke gotcha.

## v1.6.7 (2026-08-06) — Sprint-3 W6: shared UI primitives — KpiCard/Badge/Skeleton/Dialog consolidation (PRODUCTION VERIFIED)
> No API, routing, or state changes. No visual redesign. Sprint 4 explicitly NOT started.

### What was done
1. **`apps/web/components/ui/` shared primitives** — `kpi-card.tsx` (`KpiCard` stat/metric/beta),
   `badge.tsx` (`Badge`/`Dot`/`Chip`/`OrderStatusBadge`/`InstrumentTypeBadge`/`TierBadge` via
   `BadgeVariant`, colors → token-backed `t-badge`/`t-dot`/`t-chip` classes), `skeleton.tsx`
   (`SkeletonBar` + `PageLoadingSkeleton`; re-exported via `components/skeleton.tsx`),
   `dialog.tsx` (`Dialog` — single source replacing 7 inline `t-modal` sites).
2. **Consolidation** — KPI cards (backtest/admin-beta/strategies/[key]/dashboard pnl), skeletons
   (3 `loading.tsx` + 5 page panels), dialogs (settings/account/brokers/strategies/marketdata/
   terminal-builder/alert-modal/deploy-wizard), badge sets (dashboard admin-content, catalog,
   builder, watchlist) all delegate to the shared primitives; legacy shims in `components/`
   (`empty-state.tsx`, `skeleton.tsx`) keep old import paths working.
3. **Deploy** — web consolidated via production deploy flow (`infra/production/deploy.sh`),
   `origin/main` at `a0e5b8a`; API + web health 200. Post-deploy: 12 public routes 200,
   visible-text parity 12/12 (only webpack chunk-order noise in raw HTML), BUILD_ID `znbojLqT0xaMuNozJJ5dw` served.
4. **Reports** — `reports/` (`Consolidation-Sprint-3.md`, `W6--Detailed.md`,
   `W6-Visual-Verification.md`, `W6-Validation.md`, `W6-UI.md`).

> Internal consolidation only — no routes, endpoints, response formats, serializers or dead-code
> changes (nothing deleted; legacy `v1_portfolio` router tagged INACTIVE, not removed). **SPRINT 2
> PRODUCTION VERIFIED** (2026-08-06).

### What was done
1. **One canonical reader** — new `application/services/position_service.py` (`PositionService`)
   owns every position read: `get_positions_with_broker` (portfolio), `get_user_positions` /
   `get_user_positions_list` (engine — PAPER-run branch via portfolio_manager, else live engine),
   `get_paper_positions` (open-only), `list_all_positions` (admin snapshot + profiles join).
   Each consumer router became a thin adapter; the four historical envelopes are preserved
   byte-for-byte.
2. **Routes rewired** — `v1_engine.py` `/positions`, `v1_paper.py` `/positions`,
   `v1_admin.py` `/admin/positions`, `v1_portfolio.py` `/api/v1/positions` all delegate to
   `PositionService`; the v1_portfolio router is tagged **INACTIVE** (holdings/funds/summary
   still use `portfolio_manager` directly).
3. **Public service contracts kept** — `EngineService.get_positions` (same semantics incl.
   `BrokerTokenExpiredError` propagation + transient-error → `[]`) and `AdminService.
   list_positions` (same dict contract) now delegate to the canonical service; new public
   `EngineService.get_engine_for` accessor reuses the shared engine cache.
4. **Parity tests** — new `tests/test_position_service_parity.py` (11 tests: envelope + path
   parity for all four consumers + service delegation equality); `TestGetPositions` in
   `test_engine_service.py` updated to the delegation contract.

### Verification
- API regression **955 passed, 1 xfailed** (v1.6.5 944/1 → +11, zero failures); imports clean.
- **Production gate PASSED (user-approved)** — 7 files hot-deployed (`position_service.py`,
  `engine_service.py`, `admin_service.py`, `routes/v1_{admin,engine,paper,portfolio}.py`),
  md5-verified in-container, restart clean, health 200.
  - **Byte-parity**: BEFORE/AFTER capture of 12 endpoints (live, paper, admin, funds,
    holdings, engine status) — every status identical; response key-trees identical; only
    allowed diff = `positions[].updated_at` wall-clock refresh. Expired-token admin keeps
    its documented `401 BROKER_TOKEN_EXPIRED`; live admin keeps 2 real positions.
  - **Paper lifecycle (real HTTP path) 6/6**: BUY 5 `NSE:NIFTY50-INDEX` paper → filled
    @ 24653.27 (≈2.2–2.5 s) → position visible → portfolio open=1 → trade recorded →
    SELL 5 → position closed → realised −98.8, equity 500000 → 499901.2.
  - **Monitoring**: 0 Prometheus alerts, api memory 288 MiB stable, 0× 5xx, error log =
    pre-existing yfinance 404 noise only.
  - **Kill switch**: Redis `global:kill_switch` was ENABLED pre-gate (product-wide halt);
    cleared for the paper demo on user approval, then **re-enabled** (prod restored).
  - Report: `07_sprint2_w2_production_verification.md`. Next: Sprint 3 (W6) on approval.

## v1.6.5 (2026-08-06) — Canonical backtest metrics: ONE Sharpe + ONE cost model (Consolidation Sprint 1 / W1)

> Internal consolidation only — no routes, endpoints, response formats, UI or dead-code
> changes (consolidation-sprint constraint: nothing deleted). Deployment = 4 files hot-deployed
> to prod (md5-verified) + restart; PRODUCTION VERIFIED.

### What was done
1. **B1 fixed — one canonical Sharpe across every backtest path.** New
   `backtest.performance.compute_sharpe_ratio(returns)` (sample stdev `n−1`, annualized
   `√252`, `<2` returns → `0.0`). `PerformanceAnalytics` now calls it; the **legacy `/run`
   engine** (`engine/backtest.py`) previously used population stdev over per-trade PnL —
   a unit-mismatched ratio diverging from run-v2/v3 — and now computes
   `compute_sharpe_ratio` over the same equity-curve period returns as run-v2/v3. Removed the
   now-unused per-trade `_returns` list (internal, not an API).
- **B2 fixed — one canonical fee implementation.** Legacy `/run` cost math was a flat
   4-component approximation (slippage+brokerage%+STT%+exchange%) that never matched the
   segment-aware `estimate_cost` model run-v2/v3 use. `BacktestEngine._apply_costs` now routes
   through canonical `estimate_round_trip` (`EQUITY_INTRADAY`, `commission_min=0.0`,
   legacy knobs → `BacktestCostConfig` overrides). Same trade → identical fees on `/run`,
   run-v2 and run-v3 (includes stamp-duty/GST/SEBI the flat math omitted). `paper/fill_engine`
   `_build_fill` also routes through `estimate_cost` with `gst_enabled=False,
   sebi_fees_enabled=False` to keep paper fills **byte-identical** to their historical math.
3. **New parity suite `tests/test_backtest_consolidation.py` (10 tests)** — legacy-Sharpe ==
   `compute_sharpe_ratio` == `PerformanceAnalytics`, sample-vs-population guard, `<2` → `0.0`,
   legacy cost == `estimate_round_trip`, stamp-duty leg placement, paper-fill parity.

### Verification
- API regression **944 passed, 1 xfailed** (baseline 934/1 → +10, zero failures).
- **Prod deploy + smoke (in-container, real auth) — 13/13 PASS:** `POST /backtests/run` 200,
  payload keys unchanged, equals `POST /backtests/` exactly (sharpe/trades/pnl identical);
  `run-v2` 200 (sharpe −4.2, 38 trades); `GET /{run_id}` fee parity **38/38**
  (`cost_total == slippage+charges+taxes`, e.g. 2282.58 = 0.0+1150.55+1132.03); JSON export
  200; paper fills byte-identical for zero-fee and fee-bearing configs. Logs clean (0
  non-baseline errors, 0 5xx in 15min; only pre-existing marketdata 503s/Yahoo noise).

## v1.6.4 (2026-08-06) — Housekeeping: dead admin endpoint fixed, lint wired, log noise swept

> Health-check pass (tests/tsc/lint/prod probes). No features — aligns with the freeze.

### Fixed
- **`GET /api/v1/admin/strategies/all-user`** — the admin "User Strategies" tab always showed
  "No user strategies found" because the route was never registered (KNOWN_ISSUES #15).
  The existing `AdminService.list_all_user_strategies` now maps rows for the UI
  (`type` from `strategy_type`, `is_active` from `status`), and the route is registered with
  `require_admin` + optional `?user_id=` filter. 3 new tests.
- **`apps/api/core/cache.py`** — replaced deprecated `setex()` with `set(..., ex=ttl)`.
- **`apps/api/brokers/sdk/certification.py`** — `health()` probe no longer creates a discarded
  coroutine (`asyncio.iscoroutine(adapter.health())` → `inspect.iscoroutinefunction`).
- **`apps/api/tests/test_squareoff_service.py`** — scheduler tests close the discarded
  `_squareoff_loop` coroutine (kills the "never awaited" RuntimeWarning).
- **ESLint wired** — `apps/web/.eslintrc.json` (`next/core-web-vitals`) + `eslint@8` +
  `eslint-config-next@14.1.0`; `next lint` now runs non-interactively. Fixed the 17
  `react/no-unescaped-entities` errors (straight quotes → typographic) across
  `ai/page.tsx`, `dashboard/admin-content.tsx`, `onboarding/page.tsx`, `portal/page.tsx`,
  `portfolio/page.tsx`. 35 pre-existing `react-hooks/exhaustive-deps` warnings left as-is
  (deliberate omissions; not fixing to avoid behavior changes).
- **Docs** — INCIDENTS.md: INC-007 (watchlist, now in Workspace), INC-009 (MARKET price
  validation, conditional since v1.5.9), INC-010 (no duplicate content-types — verified on
  the live schema) marked Resolved with evidence. KNOWN_ISSUES #15 marked Resolved.

### Verification
- API regression **934 passed, 1 xfailed** (+4 tests; warnings 76 → 9, remaining are
  background-poll task teardown artifacts in HTTP-flow tests, not production code).
- Web `tsc --noEmit` clean; `next lint` 0 errors (35 warnings).
- `git push` of the previously-unpushed v1.6.1–v1.6.3 commits (local was 4 ahead of
  `origin/main` — a future VPS `git reset --hard origin/main` would have dropped them).

## v1.6.3 (2026-08-05) — Beta analytics: `is_auth` split so DAU/bounce/funnel are trustworthy (v1.6.2 follow-up)

> Evidence-backed (W32 reports 06/07/08/10 — DAU/bounce/cohort numbers were inflated by
> anonymous sessions and smoke traffic). Small, additive; no features.

### Changed
- **`apps/web/lib/analytics.ts`** — `is_auth` injected into EVERY queued event at flush time
  (client auth state resolved via `useAuth`), so `session.start` / `page.view` / clicks all
  carry it; unknown until auth resolves (then server truth wins anyway).
- **`apps/web/components/analytics-tracker.tsx`** — now reads `useAuth()` and syncs
  `setAnalyticsAuthState`; mounted INSIDE `Providers` (`app/layout.tsx`) so the context is
  available (was rendered outside).
- **`apps/api/routes/v1_analytics.py`** — `track-batch` resolves identity via proper FastAPI
  DI (`Depends(get_optional_user)` — previously called manually with `credentials=None`, so
  only the cookie branch ever ran) and sets `properties.is_auth = bool(user_id)` server-side
  as the authoritative value.

### Verification
- Regression **930 passed, 1 xfailed** (3 new route-level tests: signed-in true, anonymous
  false, non-dict properties untouched). Web tsc + prod build clean.
- Prod wire probe (in-container, real HTTPS): anonymous batch → `is_auth=false` + no
  user_id; signed-in batch (`fa668109`) → `is_auth=true` + user_id persisted. Confirmed in
  `analytics_events`. API redeployed (health 200), web `.next` deployed (BUILD_ID
  `dyvmbDSGyGqOqcTjXxdgV`), probe rows/files cleaned.

## v1.6.2 (2026-08-05) — BETA LAUNCH SUPPORT W32: weekly intelligence cycle + risk-audit persistence (ops-only)

> Beta Launch Support week 1: evidence collection cycle established. Full W32 evidence
> suite authored in `docs/weekly/2026-W32/` (01-product-health → 13-next-week-priorities)
> from live Supabase analytics, Prometheus and container logs.

### Ops fixes shipped (evidence-backed, feature freeze respected)
- **`risk_audit_log` migration applied to prod** — `20260804_01600_risk_audit_log.sql`
  (`CREATE TABLE IF NOT EXISTS` + index) executed on remote Supabase; PostgREST schema
  reloaded (`NOTIFY pgrst, 'reload schema'`); `rest/v1/risk_audit_log` returns 200. Closes
  KNOWN_ISSUES #14 [Action required]: emergency-stop audit writes no longer hit PGRST205
  and no longer fall back to `audit_log`. Zero code changes (DDL only).
- **Feedback store cleaned** — the 9 `E2E prod-readiness test — please ignore` rows (all
  `prtest*` users, 2026-08-02) marked `wontfix` + notes via PostgREST PATCH, so the W33
  feedback dashboard counts only real user reports.
- **Known issue triage** — KNOWN_ISSUES #14 resolved; #1 (token cycle) mitigated by the
  auto-refresh cron + INC-016; INC-015/016/017 closed (already shipped `fd896ca`).

### Evidence findings (see docs/weekly/2026-W32/)
- Backtest runs 2 → 38 (5 users), builder strategies 7 → 20, accounts 26 → 31; requests
  50,390 → 101,600 with p95 latency *improving* (API 0.249s).
- 0 container restarts; fyers breaker 2 → 0 OPEN; client errors 20 → 0 since the 08-03
  chart color-parse fix (verified in current build).
- Top open items: broker-step activation (13% connect), `/alerts/` poller 429s (610/7d),
  `async_safe_single` None log noise (653×/48h), `strategy_runs` 22P02 schema debt.

### Verification
- Migration: table + 6 columns present, PostgREST 200 on the table, `NOTIFY` sent.
- Feedback: 9 rows returned `wontfix` with notes from the PATCH response.
- No API/web code changed; health 200 (no redeploy required).

## v1.6.1 (2026-08-05) — BACKTEST ENGINE PHASE D: Trade Intelligence (interactive trade learning)
> Phase D of the institutional backtest roadmap (A/B/C/D). **Transforms every completed
> trade in `apps/web/app/backtest/page.tsx` into an interactive learning object** — click
> any trade (trades table row or the Overview equity-curve E/X marker) and a **Trade
> Intelligence** panel opens: a real candlestick price chart (candles from the same durable
> store the backtest used via `GET /backtests/candles/{symbol}/{interval}?days=`) with
> **Entry/Exit markers** and **SL/Target price lines**, a crosshair tooltip (PnL, RR, risk
> amount, signal reasons, charges/taxes/slippage/cost, risk state incl. drawdown at entry
> and capital remaining), **Replay from entry candle** (client-side step-through starting
> exactly at the entry candle), and **Prev Trade / Next Trade / Jump to Max Drawdown /
> Jump to Best / Jump to Worst**.
>
> **Constraints honoured** — visualization only: analytics and execution engine untouched
> (backend **zero** diffs), no duplicate calculations (SL is a display-level inverse of the
> persisted `risk_amount = |entry − stop| × qty`; target is honoured only when the trade
> exited via a target/LIMIT fill — `exit_reason`), all other values read straight from the
> existing run payload. Data limits surfaced honestly in the UI: SL line appears only when a
> resting stop existed (`risk_amount > 0`); per-candle indicator snapshots are not persisted
> so the signal context is shown via entry/exit reasons.

### Added
- **`apps/web/app/backtest/page.tsx`** — `TradeChart` (lightweight-charts v5:
  `CandlestickSeries` price chart, `createSeriesMarkers` entry/exit markers + animated
  replay cursor, `createPriceLine` dash lines for SL/Target, crosshair tooltip, viewport
  auto-centred on the entry candle, ResizeObserver); clickable trade rows (highlight) +
  toolbar (Prev/Next/Max Drawdown/Best/Worst); `Trade Intelligence` panel (12 detail cards
  + signals card + chart + replay control); `BacktestChart` gained trade-click → trades tab;
  `BTTrade` extended with the already-shipped enriched fields; `BTCandle`/`TradeView` types;
  `candleTime`/`nearestCandleIdx` helpers. Candles fetched once per run with the run's
  `config.days` window (`api.backtest.candles`), cached across trade selections.

### Changed
- **`apps/web/app/backtest/page.tsx`** — trades table adds RR column + selected-row
  highlight; Overview equity chart markers are clickable ("Click an E/X marker to inspect
  that trade").

### Verification
- Web `tsc --noEmit` clean; prod build clean (BUILD_ID `iia71_nq1kK2DYPZhdi9P`).
- Full API regression (backend untouched): **915 passed, 1 xfailed**.
- Deployed (`.next` swap into `trademetrix_web`, stopped-container `docker cp`, `chown -R
  1001`); `✓ Ready`, `/backtest` 200 in-container + public, new page chunk served.
- Prod smoke (puppeteer, fresh user, `p0e2e/e2e-trade-intel.js`): **12/12 OK** — run
  renders → Trades tab → click row 0 opens Trade Intelligence 1/3 with real candles →
  SL price line derived → detail cards (charges/RR/signals) → crosshair tooltip shows
  P&L/RR/charges/risk → Replay toggles and steps from the entry candle → Best→3/3,
  Worst→2/3, Max Drawdown→2/3, Next→3/3 → zero console/page errors. Smoke users swept.

## v1.6.0 (2026-08-05) — BACKTEST ENGINE PHASE C: risk-aware backtest reports (risk analytics in the UI)

> Phase C of the institutional backtest roadmap (A/B/C). **Surfaces Phase B's
> `risk_analytics` in the Backtest Engine report UI** — a new **Risk** tab (visible only
> when `risk_enabled=true`) shows why the simulation rejected orders and how capital/
> exposure/drawdown evolved, so a rejected run is diagnosable at a glance. Risk-off runs
> render byte-identical (tab hidden). No OMS / Broker Layer / Execution Engine changes.
>
> Wire budget: the persisted `BacktestResult.risk_analytics` stays exact (full timeline,
> curves, per-order rejections), but the payload/`GET /{run_id}` surface now budgets it the
> same way trades and the equity curve are budgeted — timeline/capital/exposure curves
> LTTB-downsampled to 2000 points (first/last preserved), per-order rejections capped at
> 200 with a `rejections_truncated` flag. `RiskAnalytics.rejections` (additive, persisted)
> carries the full per-order rejection records (rule, reason, capital/risk remaining,
> drawdown, exposure, timestamp/symbol/side/qty/price).

### Added
- **`apps/web/app/backtest/page.tsx`** — `RiskChart` (lightweight-charts: capital-remaining
  line, exposure area, drawdown% line, crosshair tooltip) + **Risk tab**: KPI cards
  (accepted / rejected / circuit halts / rules fired), "Rejections by Rule" bar chart,
  "Risk State Over Time" chart, and a **Rejected Orders** table (time, symbol, side, qty,
  price, rule chip, reason, capital remaining, risk remaining (`∞` when unlimited),
  drawdown%, exposure) with truncation notice; `BTRiskAnalytics` types; conditional tab.
- **`apps/api/routes/v1_backtest.py`** — `_payload_risk()` (LTTB downsample of
  timeline/capital_curve/exposure_curve at `PAYLOAD_MAX_RISK_POINTS=2000`, rejection cap
  `PAYLOAD_MAX_REJECTIONS=200` + `rejections_truncated`) applied to run-v3 `_result_payload`
  and `GET /{run_id}` (risk-off passthrough unchanged).
- **`apps/api/backtest/models.py`** — `RiskAnalytics.rejections: list[RiskRejection]`
  (additive, persisted in `backtest_runs.summary`; old rows default empty).

### Changed
- **`apps/api/backtest/risk.py`** — `analytics()` now includes `rejections=list(self._rejected)`
  (was only counts/reasons/curves).

### Verification
- **7 new tests** (`tests/test_backtest_risk_payload.py`): curve downsample >2000 (first/
  last preserved, monotonic), passthrough below threshold, risk-off passthrough, rejection
  cap + flag, enabled wire shape, route-level `GET /{run_id}` budget + risk-off passthrough.
- Full suite **915 passed, 1 xfailed** (908 baseline + 7). Web `tsc` clean, prod build
  clean (BUILD_ID `q-Eff63YJmQe0dbJva2B6`).
- Prod smoke **25/25** (user fa668109, ema_crossover, NIFTY 5m/60d = 3101 candles): risk OFF
  212 trades; risk ON `max_trades_per_day=3` → 3 trades, accepted 6, **418 rejections** all
  `MAX_TRADES_PER_DAY` ("Trade count 3 exceeds daily limit 3."), halts 0; 3101-point curves
  downsampled to exactly **2000** (first index 0 / last 3101 preserved); rejections capped
  418→**200** with `rejections_truncated=True`; full payload fields incl. `risk_remaining
  -1.0` NO_LIMIT sentinel; `GET /{run_id}` persisted with the same budgeted shape.

## v1.5.11 (2026-08-05) — BACKTEST ENGINE PHASE B: simulated risk engine (risk_enabled=true fixed)

> Phase B of the institutional backtest roadmap (A/B/C). **Fixes the
> `risk_enabled=true → 0 trades` incident**: backtest orders were being evaluated by the
> LIVE Risk Engine dry-run, which read live state (Supabase orders queries, Redis kill
> switch, market status) for a `backtest:<hex>` pseudo-user — fail-closed defaults
> (`kill_switch_enabled=True`) rejected every order. Backtests now run a **simulated risk
> engine** (`backtest/risk.py`) that reuses the shared Risk Engine vocabulary
> (`RiskConfig` extended, `RiskDecision`, `RiskRuleType`) but evaluates orders against the
> SIMULATED account only (BacktestBroker equity/cash/positions/realized P&L). No live
> broker/OMS/DB/market-state access.
>
> Simulated rules (mirroring live semantics): position sizing (`max_risk_per_trade_pct`
> clamps opening quantity), max capital, max exposure, max symbol exposure, max open
> positions, max quantity, max trades/day, daily loss limit, daily profit target (warning),
> max drawdown, circuit breaker (halts remaining orders after a daily-loss/drawdown
> breach — simulated kill switch), kill switch + emergency stop config flags.
> Deliberately NOT simulated: broker auth, market-open validation, trading window, live
> margin API, broker connectivity, OMS queue state, duplicate/cooldown/rate rules.
>
> Every rejected order carries: reason, rule triggered, capital remaining, risk remaining,
> drawdown, exposure. `BacktestResult.risk_analytics` (additive) exposes accepted/rejected
> trades, rejection reasons, halt count, risk timeline, capital curve, exposure curve.
> Configurable via new `BacktestConfig.risk` dict; capital-derived institutional defaults
> (10% daily loss, 25% drawdown, 5× exposure, 10 open positions) guarantee risk ON never
> zeroes a healthy run. Constraint honored: OMS / Broker Layer / Execution Engine / Public
> APIs unchanged (one additive `BacktestBroker.last_price/last_time` accessor only); no new
> UI, reports unchanged; legacy `/run` payload unchanged.

### Added
- **`apps/api/backtest/risk.py` (new)** — `BacktestRiskConfig(RiskConfig)` with
  backtest-only knobs (`max_risk_per_trade_pct`, `circuit_breaker`); `BacktestRiskCheck`;
  `BacktestRiskSimulator` (per-run, broker-only state reads): `check()` rule chain,
  `snapshot()` per-candle risk timeline, `analytics()`, rejection records with the full
  payload contract; `NO_LIMIT` sentinel for unlimited risk budget.
- **`apps/api/backtest/models.py`** — `BacktestConfig.risk: dict` (rule overrides);
  `RiskRejection`, `RiskTimelinePoint`, `RiskCurvePoint`, `RiskAnalytics` models;
  `BacktestResult.risk_analytics` (additive, default empty).

### Changed
- **`apps/api/backtest/manager.py`** — `_place_via_broker` gates orders via
  `BacktestRiskSimulator.check()` (with quantity clamping) instead of the live
  `risk_manager.evaluate(dry_run=True)`; `run`/`_fast_run` build the simulator when
  `risk_enabled` and attach `result.risk_analytics`; `_collect_snapshot` records risk
  timeline points; replay path passes `risk_sim` through.
- **`apps/api/backtest/replay_engine.py`** — `run(..., risk_sim=None)`: simulator path
  replaces the live risk dry-run when provided; live `risk_manager` path kept as legacy
  fallback for external callers.
- **`apps/api/backtest/execution.py`** — additive `last_price(symbol)` / `last_time()`
  accessors on `BacktestBroker` (risk sim price source).

### Verification
- **25 new tests** (`tests/test_backtest_risk_sim.py`): rule semantics, rejection payload
  contract, sizing clamp + reducer exemption, circuit-breaker halt, kill/emergency-stop
  config, analytics shape, risk-off parity + risk-on-never-zero + tight-limit reduction at
  the manager level, replay-path simulator use, broker-level sized fill.
- Full suite **908 passed, 1 xfailed** (883 baseline + 25).

## v1.5.10 (2026-08-05) — BACKTEST ENGINE PHASE A: enriched TradeRecords, big-run performance (equity downsampling + trade pagination), interactive charts

> Phase A of the institutional backtest roadmap (A/B/C). TradeRecords now carry the full
> audit trail — entry/exit reasons, per-side slippage/charges/taxes/cost totals, risk amount
> and R-multiple — without breaking any existing payload (all new fields defaulted). Big runs
> (>2k trades, >2k equity points) no longer produce monolithic payloads: equity is
> downsampled server-side (LTTB, first/last preserved) and trades are cursor-paginated. The
> backtest UI swaps static SVG equity/drawdown for interactive `lightweight-charts` canvases
> (crosshair tooltip + entry/exit markers).
>
> Constraint honored: additive changes to the backtest module only — OMS, Risk Engine, Broker
> Layer, Execution Engine untouched; legacy `/run` payload unchanged and backward compatible.

### Added
- **`apps/api/backtest/models.py`** — `TradeRecord` extended with `entry_reason`,
  `exit_reason`, `slippage`, `charges`, `taxes`, `cost_total`, `risk_amount`, `rr` (all
  defaulted for backward compatibility).
- **`apps/api/backtest/execution.py`** — `BacktestBroker._apply_fill` rewritten to open
  records with the signal reason, split entry/exit costs per side, consume entry costs
  proportionally on partial closes (`_consume_entry_costs`, `_clear_entry_state`), and map
  the exit type to a reason (`_exit_reason`: SL/SLM→stop, LIMIT→target, MARKET/signal→
  signal, close_on_end). `_record_trade` computes per-trade slippage, charges
  (brokerage+exchange_tc), taxes (STT+stamp+GST+SEBI), cost_total, `risk_amount`
  (from any resting SL trigger on the symbol at close), and `rr = pnl/risk_amount`.
  Added `total_slippage` property (reset in `__init__`/`update_config`/`reset`).
- **`apps/api/backtest/manager.py`** — `_place_via_broker` sets `order.reason` from the
  signal reason before the risk dry-run; reason threaded through the MAX loop, `_fast_run`
  and `close_on_end` (`_make_close_order(..., reason="close_on_end")`).
- **`apps/api/backtest/replay_engine.py`** — copies `signal.reason` onto orders when empty.
- **`apps/api/backtest/performance.py`** — `downsample_pairs(points, threshold=2000)` LTTB
  (largest-triangle, keeps first/last); `PerformanceAnalytics.calculate(..., max_equity_points)`
  downsamples `equity_curve` after computing ratios/returns (so KPIs stay exact).
- **`apps/api/routes/v1_backtest.py`** — new `GET /backtests/{run_id}/trades?cursor&limit`
  (cursor-paginated, limit clamped 1–2000); `_result_payload` + run-v2 cap trades at
  `PAYLOAD_MAX_TRADES = 2000` with a `trades_truncated` flag via shared `_payload_trades`/
  `_payload_equity` helpers; restored `export_backtest` signature.
- **`apps/web/app/backtest/page.tsx`** — `BacktestChart` (lightweight-charts `LineSeries`,
  `CrosshairMode` tooltip, `createSeriesMarkers` entry/exit markers) replaces the static SVG
  charts for Equity Curve and Drawdown %.

### Verification
- New tests: enriched trade fields (entry/exit reasons, cost breakdown, duration, model),
  risk/RR from a resting SL, `downsample_pairs` endpoint + shape preservation + full-series
  KPI accuracy, pagination route (clamp, cursor walk, past-end, 404). Suite **883 passed,
  1 xfailed** (was 873). Web `tsc` clean, prod build clean.
- Prod smoke (user `fa668109`, in-container): run-v3 EMA Crossover on `NSE:NIFTY50-INDEX`
  60d/15m, risk off → **57 trades**, all enriched keys present, cost consistency
  (cost_total = slippage+charges+taxes), pagination `total=57 / len=3 / next_cursor=3`;
  1026 equity points served. Backend hot-deployed (6 files, health 200); web `.next`
  deployed (new BUILD_ID, `/backtest` 200, chart bundle served).
- Note: backtests run with `risk_enabled=True` can yield 0 trades because the risk dry-run
  (`risk_manager.evaluate(dry_run=True)` in `_place_via_broker`) rejects backtest orders —
  pre-existing behavior, unrelated to Phase A. Run with risk off (as the UI's default during
  this phase) to exercise trades.

## v1.5.9 (2026-08-04) — BACKTEST DATA + P&L HONESTY: real candles, correct trade attribution

> Backtest hand-check revealed two production defects, both on the legacy and manager run
> paths: (1) `fetch_historical_data` called fyers directly and, when fyers failed (which it
> always does from the container — WAF 403 on `/data/history`, plus a wrong-URL 404 and a
> read-only `fyersApi.log` SDK fallback), it silently returned synthetic candles; the legacy
> `/run` route ran on fabricated data. (2) `build_trades_from_snapshots` priced SHORT entries
> from `average_buy_price` (0.0 for shorts) → entry ₹0 → one PnL of −1.8M per short. And the
> durable candle store returned a partial slice whenever it had ≥2 candles (a 7-day request
> got ~3 days) without topping up.

### Changed
- **`apps/api/engine/backtest.py`** — `fetch_historical_data` now routes through
  `backtest_historical.load` (durable store → broker → Yahoo); synthetic candles remain only
  as a clearly-logged last resort, never when real data exists. Removed dead
  `_map_to_fyers_symbol`/`_resolve_fyers_interval`/`_candle_to_dict` helpers.
- **`apps/api/backtest/historical.py`** — `load` is now **coverage-aware**: refetches +
  merges when the stored slice doesn't span the requested window (trading-day tolerance for
  the 09:15 IST session open), instead of returning a stale partial store.
- **`apps/api/backtest/performance.py`** — `build_trades_from_snapshots` prices SHORT entries
  from `average_sell_price` and LONG from `average_buy_price` (matches the new per-side
  `get_positions`), so short P&L is correct.
- **`apps/api/backtest/execution.py`** — `BacktestBroker` now tracks a position's `entry_time`
  (open candle) and threads it through `_record_trade`, so Trades show real open→close times
  instead of the close candle for both walls.
- **`apps/api/backtest/manager.py`** — `run` builds Trades from `broker.trades` (authoritative
  fill-level records) instead of lossy snapshot reconstruction when available; snapshots use
  the candle timestamp, not wall-clock; `total_fees` is populated from `broker.total_costs`
  (was dead 0.0 — return% is cost-inclusive, `net_pnl` is gross, so the gap was invisible).
- **`apps/api/brokers/fyers_adapter.py`** — SDK history fallback writes to `/tmp/` instead of
  `/app/fyersApi.log` (Errno 13 → SDK fallback always failed).

### Verification
- New tests: legacy fetch → durable store (no synthetic when real data exists); synthetic
  only when the store is empty; coverage-aware refetch+merge; short/long trade attribution
  prices; broker `entry_time`/`exit_time`. Suite **873 passed, 1 xfailed** (was 867).
- Prod probes (user `fa668109`): durable loader now returns a full range (125 real candles for
  a 7-day/15m window across 5 sessions, close range 24178–24774). Manager `trend_rider` on
  `NSE:NIFTY50-INDEX` 30d/15m: 550 candles, 9 trades, real entry → exit timestamps
  (2026-07-07 → 2026-07-10 etc.), and full reconciliation
  `net_pnl + total_fees = equity change` (e.g. qty1: −152.75 + 555.47 = −708.22). Legacy
  `/run` 200 with 550 real candles analyzed (0 trades on trend_rider 15m/7d is a legit
  no-crossover window; oversized qty rejects BUYs over capital — both correct engine behavior).
- Hot-deployed (7 files, health 200).

## v1.5.8 (2026-08-04) — BROKER-FIRST MARKET DATA: real LTP/change% for compact option symbols

> Follow-up to v1.5.7: positions now show real P&L, but LTP/Chg% still came from Yahoo only.
> `/marketdata/quote` bypassed the broker entirely — Yahoo can't resolve the fyers compact
> option format (`SENSEX2680679000CE`, `NIFTY2680424450PE`), so those positions showed `—`
> instead of live prices. Market data now comes from the broker.

### Changed
- **`apps/api/routes/v1_marketdata.py`** — `GET /marketdata/quote` is now **broker-first**:
  resolves the user's active broker and calls the adapter's `get_quotes` (fyers REST
  `/data/quotes`; reuses the running feed adapter via `shared_socket.get_broker_adapter`, else
  the cached `EngineService` engine). Symbols the broker can't price fall back to Yahoo
  per-symbol. No broker → pure Yahoo (unchanged).
- **`apps/api/brokers/fyers_adapter.py`** — `_ensure_fyers_symbol` and `_ws_symbol` now use a
  `BSE:` prefix for SENSEX underlyings (was hardcoded `NSE:` → BSE symbols couldn't be quoted
  or WS-subscribed); `_normalize_quote` preserves `Exchange.BSE` from the symbol prefix.
- **`apps/api/engine/executor.py`** — `ExecutionEngine.get_quotes(symbols)` delegate.
- **`apps/api/market/data_socket.py`** — `get_broker_adapter(broker_type)` accessor.

### Verification
- New tests: broker-first with Yahoo fill (mixed batch → fyers + yahoo quotes by symbol),
  full Yahoo fallback (no broker data), BSE prefix in `_ensure_fyers_symbol`/`_ws_symbol`.
  **867 passed, 1 xfailed**.
- In-container route probe (user `fa668109`): `SENSEX2680679000CE` → `last 106.5 close 206.95
  broker fyers` (real position LTP), `NSE:NIFTY50-INDEX` → `24614.9 / 24774.3 broker fyers`,
  `NIFTY2680424450PE` → `0.1 / 18.35 broker fyers` (closed position — UI uses realised P&L).
- Hot-deployed (4 files, `docker cp` + restart, health 200), pushed `eb4f7d3`.

## v1.5.7 (2026-08-04) — POSITIONS 0.00 FIX: map fyers v3 position fields (real root cause)

> Follow-up to v1.5.5/v1.5.6: the portfolio/terminal positions still showed **0.00** P&L and
> empty averages even for *today's* real trades. Root cause was **backend**: the fyers v3
> `/api/v3/positions` API renamed its fields — `avgBuyPrice/avgSellPrice/unrealised/realised`
> are **null in v3**; the real data lives in `buyAvg/sellAvg/pl/realized_profit/
> unrealized_profit/netQty`. `FyersAdapter._normalize_position` read the null v2 names → every
> live position normalized to `quantity 0 / avg 0.0 / pnl 0.0` (proved via raw in-container
> probe of the v3 payload, user `fa668109`). The v1.5.6 frontend guard was necessary but not
> sufficient — this closes the loop at the source.

### Fixed (`apps/api/brokers/fyers_adapter.py`)
- **`_normalize_position`** — reads v3 fields with v2 fallbacks: `buyAvg`→`average_buy_price`,
  `sellAvg`→`average_sell_price`, `netQty`→`quantity`; `unrealised_pnl` = `unrealized_profit`
  (fallback `pl` for open positions), `realised_pnl` = `realized_profit` (fallback `pl` for
  closed positions), `m2m` = `pl`. Previously all `avgBuyPrice`-style names → zeros.
- **Exchange preserved** — `BSE:`-prefixed symbols now map to `Exchange.BSE` (was hardcoded
  `Exchange.NSE` + prefix dropped, so BSE options lost their exchange).
- **Product mapped** — `productType` `MARGIN` → `ProductType.NRML` (was hardcoded INTRADAY).
- **`_parse_instrument` compact options** — fyers v3 compact symbols (`NIFTY2680424450PE` =
  yymdd + strike, `SENSEX2680679000CE` = strike 79000, expiry 2026-08-06) now parse to
  `OPT`/strike/expiry instead of falling to EQ. Alpha format (`NIFTY26AUG24450CE`) unchanged.

### Verification
- New tests `tests/test_broker_fyers.py`: `test_get_positions_v3_fields` (open MARGIN + closed
  BSE position with real v3 payload → avg 116.1 / realised 2915.25 / NRML / OPT / strikes /
  expiry) + `test_parse_instrument_compact_numeric_options` — **15 passed**; full suite
  **864 passed, 1 xfailed** (+2).
- Hot-deployed to prod API (`docker cp` + restart, health 200); in-container probe via
  `_authenticate_adapter` → **5 real positions**: open `SENSEX2680679000CE` qty 20 avg 116.1
  unrealised −192, closed `NIFTY2680424500PE` realised +2915.25, `NIFTY2680424600CE` −575.25,
  `SENSEX2680677500PE` −884, `NIFTY2680424450PE` −1287 — matches fyers `overall`
  (`pl_realized 169 / pl_unrealized −192`).
- `/engine/positions` route probe → same real values (BSE exchange, NRML, OPT metadata).
- Browser smoke on prod (puppeteer, mocked real payload shapes): open position shows **−192**
  unrealised (not 0.00), closed shows **+2915.25** / **−575** realised, Unrealised·Realised
  totals present, 0 console errors — **7/7 OK**. Smoke user (`tmv3*`) deleted.

## v1.5.6 (2026-08-04) — PORTFOLIO 0.00 FIX: fall back to broker P&L when no live quote

> Follow-up to v1.5.5: the portfolio/terminal positions still showed **0.00** P&L for symbols
> the live quote cannot price. Root cause: the quote poll returns `last_price: 0` for symbols
> Yahoo can't resolve (custom option formats like `SENSEX2680677500PE` / `NIFTY2680424450PE` —
> confirmed via in-container probe: `/marketdata/quote` → `{last_price:0, close:0}`), and
> `positionQuote` treated that as a *valid* quote → P&L computed `qty × (0 − avg) = 0.00`
> instead of using the broker's `unrealised_pnl`. **A quote/tick is only valid when
> `last_price > 0`.** Also hardened the Today's P&L `unrealisedPnl` memo to the same rule.

### Fixed
- **`apps/web/app/portfolio/page.tsx`** — `positionQuote` and the `unrealisedPnl` memo now
  require `last_price > 0` before treating a tick/quote as authoritative; otherwise fall back
  to the position's own `unrealised_pnl` / `realised_pnl`.
- **`apps/web/app/terminal/page.tsx`** — identical guard for `positionQuote` and
  `quoteForTicket` (terminal had the same latent bug for zero-quotable symbols).

### Verification
- In-container probe (user `fa668109`): `/engine/positions` → 5 rows all in the
  `SENSEX2680677500PE`-style format with `quantity:0 avg:0 pnl:0`; `/marketdata/quote` returns
  `last_price 0 / close 0` for all 5 → previously rendered as P&L 0.00.
- Browser smoke on prod (puppeteer, mocked zero-quote positions): open position with broker
  `unrealised_pnl=+500` shows **+500** (not 0.00), closed position shows +500 realised,
  no fabricated `+0%`, 0 console errors — **5/5 OK**.
- Web `tsc` + `next build` clean; deployed `.next` (BUILD_ID `wn34X_4_dOkAyST4mlg6Y`),
  `/portfolio` + `/` 200. Smoke user (`tmzero*`) deleted.
- API untouched (862 passed, 1 xfailed baseline).

## v1.5.5 (2026-08-04) — PORTFOLIO: rich positions (open + closed today) + trade history

> Beta feedback fix (allowed under feature freeze): the portfolio page only showed a minimal
> Open Positions table (symbol/qty/avg/LTP/P&L) with no closed-positions view, no per-position
> buy/sell detail, no change% / P&L% columns, and no trade history. Everything needed was already
> returned by `/engine/positions` (`buy_quantity/sell_quantity/average_sell_price/realised_pnl/
> m2m`) and `/engine/orders` (filled orders) — **frontend-only change**, same data sources the
> terminal already used.
> - **Positions panel** — upgraded to the terminal's rich layout: split into **Open Positions**
>   (Symbol/Qty/Buy/LTP/**Chg%**/Unrealised P&L + pnl%) and **Closed Today** (Buy Qty/Avg Buy/
>   Avg Sell/Realised P&L), with an Unrealised · Realised total in the panel header. Live change% /
>   LTP come from the WS tick first, else a 5s quote poll of the position symbols (`usePolling`),
>   else the broker's own P&L fields.
> - **Trade History panel (new)** — the 20 most recent **executed (FILLED)** orders: Symbol/Side/
>   Qty/Price/Time with an executed-count in the header. Recent Orders (all statuses) kept below it.

### Changed
- **`apps/web/app/portfolio/page.tsx`** — extended `Position` interface (buy/sell qty, avg sell,
  realised pnl, m2m); added `TickData`/`usePolling` imports, `QuoteData` state, position-symbol
  WS subscription, `refreshQuotes` + `positionQuote` helpers; split positions open/closed; new
  Trade History table of FILLED orders.

### Verification
- Web `tsc --noEmit` clean; `next build` (`.env.production`) clean.
- Browser smoke on prod (puppeteer, real signup, mocked `/engine/positions` + `/engine/orders`
  via fetch override — new rows flow through the same react-query hooks): **18/18 OK** —
  Positions (3): Open (2) header + rows `NIFTY50-INDEX`/`RELIANCE-EQ`/`NIFTY26AUGFUT`, Closed
  Today (1), chg% column (`-0.32%`), pnl% cell, realised `+6000` on the closed row; Trade
  History "2 executed" with BUY + SELL fills; Recent Orders PENDING + PAPER badge intact; 0
  console errors (only the known anonymous `/auth/me` 401 filtered).
- Deployed web `.next` tar → stopped container → `chown -R 1001` → restart: `✓ Ready`,
  `/portfolio` + `/` 200, new BUILD_ID served. Smoke user (`tmport*`) + 4 leftover
  `tmchgpct*` test users deleted from GoTrue.
- API untouched (862 passed, 1 xfailed baseline unchanged).

## v1.5.4 (2026-08-04) — FEED FIX: real change% on every tick + live streaming for typed symbols

> Beta feedback fix (allowed under feature freeze): the terminal's change% showed **0.00** for
> symbols with live ticks (price moved, percentage never did). Two root causes, both on the
> backend feed path — one line of code and one wiring gap:
> 1. **Fyers data socket ran in `litemode=True`** — the payload is stripped to just
>    `{ltp, symbol}`. `_parse_sdk_tick` read `ch`/`chp` → always `0.0` → every relayed tick
>    carried `change_pct: 0.0` regardless of symbol. Flipped to full mode: ticks now carry real
>    `change`, `change_pct` (and bid/ask/oi/prev_close/open/high/low).
> 2. **Typed symbols were never streamed** — `/feed/start` subscribes only the fixed MAJOR list,
>    so user symbols (e.g. `NSE:NIFTY26AUGFUT`, `NSE:NIFTY26AUG25000CE`) never produced ticks and
>    the Yahoo quote fallback returns 0/0 for futures/options. WS `subscribe` now extends the
>    running fyers feed (`subscribe_symbols` keeps the reverse name map + subscribed list in sync;
>    short retry loop while the SDK socket connects).

### Fixed
- **`apps/api/brokers/fyers_adapter.py`** — `litemode=False` in `FyersDataSocket` (was silently
  stripping every field except ltp); new `subscribe_symbols()` returning still-pending symbols
  (symmetric to the existing `unsubscribe_symbols`).
- **`apps/api/market/data_socket.py`** — `SharedDataSocket` now registers the **inner** adapter
  (not the `CircuitBreakerBroker` wrapper, which doesn't forward privates); new `add_feed_symbols`
  + `feed_has_ws` (retries while a fyers socket is expected, i.e. token present).
- **`apps/api/routes/v1_marketdata.py`** — WS `subscribe` action extends the running fyers feed
  with the client's symbols (up to 10s, bounded).
- **`apps/web/app/terminal/page.tsx`** — belt-and-braces: prefer the live tick's `change_pct`;
  only fall back to the quote poll when the tick lacks change data.

### Verification
- Prod WS probe (API-minted token + `tm_session` cookie): before → `NSE:NIFTY50-INDEX`
  `change=0.0 change_pct=0.0`; after → `change=-159.4 change_pct=-0.64`, and the user's real
  symbol `NSE:NIFTY26AUGFUT` now streams `change=-97.1 change_pct=-0.39` (feed extension works,
  log: `Feed fyers extended (pending=0)`).
- Browser smoke on prod (puppeteer, real signup): typing `NSE:NIFTY50-INDEX` renders the ticket
  quote panel `NSE:NIFTY50-INDEX 24614.9 -0.64%` — real change%, not 0.00. 6/6 OK, 0 console
  errors (only the known anonymous `/auth/me` 401 noise filtered).
- API regression **862 passed, 1 xfailed** (4 new fyers adapter tests). Web `tsc` + `next build`
  clean.
- Deployed: API hot `docker cp` (3 files) + restart, health 200; web `.next` tar
  (`--strip-components=1`) + restart, `✓ Ready`, `/terminal` 200.

### Notes
- The Redis pub/sub `market:ticks:*` path still builds `Tick` without `change_pct` (nothing
  writes that channel in-repo) — untouched, out of scope.
- Yahoo fallback feeds (no fyers token) only cover the MAJOR list — futures/options need the
  fyers feed (or broker creds), by design.

## v1.5.3 (2026-08-04) — TERMINAL UI FIX: change%, open/closed positions, buy/sell price + realised/unrealised P&L



> Beta feedback fix (allowed under feature freeze): the terminal's change percentage never
> rendered for typed symbols and position details (buy/sell price, realised/unrealised P&L,
> closed positions) were not visible. Frontend-only fix — the backend already returns every
> field via `/engine/positions` (`buy_quantity`, `sell_quantity`, `average_buy_price`,
> `average_sell_price`, `unrealised_pnl`, `realised_pnl`, `m2m`). Deployed: hot `docker cp` of
> `.next` into `trademetrix_web`. `tsc` + `next build` (`.env.production`) clean.

### Fixed
- **`apps/web/app/terminal/page.tsx`** — extended `Position` interface (buy/sell qty, avg sell,
  realised P&L, m2m); positions split into **Open Positions** (Qty / Buy / LTP / Chg% / Unrealised
  P&L + pnl%) and **Closed Today** (Qty / Avg Buy / Avg Sell / Realised P&L) sections; header
  totals for Unrealised + Realised; live-tick-first, quote-poll-fallback LTP; change% column.
- **Change% root cause**: WS tick feed only relays `subscribed_symbols` (fixed MAJOR feed), so
  typed symbols had no `change_pct`. Now the terminal polls `GET /marketdata/quote` every 5s
  (`usePolling`) for position + typed symbols and computes `(last−close)/close` client-side
  (`Quote.close` = previous close). Falls back to `Tick.change_pct` when the symbol is WS-fed.
- **`apps/web/lib/api.ts`** — added `marketdata.quote(symbols)` client method.

### Verification
- Browser smoke on prod (puppeteer, real login via API-issued `tm_session` cookie with
  `domain=.trademetrix.tech`): 0 console/page errors; quote poll fires; change% renders for a
  typed symbol (RELIANCE −1.96%); with mocked positions payload: **OPEN POSITIONS (2)** +
  **CLOSED TODAY (1)** headers render with Buy 1280 / Avg Sell 3412 / Unrealised +134 /
  Realised +84 / RELIANCE change% ~−1.9% all present in the DOM.
- Deployment note: `.next` must be extracted with `--strip-components=1` (tar contains a `.next/`
  prefix — a nested `.next/.next` crashed the server on BUILD_ID ENOENT; fixed via host-side
  extraction + `docker cp` into the stopped container + `chown`, no drift vs repo after).

### Notes
- Fresh-user paper `/engine/trade` returns `RISK_REJECTED` — pre-existing backend risk behavior
  (worker-side shared rule state), not a regression of this fix; unchanged here.
- Test users cleaned from prod (10 GoTrue admin deletes).

## v1.5.2 (2026-08-04) — user_strategies JSONB PARITY FIX (FINAL CORRECTNESS DEPLOY)

> The legacy `/api/v1/user-strategies` service assumed a dev-only relational schema that does
> not exist on prod Supabase: legs live in a `legs` jsonb column and legacy scalar fields
> (`entry_time`, `overall_*`) live inside a `config` jsonb column. List/get/create/update on
> prod failed with PGRST200 (phantom `user_strategy_legs` join) and PGRST204 (missing columns).
> Deployed: commits `ebcf9ff` + `19a1bbc`, hot-updated on VPS. Full suite **858 passed, 1 xfailed**.
> Report: `docs/evolution/certs/web_v1.5.1/user_strategies_jsonb_deploy_report.md`.

### Fixed
- **strategy_service** list/create/get/update/`_row_to_strategy` read/write the prod jsonb schema
  (`select("*")`, legs as jsonb, `entry_time`/`overall_*` folded into `config` on create and merged
  on update); `normalize_user_strategy_row()` merges config back into the row.
- **user_strategy_runner `_get_open_legs`** reads the jsonb legs column via the normalized row.
- **copilot** funds context reads the live `margin_snapshot` table.
- **Migration `20260804_01800_user_strategies_jsonb.sql`** — idempotent `ADD COLUMN IF NOT EXISTS`
  `config`/`legs` jsonb; no-op on prod (columns already present), applied locally.

### Verification
- API E2E on prod: create → read (legs=2, config merged) → update → list → **restart** → re-read
  persists; DB rows confirmed `config={"entry_time":"10:00"}`, legs=2.
- Browser E2E (real prod UI session): **13/13 OK** — signup → Create → Read → Edit+Save → Reload
  → Deploy/Start (PAPER, 2/2) → Stop (paused) → Delete; zero page errors; schema cache verified via
  OpenAPI (legs+config present, `user_strategy_legs` absent).
- Post-deploy logs: 0 schema-cache/PGRST errors; only pre-existing timeout-middleware and
  yfinance/Redis noise. Health endpoints green throughout.

### Notes
- Feature freeze now in effect: only production bug fixes, security fixes, broker compatibility
  updates, performance improvements, and beta feedback fixes are accepted.
- Beta backlog: dashboard "User Strategies" tab targets a nonexistent `/admin/strategies/all-user`
  endpoint (404 → empty table); no end-user UI exists for the legacy user-strategies lifecycle.

## v1.5.1 (2026-08-04) — BETA HARDENING SPRINT

> Reliability/correctness hardening driven by 48h prod telemetry + browser E2E + beta
> feedback. No new features. Deployed: commit `fd896ca`, API hot-updated on VPS.
> API full suite: **858 passed, 1 xfailed** (+25 regression tests vs v1.5.0).
> Post-deploy prod logs (30 min): **0×** `invalid input syntax for type uuid: "system"`,
> **0×** `Paper bracket quote refresh failed`, **0×** `CircuitBreaker[broker_fyers] is open`,
> **0×** `async_safe_single query failed: 'NoneType'`.
> Full detail: `docs/evolution/certs/web_v1.5.0/hardening_report.md`.

### Fixed
- **Kill switch (P1):** global gate read Redis `global:kill_switch` flag (the old `risk_settings`
  probe with `user_id='system'` always returned 22P02 and silently disabled the gate);
  emergency-stop state persisted to Redis and restored on startup (restart-safe); audit writes
  fall back to `audit_log` when `risk_audit_log` is missing. Migration
  `20260804_01600_risk_audit_log.sql` added (apply to prod via SQL editor; DDL blocked from API).
- **Broker token expiry (P1):** `TokenManager` fast-fails on an already-expired stored token and
  maps open circuit breaker → structured `BrokerTokenExpiredError`; `/engine/positions|funds`
  return `401 BROKER_TOKEN_EXPIRED` instead of raw 500 tracebacks.
- **Paper bracket quotes (P2):** SL/TARGET price discovery is broker-independent for paper orders
  (cache → Yahoo → broker REST last); per-symbol warning throttle 1/60s kills the 5542-line spam.
- **`async_safe_single` (P2):** guards a None `execute()` result (was surfacing misleading
  `'NoneType' object has no attribute 'data'` warnings and masking the query).
- **Rate limiter (P3):** `/analytics/track-batch` exempt from the shared per-IP budget (5s
  fire-and-forget batch consumed 12/60 RPM); default budget 60 → 120 RPM.

### Verification
- New tests: `test_kill_switch_hardening.py` (7), `test_token_manager_hardening.py` (4),
  `test_safe_query_hardening.py` (3), `test_ratelimit_hardening.py` (3),
  `test_bracket_quote_hardening.py` (4); extended `test_engine_service.py` (+4), adapted
  `test_risk_fail_closed.py`, `test_auto_trading.py`.
- Live prod smoke: emergency stop/release persist to Redis and restart-safe recovery sees stops;
  global kill switch enable sets Redis flag and gates `global_kill_switch_active()`; both cleaned up.
- Incidents: INC-015, INC-016, INC-017 added (Resolved).

> **Release status: `v1.5.0-beta` — TRADEMETRIX V1.5.0 BETA READY** (tag `v1.5.0-beta`).
> Web app deployed for Auto Trading v1.0: `next build` clean (BUILD_ID `gJiJa4QYQJlUThzieN0Ff`),
> hot-swapped into `trademetrix_web`, container healthy. Browser E2E (Playwright, prod):
> **38/38 functional checks PASS** — 18 routes, 9 API integrations, paper lifecycle
> (deploy/status/pause/resume/reconcile/stop), live-no-confirm **409 gate**, emergency
> stop + release, Confirmation Wizard (client checkbox + server 409). **0 page errors,
> 0 hydration warnings, 0 React warnings.** Reports:
> `docs/evolution/certs/web_v1.5.0/{web_deployment_report.md, browser_smoke_report.md, browser_smoke.json}`.
> API full suite: **832 passed, 1 skipped, 1 xfailed**.
> Known pre-existing prod noise (not regressions): `/engine/*` CORS blocks from expired
> Fyers token (circuit breaker open, tracked since 2026-08-01, pending re-auth).

### Added
- **`strategy_runtime/` (new package, v1.0.0)** — first-class runtime owning the full strategy lifecycle (start → run → pause/resume → stop → restart → recover): typed `StrategySpec`/`StrategyTrigger`/`RuntimeState` (`models.py`), strict `RuntimeStateMachine` + `IllegalTransition` + `can_transition` (`state_machine.py`), per-user/per-broker `RuntimeRegistry` (`registry.py`), `RuntimeContext` + `position_memory_for()` (`context.py`), `RuntimeLifecycle` + `runtime_strategy_lifecycle` singleton (`lifecycle.py`), `StrategyRuntimeManager` + `strategy_runtime_manager` singleton (`manager.py`), `RuntimeDispatcher`/`CandleDispatcher`/`TriggerDispatcher` (`dispatchers.py`), `StrategyWorker` (run loop, candles, time-trigger fold, manual dry-run evaluate) (`workers.py`), `RuntimeRecovery` (restore + adopt + fail-open) (`recovery.py`), `RuntimeObservability` (`observability.py`), `RuntimeEvent`/`runtime_bus` (`events.py`), `StrategyStateStore` + `CheckpointStateStore` + `InMemoryStateStore` (`state_store.py`), public API + `__version__` (`__init__.py`).
- **HTTP surface** — `routes/v1_strategy_runtime.py` (prefix `/api/v1/runtime`, auth-gated): POST `/deploy`, `/{id}/stop|pause|resume|restart|evaluate`, GET `/{id}/status`, `/strategies`, `/health`, POST `/event` (admin). Legacy `routes/v1_builder.py` deploy/start/stop now delegate **runtime-first** with legacy `start_graph_strategy` fallback (`_build_runtime_spec`/`_runtime_start`/`_runtime_stop`).
- **App wiring** — `main.py` lifespan: `configure_state_store(SupabaseCheckpointStore())` + `await initialize()` (fail-open) + 4s-delayed `RuntimeRecovery().recover()` background task + graceful `shutdown()` (scheduler → workers → dispatcher).
- **Prometheus** — additive metrics in `core/prometheus.py`: `strategy_runtime_running` Gauge; `strategy_runtime_lifecycle_events_total{state}`, `_orders_total{outcome}`, `_errors_total`, `_restarts_total`, `_ticks_total`, `_dropped_ticks_total` Counters; `strategy_runtime_latency_seconds`/`strategy_runtime_recovery_seconds` Histograms.

### Changed
- `execution_engine/persistence.py` `recover_runtime_state()` skips runtime-owned strategies (checkpoint kind `strategy_runtime` → `runtime_owned_strategies` → recorded in `strategy_skips`) — no double-start with engine recovery.
- Manager: `_start_running` calls `_stop_legacy(...)`; new `_stop_legacy()` cancels surviving legacy `graph_strategy_runner._running_tasks` for adopted strategies; new `shutdown()`.

### Fixed (found while building the runtime)
- `core.cache` `get`/`set` are coroutines — `_persist_seen_ids`/`_load_seen_ids` in `workers.py` now async and awaited in `stop()` and the run-loop `finally`.
- `recovery.py` bogus `from strategy_runtime.recovery import runtime_observability` removed; `_adopt` called on `self` (not `self._manager`); `obs.record_recovery` → `runtime_observability.record_recovery`.
- `routes/v1_builder.py` manager junk line removed; `_publish_event` wrapper removed (`_on_broker_disconnect` now emits `_publish_runtime_event("BrokerDisconnected", ...)` directly).

### Verification
- New tests: `tests/test_strategy_runtime.py` (18: lifecycle, state-machine table, pause/resume/restart, restart-from-stopped, candle eval + orders, seen-candle dedup, no-signal, two-strategy isolation, MTF aggregation, manual dry-run, broker disconnect/reconnect + per-broker isolation, session open/close, checkpoint persist/remove, health, user isolation), `tests/test_strategy_runtime_recovery.py` (8: restore running, idempotent, skip stopped, paused-as-paused, adopt legacy-running, engine-recovery skip guard, legacy-only restart, fail-open broken store), `tests/test_strategy_runtime_api.py` (3 HTTP: deploy→status→pause→resume→evaluate→stop lifecycle, health, 404 unknown id).
- Full regression: `pytest tests/` → **806 passed, 1 xfailed** (+3 vs v1.4.0's 803, +50 vs v1.3.1's 717).
- Benchmark (`benchmark_strategy_runtime.py`): tick throughput ≈78k ticks/s (0 dropped), candle eval ≈15.7k evals/s (avg 0.31ms), 10-worker fanout ≈4.2k ticks/s (uniform, 0 dropped), seen-candle dedup 10k replays → 1 eval/1 order.

### Known gaps
- Order execution still flows through the frozen `engine.gate.execute_order(...)` path; runtime-level risk integration (position/order checks) deferred.
- Recovery is fail-open by design — a broken store means no auto-restore (never crashes startup).
- Supabase `strategy_runs` insert noise (permission-related) is benign warn-level.
- Docs: `docs/evolution/STRATEGY_RUNTIME_V1.md`, `docs/evolution/RELEASE_AUDIT_STRATEGY_RUNTIME_V1.md`, `docs/evolution/PROD_READINESS_STRATEGY_RUNTIME_V1.md`.

## v1.4.0 (2026-08-03) — EXECUTION ENGINE V1.0 (CANONICAL EVENT-DRIVEN EXECUTION LAYER)

### Added
- **`execution_engine/` (new package)** — canonical, event-driven execution layer composed on top of the frozen Broker SDK v2: typed domain bus (`events.py`, 6 domains / 24 event types, thread-safe publish with `call_soon_threadsafe`, single async FIFO dispatcher, deterministic inline dispatch pre-startup, sequence + correlation ids, 2000-event ring buffer, legacy `execution.event_bus` bridge), canonical `OrderState` machine with `FAILED` + `PARTIAL` alias (`state_machine.py`), FIFO lot engine (`fifo.py`), fills ledger + `TradeManager` (`trades.py`, optional `TradeStore` protocol), event-driven netting + MTM (`positions.py`), per-account P&L with IST daily window + equity/peak/drawdown recomputed from state (`pnl.py`), portfolio snapshots (`portfolio_engine.py`, optional `SnapshotStore`), `ExecutionEngine` facade with idempotent `submit`/`cancel`/`modify` (`engine.py`), Prometheus sink (`metrics.py`), and one-call bootstrap `init_execution_engine(loop)` wired into `main.py` lifespan.
- **Legacy composition** — `portfolio/manager.py` `refresh()` mirrors broker-truth state onto the canonical bus (`portfolio.snapshot`, `source: portfolio_manager`), additive and fail-open.

### Changed
- `apps/api/main.py` — lifespan calls `init_execution_engine()` after `order_manager.start()` and `shutdown_execution_engine()` on graceful shutdown (both non-fatal on failure).

### Fixed (found while building the engine)
- FIFO realized P&L sign inversions (SELL-against-longs + BUY-against-shorts) — closing above entry now realizes a profit.
- Infinite `portfolio.snapshot` fanout (PortfolioEngine self-trigger) + duplicate snapshots per fill (subscription scoped to PORTFOLIO domain).
- Duplicate ring-buffer entries (`_finalize` idempotency) and inline-dispatch race (`apublish` drains cascade tasks).
- `EXECUTION_RESULT` KeyError on non-fill statuses; `open_positions` added to `portfolio.revalued` payload.

### Verification
- New tests: `tests/test_execution_engine.py` (40 tests: state machine, FIFO, bus incl. thread-safety, trade ledger, positions lifecycle, P&L/portfolio chain with FIFO round-trip 267.5, facade outcomes, metrics, bootstrap, legacy composition).
- Full regression: `pytest tests/` → **756 passed, 1 xfailed** (+39 vs v1.3.1's 717).

### Known gaps
- Durable `TradeStore`/`SnapshotStore` adapters not wired (legacy `orders` audit table remains the durable trail).
- `oms/state_machine.py` / `execution/models.py` delegation to the canonical machine deferred to keep the regression surface frozen.
- Docs: `docs/evolution/EXECUTION_ENGINE_V1.md`, `docs/evolution/RELEASE_NOTES_EXECUTION_ENGINE_V1.md`.

## v1.3.1 (2026-08-03) — UNIFIED BROKER SDK V2 (PHASES 3 & 4: OBSERVABILITY + LIVE CERTIFICATION)

### Added
- **`brokers/sdk/events.py` (new)** — typed broker audit event bus: canonical `BrokerEventKind` set (login/logout, token refresh/expiry, auth, order sent/rejected/filled, position, websocket up/down, rate-limited, circuit open, health-changed, reauth-required), sequence-numbered fan-out to sinks, in-memory ring buffer (`recent`), severity normalisation, `LoggingSink` (structured `event=…` lines), `MetricsSink` → Prometheus `broker_events_total`, and a health bridge (state transitions publish `HEALTH_CHANGED`).
- **`brokers/sdk/auth.py` (new)** — unified authentication layer: `Token` / `TokenState` / `token_state()` (valid / expiring-soon / expired / invalid with 5-min buffer), single-flight refresh (`ManagedSession`), re-auth-required state, `InMemoryTokenStore` + pluggable `TokenStore`, per-account `SessionManager` registry with snapshot, and `AuthProvider` base for brokers. Re-auth on refresh failure → `ReAuthRequiredError`; state exposed via `session.health()`.
- **`brokers/sdk/websocket.py` (new)** — unified WebSocket manager (backend-agnostic via a `WebSocketBackend` factory): auto-reconnect with exponential backoff (cap 60s), heartbeat + latency monitoring, subscription dedup + resubscription on connect, message routing to handlers, stats (`messages_in`, reconnects, last pong), and `health()`.
- **`brokers/sdk/health.py` (new)** — `BrokerHealthService`: component signals (REST, WS, auth, rate-limit, circuit, degraded) → one canonical `BrokerHealthState` (connected/rest/ws-only/degraded/rate_limited/circuit_open/auth_failed/disconnected); event-bus driven; per-broker snapshot with `reported_at`.
- **`brokers/sdk/metrics.py` (new)** — unified broker metrics surface: flat serialisable snapshot (requests/success/failure/retry, breaker, ws, auth, token-refresh count, order/rest/ws latency, cache/dedup hit ratio, rate-limit utilisation), `MetricSource` producer protocol, `BrokerMetrics` registry with per-broker snapshots + health overlay.
- **`brokers/sdk/observability.py` (new)** — one-call app wiring (`wire_default_observability`): `TransportMetricSource` (adapts `HttpTransport.snapshot()`/`health()` to the metrics contract), `breaker_state_bridge` (circuit-breaker callback → health + `CIRCUIT_OPEN` event + prometheus gauge), and health/event/metrics composition. Wired in `main.py` lifespan (non-fatal on failure).
- **`brokers/fyers_provider.py` (new)** — Fyers auth `AuthProvider` (access-token consent model, no silent refresh → `ReAuthRequiredError`) + live-observability glue `register_fyers_observability` (real transport snapshot into the default metrics/health registries).
- **New broker endpoints** — `GET /api/v1/brokers/health` (all brokers), `/health/{broker}`, `/metrics/{broker}` (14-key flat snapshot), `/capabilities` (runtime discovery). Auth-required; unknown broker → 404. Brokers block added to `/health/metrics` (`brokers` key).
- **Prometheus** — `broker_events_total{broker,kind}`, `broker_health_state{broker}` (1–8 ladder), `broker_auth_state{broker}` (0–5 ladder), plus `record_broker_event/record_broker_health/record_broker_auth` in `core/prometheus.py`.
- **`brokers/sdk/live_cert.py` (new)** — live certification framework for the canonical engine workflow: `LIVE_STEPS` (login → token refresh → quotes → history → option chain → websocket → positions → holdings → funds → disconnect → reconnect → token-expiry → circuit-recovery → [place/modify/cancel order]). Drivers speak the canonical v2 surface (`connect(credentials)`, `refresh_token(credentials)`, `get_option_chain(symbol)`, `subscribe_market_data(symbols, on_tick)`), signature-filtered for legacy methods; the websocket probe subscribes in a background task and accepts a connected, error-free feed (ticks are market-hours dependent).
- **`brokers/live_cert.py` (new)** — `python -m brokers.live_cert --broker <name> [--allow-orders] [--user <uuid>] [--out path]` orchestration: resolves the adapter via the SDK registry, optionally authenticates from stored broker credentials (`--user`), runs every step with a per-step timeout, and writes `.{json,md}` certification reports.

### Changed
- `apps/api/routes/v1_brokers.py` — health/metrics/capabilities endpoints (Phase 4) with auth + 404 handling, per-broker payloads backed by the SDK health/metrics registries.
- `apps/api/core/metrics.py` — `/health/metrics` now includes the `brokers` key from the SDK metrics registry.
- `apps/api/core/prometheus.py` — broker state gauges + event counter (Phase 4).
- `apps/api/main.py` — `wire_default_observability()` called in lifespan (event bus → health → metrics composed), `broker.connected` event recorded on credential save.
- `apps/api/brokers/sdk/live_cert.py` — `LiveCertResult` is skip-aware (`add(..., skipped=True)`); `passed` = every **executed** (non-skipped) step passed; `ran` lists executed steps; order-steps recorded as skipped unless `allow_orders=True`; `write_report` emits `.json` + `.md`; `_call_live` scores a completed call (even returning `None`) as passing, matching adapter fire-and-forget semantics; credential-backed connect steps (`login`/`reconnect`/`circuit_recovery`) reuse the stored creds; capability-absent steps raise `UnsupportedFeatureError` → recorded as SKIP.

### Verification
- New tests: `tests/test_sdk_phase3.py` (events bus fanout/ring/severity/sinks, auth lifecycle incl. refresh/re-auth/invalidate/session-manager, health derivation/tracking/degrades, websocket manager subscribe/reconnect/routing/latency — ~25 tests) + `tests/test_sdk_phase4.py` (metrics overlays, registry snapshots, breaker bridge, health/metrics/capabilities endpoint shapes — ~13 tests) + `tests/test_sdk_live_cert.py` (healthy pass, broken adapter, token-expiry invalidation, opt-in order steps, per-step timeout, report serialisation/presence, default-driver coverage of all steps, capability-absent skip, credential-backed CLI recipe — 11 tests).
- Full API regression: `pytest tests/` → **717 passed, 1 xfailed** (baseline 662 for v1.3.0; +55 new).
- **Fyers live certification — LIVE_CERTIFIED (2026-08-03)**: credential-backed run (`--user fa668109-…`) completed in 18.1s against production: login, quotes, history, websocket, positions, holdings, funds, disconnect, reconnect, circuit-recovery all PASS on real live data; `token_refresh`/`token_expiry`/`option_chain` recorded as SKIP (Fyers capability-absent — `UnsupportedFeatureError`). Report: `docs/evolution/certs/fyers_live_cert.{json,md}`.

### Known limitations (not regressions)
- **Fyers `get_option_chain` live certification** is recorded as SKIP in the live-cert run (`UnsupportedFeatureError` — no direct Fyers API surface); the platform-level option-chain route remains covered by the transport (10s TTL) and the Fyers rate-limit audit. Tracked in `docs/evolution/BROKER_SDK_V2.md` → Known Gaps.
- Live certification for the 10 non-Fyers brokers still waits on active credentials (cert-only step recorded when run).

## v1.3.0 (2026-08-03) — UNIFIED BROKER SDK V2 (PHASE 2: GENERIC TRANSPORT)

### Added
- **`brokers/sdk/transport.py` (new)** — generic, broker-agnostic `HttpTransport` extracted from `brokers/fyers_http.py`: per-token sliding-window rate limiter (RPM + burst), jittered exponential backoff honoring `Retry-After` (429/1015), zero-retry WAF blocks (403), in-flight dedup, GET response caching, correlation ids, `health()`, and Prometheus counters (`broker_http_calls/wire_calls/cache_hits/dedup_hits/retries/rate_limited/waf_blocks/failures_total` + `broker_http_latency_seconds`).
- **Pluggable strategy extension points** — `AuthStrategy` (header + signing hook), `HeaderStrategy`, `URLBuilder`, `ResponseParser`, `ErrorTranslator` (status → typed `BrokerError`), `RetryPolicy`, `RateLimiter`/`TokenRateLimiter` — zero `if broker` branches; adding a broker = config + strategy overrides only.
- **`GET /brokers/admin/rate-limit`** now backed by the same transport (unchanged shape) — per-token RPM/retry ledger plus new `health()` data.

### Changed
- **`brokers/fyers_http.py` refactored into a thin facade** over the generic transport — public API identical (`FyersTransport`, `FyersResponse`, `FyersWAFError`, `TokenRateLimiter`, `get_transport`, `fyers_rate_snapshot`); all 7 consumer sites untouched. `FyersWAFError` now subclasses SDK `BrokerWAFError`.
- **`core/prometheus.py`** — new `broker_http_*` transport counters + `record_broker_transport_metric()`/`record_broker_transport_latency()`.
- **Structured logs** gained a `corr=` field (per-request correlation id) on `fyers.request`/`fyers.retry`/`fyers.waf` records.

### Verification
- API regression: `pytest tests/` → **662 passed, 1 xfailed** (baseline 644; +16 generic-transport tests in `tests/test_sdk_transport.py`). Two `asyncio.sleep` patch targets moved from `brokers.fyers_http` to `brokers.sdk.transport` (where sleep now executes).
- Before/after benchmark (`apps/api/benchmark_transport.py`, canned workload vs git HEAD): **Δ = 0 on every accounting counter** (calls, wire calls, cache hits, dedup hits, retries, rate-limited, WAF blocks, failures); overhead ≈ +0.09 ms + ~63 B per request (correlation id + metric emit). Report: `docs/BrokerTransportBenchmark.md`.
- Docs: `docs/evolution/BROKER_SDK_V2.md` §2/§8/§11 updated (Phases 1–2 marked done, onboarding recipe).

## v1.1.0 (2026-08-03) — PRODUCTION READINESS FIXES

### Product policy: complete-and-keep (no removals)
All audit findings (`docs/ProductCleanupAudit.md`, KEEP 29) are now fixed in place — every page is functional, live-data, and discoverable. No features deleted.

### Added
- **`GET /api/v1/feedback` (user feedback history)** — new route in `routes/v1_feedback.py` + `list_user_feedback()` in `application/services/analytics_service.py` (Supabase `feedback_items` query, fail-open fallback); scoped to the authenticated user; new test `test_list_user_feedback_scoped_to_user`.
- **`/funds` page** (`app/funds/page.tsx`) — live margin cards, margin breakdown (pay-in/pay-out, collateral, MTM unrealised) and P&L panel from `/engine/funds` + `/analytics/pnl?period=1d`; broker-connect CTA when no broker. New Trade nav item `Funds` (💰) alongside the broker-management page (`/brokers`, 🏦).
- **Workspace→Terminal integration** — `components/workspace/sidebar.tsx` gained Terminal (💻, `/terminal`) and Option Chain (📡, `/marketdata`) entries.

### Changed
- **Feedback page** (`app/feedback/page.tsx`) — real API submit via `api.feedback.submit` (removed fake `setTimeout`), submission history via `api.feedback.myHistory`, status badges (new/triaged/resolved/wontfix), NPS 0–10 persisted in metadata, auto-refresh after submit.
- **Analytics page** (`app/analytics/page.tsx`) — live `/analytics/pnl?period=1d|1w` + `/analytics/mtm`; KPI row now real (Today's P&L, Total P&L, Win Rate, Avg Win/Loss, Expectancy, Active Runs) plus a live P&L Snapshot panel (realized/unrealized/weekly/monthly/overall P&L, current equity, drawdown %, MTM).
- **Status page** (`app/status/page.tsx`) — rewritten: live probes to `/health`, `/health/ready` (db/cache dependencies), `/health/metrics` (CPU/memory/requests/threads) and EventSource websocket check; 60s auto-refresh; real version/uptime; fake incidents and the mock maintenance button removed.
- **Landing page** (`app/page.tsx`) — header nav gained Pricing + System Status; footer expanded to full public nav (Product: Pricing/Client Portal/Open Terminal; Resources: System Status/Documentation/Contact; Legal: Privacy/Terms/Risk Disclosure/Disclaimer). Footer styles hoisted to module constants to avoid a TypeScript JSX parser bug with nested inline styles.
- **`lib/api.ts`** — new `feedback` (submit/myHistory) and `analytics` (pnl/mtm) client groups; `api.feedback.submit` matches the production endpoint.
- **`docs/ProductCleanupAudit.md`** — updated to KEEP 29; prior HIDE/REMOVE recommendations superseded by the no-delete policy.

### Verification
- API regression: `pytest tests/` → **563 passed, 1 xfailed** (incl. new feedback-history test). Note: bare `pytest` at repo root collects the standalone `pat_test.py` runner (matches `*_test.py`) which exits at import — run scoped to `tests/`.
- `tsc --noEmit` clean; prod build clean (all pages incl. `/funds`).
- Prod E2E + screenshots of landing/funds/feedback/analytics/status and workspace sidebar.

## v1.1.1 (2026-08-03) — POST-DEPLOY E2E HOTFIXES

### Fixed
- **Status probes hit the wrong origin** — health endpoints mount at the API root (no `/api/v1` prefix), so probes 404'd; the status page now derives `API_ORIGIN = new URL(API_BASE).origin` and probes `/health`, `/health/ready`, `/health/metrics` there (`44462a4`, `362c026`).
- **Metrics renderer assumed the wrong payload shape** — `/health/metrics` `requests` is a per-path dict (`{path: {count, avg_ms, max_ms, min_ms}}`), not a flat object; total + top path are now computed and rendered (`362c026`).
- **Logged-out users got 3× 401 retries on every page** — `auth-context` `fetchUser` now fast-paths any `401` to anonymous state immediately (`44462a4`).
- **Status EventSource opened unauthenticated** — the events stream is auth-gated; the page now checks `/auth/me` first and marks the stream operational for anonymous visitors instead of failing (`44462a4`).
- **lightweight-charts parse errors on the workspace chart** — `color-mix()`/CSS-var colors are unparseable by the chart library; all theme colors are now resolved to concrete hex at runtime via `colorVar()` (getComputedStyle) + `mix()` (hex-alpha) helpers (`dc673d9`). Zero pageerrors after fix.
- **Intermittent 405 / stale profile on `PATCH /api/v1/auth/profile`** — two distinct causes, both fixed:
  1. `profiles.onboarding_completed` column did not exist on remote Supabase (PGRST204 → 500). New migration `supabase/migrations/20260803_01400_onboarding_completed.sql` applied.
  2. The 120s in-memory `_user_cache` was never invalidated by profile writes, so `/auth/me` returned the pre-PATCH profile for up to 2 minutes; `update_profile` now pops the cache entry (`a8cbc16`). FastAPI 0.141.x lazy `_IncludedRouter` startup warm-up was also added as a hardening measure (`b0c73f1`).

### Verification
- API regression: `pytest tests/` → **563 passed, 1 xfailed**.
- Full prod E2E green (18/18): landing nav/footer, live status probes, signup → onboarding PATCH → `/auth/me` reflects `onboarding_completed: true`, funds CTA, feedback submit + history, analytics live P&L, workspace Terminal/Option-Chain links. Zero pageerrors, zero hydration errors.
- Remaining expected console noise: single 401 on `/auth/me` per anonymous page visit (no retries), 503 from the external option-chain vendor.

## v1.1.2 (2026-08-03) — FYERS RATE-LIMIT COMPLIANCE

### Added
- **`brokers/fyers_http.py` (new)** — shared per-token `FyersTransport`: sliding-window `TokenRateLimiter` (budget **100 RPM + 8 req/s burst** per access token, 50% headroom under Fyers' ~200/min community-observed ceiling), response caching (`cache_ttl`), concurrent-request dedup (in-flight future), jittered exponential backoff (base 0.25s, cap 8s, `MAX_RETRIES=3`) honoring `Retry-After`, and Cloudflare semantics: **1015 retryable**, **403 = WAF block → `FyersWAFError`, zero retries**. Process-wide registry keyed by `client_id`; `fyers_rate_snapshot()` per-token stats.
- **`GET /brokers/admin/rate-limit`** (admin-only) — live snapshot of per-token Fyers traffic (calls, wire calls, cache/dedup hits, retries, rate-limited, WAF-blocked, failures, RPM). `fyers` key added to `/health/metrics`.
- **Structured logs** — `fyers.request` (endpoint, method, status, retries, latency_ms, cached, dedup, rate_rpm, caller) and `fyers.retry` (attempt, delay, reason).
- **`_fetch_csv` in `market/symbol_master.py`** — 24h TTL cache + backoff for the static Fyers symbol CSVs (NSE_CM/NSE_FO).

### Changed
- **All Fyers REST traffic routed through the transport** — authenticate, place/modify/cancel, orderbook (3s TTL), positions (5s), holdings (10s), funds (5s), quotes (0.5s), span margin (60s cache), history (retries=1/URL, no cache). Order writes (place/modify/cancel) never retry; auth retries=2; reads retries=3.
- **Option-chain call sites** (`routes/v1_marketdata.py` POST + `market/option_chain.py`) — now via `get_transport` with 10s TTL; web route capped at retries=1.
- **OMS bracket quotes WS-first** — `_bracket_quote` prefers a fresh WS-fed tick (`market_cache`, age <5s) over REST and single-flights quotes per (user, symbol) so the global 2s bracket monitor issues one REST quote per symbol regardless of bracket count.
- **`_stream_yahoo` backoff** — Yahoo fallback polling now backs off exponentially (cap 30s) instead of tight-looping on failures.

### Verification
- New `tests/test_fyers_http.py` (9 tests: 429/`Retry-After`, 1015 backoff cap, WAF no-retry, 400 no-retry, dedup → 1 wire call, cache, sliding window + burst ceiling, RPM accounting); `tests/test_broker_fyers.py` rewritten against the mocked transport; `tests/test_margin_estimate.py` updated to transport-shape assertions.
- Full API regression: `pytest tests/` → **573 passed, 1 xfailed**.
- Compliance report: `docs/FyersRateLimitAudit.md` (full endpoint inventory, RPM table, controls, residual risk).
- Pending post-deploy: `/brokers/admin/rate-limit` snapshot on a live trading day; `fyers` block in `/health/metrics`; `fyers.request`/`fyers.retry` lines in logs.

## v1.2.0 (2026-08-03) — UNIFIED BROKER SDK V2 (PHASE 1 FOUNDATION)

### Added
- **`brokers/sdk/` (new)** — enterprise broker-agnostic layer:
  - `errors.py` — typed `BrokerError` taxonomy: `UnsupportedFeatureError`, `BrokerAuthError`, `BrokerRateLimitError` (Retry-After aware), `BrokerWAFError` (never retried), `BrokerConnectionError`, `BrokerTimeoutError`, `BrokerDisconnectedError`, `BrokerValidationError`, `OrderRejectedError`/`MarginInsufficientError`, `BrokerServerError` — each with `code`, `broker`, `retryable`, `http_status`, `retry_after`, `correlation_id`; `translate_broker_error(status, body, headers)` and `translate_exception()` map HTTP/raw failures onto the taxonomy.
  - `capabilities.py` — `CapabilityFlag` enum (19 features: order mod, bracket, cover, GTT, multi-leg, option chain, historical, websocket, market depth, greeks, indices, currency, commodity, margin calculator, …) + `BrokerCapabilities` (canonical `supports()`/`require()` with typed `UnsupportedFeatureError` + the legacy boolean surface) + authoritative per-broker matrix.
  - `registry.py` — `BrokerRegistry` (adapter class + UI metadata + capabilities in one spec), `create()` preserving the `CircuitBreakerBroker` factory contract.
  - `interface.py` — `BrokerPort` protocol (19-method v2 surface) + `BrokerAdapterBase` mixin bridging v2 names onto legacy `BaseBroker` methods; unimplemented features raise the typed error instead of failing unpredictably.
  - `certification.py` — reusable Level A interface cert + Level B behavioral flow.
- **All 11 broker adapters now expose the identical v2 surface** (via `BrokerAdapterBase`; zero behavior change).
- **Certification suite** (`tests/test_broker_certification.py`) — Level A cert for every registered broker; all 11 currently CERTIFIED; one capability gap recorded (fyers `option_chain` — Phase 4 will implement it on the adapter).

### Changed
- **Single source of truth** — execution-layer `BROKER_CAPABILITIES` and UI broker metadata now derive from the SDK registry/matrix (values identical, verified by `test_legacy_equivalence`); legacy `create_broker`/`register_broker`/`get_broker_metadata` delegate to the SDK.

### Documentation
- `docs/evolution/BROKER_SDK_V2.md` — layers, capability matrix, sequence diagrams (order flow, market data, error translation), phased roadmap (transport → auth/ws/health/audit → adapter porting → live cert → benchmarks), migration plan, rollback strategy.

### Verification
- Full API regression: `pytest tests/` → **644 passed, 1 xfailed** (+71 new SDK/certification tests).


## v1.0.1 (2026-08-02) — USER NAVIGATION REDESIGN (P0 INCIDENT FIX)

### Product discoverability — navigation only (zero backend/API/logic changes)

### Fixed
- **P0: normal users were trapped on `/portfolio`** — the app shell hard-redirected every non-admin away from all non-standalone pages, so the sidebar (the only navigation surface) never rendered for them and 4 of 5 shipped features were invisible. The redirect gate now only bounces non-admins from admin routes (`/admin*`, `/dashboard`).
- **Sidebar now renders for every authenticated user** with the full platform: Home (Home/Watchlist/Portfolio shell), Trade (Trading Workspace, Orders, Positions, Funds), Build & Analyze (Market Analyzer, Strategy Builder, Backtest, Analytics, Trade Journal), Manage (Alerts, Risk Control, Settings, Help), Platform (Terminal, Option Chain, Terminal Builder, Strategies, Marketplace, AI Assistant) — all 14 required nav items present.
- **Admin routes fully isolated** — `/admin/*` + `/dashboard` unreachable by users (client gate + existing server-side `require_admin` RBAC untouched); admin sidebar gained a Beta section (Beta Dashboard, Broadcast).
- **Orphaned pages wired in** — Catalog + Multi-Leg buttons on the Strategies page; Account/Feedback/Changelog/Transparency/Status added to the profile popover; logo link is role-aware.
- **Dead ends removed** — `/trade`, `/marketdata`, `/brokers` links from the portfolio header now work for users; sidebar active-state matching tightened (exact-or-child).

### Changed
- `components/app-layout.tsx` (user nav sections, role-aware gate + sections, profile popover, `isActive_`), `app/strategies/page.tsx` (header links), `docs/DiscoverabilityAudit.md` (audit + fix report with navigation map).

### Verification
- Every nav href resolves to a real route (44/44); all 37 user+admin routes return 200 on the prod build; SSR HTML contains the full user nav.
- `tsc --noEmit` clean; prod build clean (46 static pages).
- Post-deploy E2E on prod: login → Home → all menu items, logout, admin-route isolation, console/hydration checks (see `docs/DiscoverabilityAudit.md`).

## v1.0.1-beta (2026-08-01) — BETA OPERATIONS MODE

### GA evidence collection (no product features — telemetry, dashboards, reports)

### Added
- **Persistent product analytics** — new Supabase tables `analytics_events` (event/properties jsonb/session_id/user_id/created_at + 4 indexes) and `feedback_items` (category/title/description/metadata/status/notes + indexes), migration `20250801_01300_analytics_persistence.sql` applied to remote. Replaces the lossy in-memory tracker: everything now survives restarts.
- **Client tracker** (`apps/web/lib/analytics.ts` + `components/analytics-tracker.tsx`) — privacy-first: no PII (`user_id` resolved server-side from auth), payload redaction (secrets stripped, strings capped), sampling + excluded paths + Do-Not-Track respect, 5s batching + keepalive/beacon flush, CSRF-aware, `NEXT_PUBLIC_ANALYTICS_ENABLED`/`NEXT_PUBLIC_ANALYTICS_SAMPLE` config. Tracks session.start, page.view (SPA-aware), click, scroll.depth, client_error.
- **Server-side value events** — authoritative `strategy.created`, `backtest.run`, `order.placed`, `broker.connected` recorded from auth context (never client-supplied); `api_error` recorded by the timing middleware on 5xx.
- **Feedback Center** — in-app dialog (bug/feature/nps/report) now persists to Supabase; admin list + status triage (new/triaged/resolved/wontfix) via `GET/PATCH /api/v1/admin/feedback`.
- **Beta Dashboard** (`/admin/beta`) — admin-guarded: activation overview (DAU/WAU/MAU, activation/retention/crash-free rates, 14d activity), activation funnel, custom step-funnel with drop-off %, weekly retention cohort matrix, most-used features ranking, session list + per-session event replay timeline, crash signatures grouped by key, feedback triage table.
- **Admin analytics API** — `/api/v1/admin/analytics/{overview,funnel,retention,features,sessions,crashes}` + `/sessions/{id}/events`, all `require_admin`; anonymous ingest `POST /api/v1/analytics/track-batch` (fail-open, CSRF-protected).
- **Weekly analytics reports** (`infra/scripts/analytics_report.sh`) — generates `docs/weekly/<W>/06-funnel, 07-activation, 08-retention, 09-most-used-features, 10-drop-off, 11-most-requested-features` from remote Supabase; W31 baseline authored with real data.

### Changed
- `AnalyticsService` rewritten DB-first (in-memory fallback keeps ingest fail-open); `v1_feedback.py` DB-backed; `core/deps.py` adds `get_optional_user`; test mocks use the service module's imported `get_supabase`/`async_supabase` references.

### Verification
- API regression: **562 passed, 1 xfailed** (11 new analytics tests).
- Web: `tsc --noEmit` clean; prod build clean.
- Deployed hot to prod; in-container smoke (auth + CSRF): track-batch 200/accepted, all 6 admin endpoints 200, feedback submit + triage, session replay, admin event filter — **ALL PASSED**; smoke rows cleaned.
- New web BUILD_ID served on prod.

## v1.0.0 (2026-08-01) — GENERAL AVAILABILITY

### GA Preparation (production readiness — no new features)

### Added
- **Single-command production deploy** (`infra/production/deploy.sh`) — non-interactive: installs Docker/Compose if missing, `git reset --hard origin/main` (repo = sole source of truth), env-file guard, OpenRouter key injection only when explicitly provided, DNS advisory, `build --parallel api web`, `up -d`, health gates on API `/health` + web (18×10s), clear failure tips, `Deployment Complete — v1.0 GA` banner. Validated E2E on prod from a fresh `origin/main` checkout.
- **Verified backup pipeline** (`infra/scripts/backup.sh`) — Redis RDB via `redis-cli SAVE`; Prometheus consistent TSDB snapshot (admin API, zero downtime); Grafana/n8n/Caddy via brief stop + tar of their `production_*` volumes; env-file copy; 14-day retention; every archive `tar tzf`-verified (exit 1 on any failure). E2E: all components `[OK]`, 49M verified.
- **Prometheus admin API enabled** — `--web.enable-lifecycle` + `--web.enable-admin-api` in the production compose (Prometheus 3.x split the flags; required for snapshot-based backups). Force-recreated container; snapshot verified (`20260801T082220Z-…`).
- **Remote Supabase fully migrated** — `20250731_01100_builder_persistence.sql` + `20250801_01200_backtest_persistence.sql` applied to `db.nwutlfuowiulfpbsrldn.supabase.co` (PostgreSQL 17.6): `builder_strategies`, `builder_strategy_versions`, `builder_strategy_logs`, `backtest_runs`, `candles`, `corporate_actions` all created (RLS on, service-role bypass). Verified post-restart: 7 strategies / 2 runs / 533 candles persisted.
- **Restart persistence verified (prod)** — builder strategy (status `ready`), COMPLETED backtest run, lifecycle logs and version history all survive an API restart; OMS recovery confirmed ("Recovered 1 active orders…").
- **GA docs** — `DEPLOYMENT.md` (rewritten, single-command), `DISASTER_RECOVERY.md` (rewritten, RPO/RTO + scenarios), `BACKUP_RESTORE.md` (new), `RUNBOOK.md` (refreshed), `RELEASE_NOTES.md` (rewritten for GA), `KNOWN_ISSUES.md` (new), `UPGRADE_GUIDE.md` (new).

### Changed
- **Backtest data reliability** (`backtest/manager.py`, `backtest/data_loader.py`, `market/historical.py`) — run-v3 now propagates `user_id` to the data loader at both call sites (previously loaded zero candles); the auto source routes through the durable candle store (`backtest_historical.load`: Supabase-first, gap-fill, write-back) instead of broker-only; Yahoo fallback (`^NSEI` etc.) engages when creds are absent/expired/fetch fails/`not user_id`. Backtests complete without any broker credentials.
- **Repo made authoritative** — 112-file backlog (Phases 4.3–6) committed (`f88d300`) and pushed to public GitHub `main`; verified zero tracked secrets (`.env*` gitignored); VPS repo now `git reset --hard origin/main` (env files survive as untracked).
- **Deployment UX** — old interactive `read -rp "Enter your OpenRouter API key"` paths removed (they aborted non-TTY deploys); backup archives no longer truncated (`tar -C /v .` only, stopped-container tar for sqlite-backed volumes).
- **reportlab baked** — 5.0.0 and all runtime deps verified in a clean `--no-cache` image build; fresh containers need zero manual post-install.

### Verification
- Full API regression: **551 passed, 1 xfailed**.
- Web: `tsc --noEmit` clean + prod build clean.
- Deploy E2E from `git reset --hard origin/main`: images built, api+web healthy (200), GA banner, exit 0.
- Backup E2E: all components verified (`[DONE] Backup complete and verified`), exit 0.
- Persistence smoke post-deploy-restart: `strategies=7, runs=2, candles=533` in remote Supabase.

### Known gaps
- See `KNOWN_ISSUES.md` (Fyers token re-auth, TRADINGVIEW_WEBHOOK_SECRET unset, Telegram stubs, service-role keys, single-host footprint, on-VPS-only backups).

## v0.2.0-rc.7 (2026-08-01)

### Phase 6 — Product Polish (Accessibility, Consistency, Performance Audit)

### Added
- **Audit + Improvement Plan** (`docs/evolution/PHASE6_PRODUCT_POLISH.md`) — full survey of 63 pages + 42 components with four reports: UX (dead header tabs, fake search div, hardcoded `v0.1`, duplicate nav, toast/inline-success inconsistency, empty-state drift, no error boundary), Performance (84.6 kB shared JS, 9 polling intervals all cleaned, no RSC/streaming/dynamic chunks), Accessibility (A1–A9), Visual Consistency (≈100 hardcoded hexes, ~340 buttons without `type` — deferred).
- **Skip-to-content link** — visible-on-focus `Skip to content` in the app shell targeting `#main-content` on the content container (keyboard-first navigation).
- **Real search button** — global search trigger is now a `<button data-search-open aria-label="Search symbols, strategies, pages (⌘K)">` (was a non-focusable `<div>`).
- **Search overlay dialog semantics** — overlay is now `role="dialog"` + `aria-modal="true"` + `aria-label`, with a Tab focus trap while open and focus restored to the trigger on Escape (only when focus was inside the overlay).
- **Dropdown a11y** — notifications + profile popovers: `role="menu"`, `aria-label`, `aria-expanded`, `aria-controls` (ids `notifications-popover`/`profile-popover`); `aria-current="page"` on active nav links; `aria-label` on sign-out, theme-toggle, sidebar collapse/expand icon buttons.
- **Root error boundary** — `app/error.tsx` (Try again + Back to Dashboard, dev-only error dump) and `app/not-found.tsx` (friendly 404 with dashboard link) — the app previously had zero `error.tsx` files anywhere.
- **Real app version** — header badge and portal footer now render `AppVersion`/`getAppVersion()` (env-driven) instead of hardcoded `v0.1`.
- **Toast a11y** — toast container `role="status"` + `aria-live="polite"`; each toast item `role="alert"`.

### Changed
- **Contrast fixes** — dark-theme `--text-faint` `#5b5875` → `#7d79a0` (~2.5:1 → 4.5:1); light-theme `--text-faint` `#9aa0a6` → `#757580`; `error-message.tsx` `#ef4444` → `var(--text-red)`.
- **Color literal sweep** — `#ef4444` → `var(--red)` (6 files incl. portal, strategies/catalog, admin beta/broadcast, strategy-builder types, equity-curve); `#555570`/`#8888a0` → `var(--text-faint)` (5 files).
- **Dead code removed** — `apps/web/components/header.tsx` deleted (zero imports; duplicated the app-shell header with non-functional tabs + hardcoded version).
- **Dashboard tabs already lazy-loaded** — verified all 11 admin tabs use `next/dynamic(..., { ssr: false })`; no change needed.

### Verification
- Per-batch: `npx tsc --noEmit` exit 0 after B1/B2/B3; prod `npm run build` clean after every batch.
- Full API regression: **549 passed, 1 xfailed** (API untouched by Phase 6 — baseline unchanged).
- Prod deploy (web only): new BUILD_ID manifest served, `/backtest` 200, `/dashboard` HTML contains skip-link target, `aria-current="page"`, `data-search-open`, and the new search `aria-label`.

### Known gaps
- ~340 buttons still missing explicit `type="button"` (deferred; visual/behavioral risk low, churn high).
- Remote Supabase migration still blocked (placeholder DB password) — unchanged from rc.6.
- Search results list keyed to marker but not yet indexed as a full `combobox` pattern (overlay + focus management shipped in this phase).

## v0.2.0-rc.6 (2026-08-01)

### Phase 5 — Institutional Backtest Engine (Build → Backtest → Optimize → Deploy)

### Added
- **Backtest costs module** (`backtest/costs.py`) — Indian-market cost model: brokerage (₹20 flat equity/options/intraday, ₹20 flat futures, min ₹20), STT (0.1% delivery, 0.025% intraday/futures, 0.0625% options sell-side), exchange transaction charge (0.00297% non-agg F&O, 0.003% equity), SEBI charges, stamp duty (0.003% delivery, 0.02% derivatives), GST. `estimate_cost` returns a segmented breakdown per trade; `estimate_round_trip`; configurable override knobs.
- **Durable candle store** (`backtest/historical.py` + migration `20250801_01200_backtest_persistence.sql`) — `candles`, `corporate_actions`, `backtest_runs` tables in Supabase. `BacktestHistoricalData` loads DB-first, gap-fills from the broker, and write-throughs best-effort (fail-open to in-memory). Corporate-action adjustment (split/bonus price scaling) applied at load; continuous-futures contract stitching (`-CONT`) with proportional back-adjustment on roll.
- **BacktestBroker + realistic fill engine** (`backtest/execution.py`) — MARKET fills at close ± slippage, LIMIT trade-through with expiry, SL/SL-L trigger-then-limit, SL-M trigger, seeded partial fills, fill latency measured in candles. Broker exposes the same contract as PaperBroker and plugs into `ExecutionManager._adapters` as a fake `backtest:{run_id}:paper` user — zero OMS/broker changes.
- **Manager MAX-speed path** (`backtest/manager.py`) — broker-direct replay loop (no portfolio manager): broker `on_candle` before strategy, risk dry-run checks when enabled, position close-out at the end, per-candle snapshots, in-memory trade recording with entry/exit times. Results persisted to `backtest_runs` at completion; `get_run` restores from DB when the in-memory run is gone (restart-safe).
- **Performance extensions** (`backtest/performance.py`) — expectancy & expectancy-per-R (R = average loss), average/median risk-reward ratio, weekday/hour/month trade distributions, and 252-day annualized alpha/beta vs a benchmark (benchmark candles passed from the manager).
- **Optimizer** (`backtest/optimizer.py`) — grid search (≤512 combos), walk-forward (6 windows, train-prior-fold/test-current-fold), Monte Carlo (2000 bootstrap paths over trade PnLs → p5/p25/p50/p75/p95, mean, probability of profit), and OFAT ±20% sensitivity. Lean `_fast_run` path with `candle_slice` support so folds don't reload data.
- **run-v3 route** — backtest any builder (DSL) strategy by `strategy_id`; compiles + validates the DSL, runs it as `GraphStrategy` (same runtime as paper/live), returns the full Phase-5 metrics superset.
- **Compare + exports** — `POST /backtests/compare` (up to 10 run IDs); `GET /backtests/{run_id}/export?format=json|csv|pdf` (reportlab landscape A4 report).
- **Deploy-to-paper** — `POST /backtests/{run_id}/deploy-to-paper` starts the backtested builder strategy in paper mode via the existing graph runner.
- **Data endpoints** — `GET /backtests/candles/{symbol}/{interval}` (durable store read) and `GET/POST /backtests/corporate-actions` (adjustment ingestion).
- **Web UI** (`apps/web/app/backtest/page.tsx` rewrite) — built-in or builder (DSL) source selector, run form (slippage/latency/partial-fill/risk), 14-metric KPI grid (expectancy, expectancy/R, RR ratios, alpha/beta, sortino, calmar), equity + drawdown SVG charts, weekday/hour/month distributions, weekday×hour P&L heatmap, server optimizer tab (grid/walk-forward/Monte Carlo/sensitivity with best-combo highlight), compare-runs tab, trade log, one-click JSON/CSV/PDF export and deploy-to-paper.

### Changed
- `apps/api/backtest/models.py` — `BacktestConfig` gained `strategy_id`, `user_id`, `candle_slice`, `slippage_pct`, `latency_candles`, `partial_fill_probability`, `seed`, `cost`; `strategy_type` now defaults to `""`; `BacktestResult` gained the Phase-5 metric fields.
- `apps/api/replay_engine.py` — optional `broker`/`risk_check`/`bt_user_id` parameters (back-compat kept).
- `apps/api/requirements.txt` — `reportlab>=4.0`.
- `apps/web/lib/api.ts` — `api.backtest` gained `runV3`, `optimize`, `getOptimize`, `compare`, `exportJson/Csv/Pdf`, `deployToPaper`, `candles`, `corporateActions`, `addCorporateAction`; `backtestExportUrl` helper for binary downloads.

### Verification
- Unit: 55 new tests (`test_backtest_{costs,historical,execution,performance,optimizer,routes_v3}.py`). Full suite **549 passed, 1 xfailed** — baseline 485 + 64 Phase-5 tests, no regressions.
- Local Supabase: migration `20250801_01200_backtest_persistence.sql` applied; PostgREST 200 on `candles`, `corporate_actions`, `backtest_runs`.
- Prod (api.ai.trademetrix.tech, authenticated): **20/20 smoke checks** — builder strategy created → run-v3 (DSL backtest, all new metrics present) → get run → JSON/CSV/PDF exports (PDF is valid %PDF bytes) → compare → deploy-to-paper (runner started, then stopped cleanly) → candles endpoint returns data → corporate-actions list 200. Web: new build served (BUILD_ID rotated, `/backtest` 200, chunk contains new UI).

### Known gaps
- Remote Supabase migration still blocked (placeholder DB password) — `backtest_runs`/`candles`/`corporate_actions` persistence on prod is fail-open (in-memory + broker fetch) until the migration can be applied; `POST /backtests/corporate-actions` needs the remote table.
- Prod container needed `docker exec -u root pip install --ignore-installed reportlab` (PIL owned by root) — the image doesn't bake it in yet.

## v0.2.0-rc.5 (2026-08-01)

### Phase 4.3 — Strategy Lifecycle Management (Strategy Builder V2 → full lifecycle)

### Added
- **Version control** — every save of name/nodes/edges/settings snapshots a version (v1, v2, …) into `builder_strategy_versions` (capped at 50, ring-buffer in memory, write-through to Supabase). Restore rolls back any version to a NEW version number (history is never rewritten). Version diff (`/compare`) shows added/removed/changed nodes, edges, params and settings between any two versions.
- **Lifecycle statuses** — `draft → validated → ready → paper/live → stopped → archived` with `published` kept as a legacy alias so existing publish/start routes keep working. Validate promotes draft→validated; the new Ready button marks a strategy deployable; deploy sets paper/live; stop sets stopped; archive is reversible only via clone.
- **Deployment wizard** — paper/live mode (fail-closed: live REQUIRES a broker), symbol, interval, capital, risk (risk-per-trade %, max daily loss, SL %, target %) and schedule (trading days, start/end time, Asia/Kolkata). Persisted as a `deployment` JSONB on the strategy and honored by the runner (mode drives `is_paper`).
- **Validation score** — 5-metric scorecard (quality, risk, complexity, readability, readiness) with overall %, A–F grade and a per-metric breakdown, computed from the compiled graph (`/score`).
- **Strategy logs timeline** — lifecycle (deploy/stop/ready/archive), validation results, signal decisions, order placements, rejections and runner errors recorded per strategy (in-memory ring 500 + write-through to `builder_strategy_logs`); auto-refreshing panel in the builder and pollable via `/logs`.
- **Execution dashboard** — `/strategies` page now shows all running graph strategies with health (ok/degraded), symbol/interval/mode, candles/signals/orders/filled/rejected/errors counters, realized PnL (read-only estimate from the orders audit table — no OMS writes), and a deep link into the builder. Auto-refreshes every 5 s.
- **Runtime instrumentation** in `engine/graph_strategy_runner.py` — per-strategy runtime stats, lifecycle/signal/order/rejection log records, latency tracking, and `get_runtime_dashboard()`/`get_running_strategies()`.
- **Template categories** — `list_templates` now returns the `official` category tag per template.

### Changed
- `apps/api/builder/manager.py` — version-on-save, `get_version`/`get_versions`/`compare`/`set_status`, deployment persistence; module-level `_snapshot_version` (ring-buffer helper).
- `apps/api/routes/v1_builder.py` — new routes: `/ready`, `/deploy` (DeployStrategyRequest with RiskDeployRequest + ScheduleDeployRequest), `/score`, `/logs`, `/compare`, `/dashboard`; validate/start/stop/publish/archive/clone/rollback are lifecycle-aware (status transitions + log records).
- `apps/web/lib/api.ts` — `api.builder` gained `ready`, `deploy`, `score`, `logs`, `compare`, `dashboard`; `start` accepts `mode`.
- `apps/web/app/strategies/builder/page.tsx` — status chips (live/paper/stopped/ready/validated/draft/archived), Versions button, Ready button, working Deploy wizard, validation score panel and auto-refreshing logs panel.
- `apps/web/app/strategies/page.tsx` — live Execution Dashboard section with per-strategy health/orders/PnL.
- `apps/web/components/workspace/strategy-builder/` — new `deploy-wizard.tsx`, `versions-drawer.tsx`, `strategy-score.tsx`, `strategy-logs.tsx`.
- `supabase/migrations/20250731_01100_builder_persistence.sql` — added `builder_strategy_logs` table + `deployment` JSONB column (applied to local Supabase; remote apply still blocked on Supabase DB password).
- `apps/api/middleware/csrf.py` — the INC-013 cookie-rotation fix was present locally but the deployed container still ran the old pre-fix version (cookie was set only on the first request → body token rotated on every `/auth/csrf` while the cookie never updated → every POST after the first returned 403 "CSRF validation failed"). Re-deployed the fixed middleware; rotation now verified live.

### Verification
- Unit: 9 new lifecycle tests (`tests/test_builder_lifecycle.py`) — every-save-snapshots, compare, rollback-bumps-version, rename, status transitions, deployment roundtrip, score structure, logs, template categories. Full suite **494 passed, 1 xfailed** (baseline 485 + 9 new, no regressions).
- Integration (local HTTP): 19-step lifecycle smoke — create → validate (promotes) → ready → deploy paper (persists deployment) → live-without-broker rejected → save creates v2 → compare → score (A) → logs (lifecycle+validation) → dashboard (running=1) → stop → status stopped. All green.
- Restart persistence (local Supabase): strategy written in process A (name v2, ready, paper deployment, ≥2 versions) fully restored in fresh process B.
- Prod (api.ai.trademetrix.tech): full lifecycle via authenticated API — create → validate → ready → deploy paper (runner "subscribed to live tick feed" for NIFTY) → dashboard shows 1 running → stop clean → status stopped. Web: new build served (BUILD_ID rotated, `/strategies` 200).

### Known gaps
- `builder_strategies`, `builder_strategy_versions`, `builder_strategy_logs` tables still MISSING on the prod Supabase (migration blocked on the placeholder DB password) — strategies survive only in-memory on prod; write-through persistence activates automatically once the migration is applied.

## v0.2.0-rc.4 (2026-07-31)

### Phase 3 — Unified Trading Intelligence (`/workspace`)

### Added
- **Universal symbol context** — one active symbol drives the chart, action bar, position card, analyzer, option chain and alert modal (`lib/stores/ui-store.ts`); switching anywhere re-syncs everything.
- **Chart action bar** — BUY / SELL / 🔬 Analyze / ☰ Option Chain / 🤖 Strategy / 📈 Backtest / 🔔 Alert / 📓 Journal for the active symbol.
- **Position intelligence card** (bottom-left tab) — LONG/SHORT + qty, live P&L + %, entry/current/SL/TARGET (OMS auto-bracket defaults −10%/+15%)/RISK/REWARD/RR/product grid, holding time from first fill, actions: Modify (pre-filled drawer), Exit (MARKET close via engine `source:exit_sl`, no cascading brackets), Reverse, Scale In, Scale Out.
- **Order timeline** (bottom-right tab) — Requested → Validated → Sent → Accepted → Filled → Completed mapped from OMS statuses, with rejection reason chips for REJECTED/CANCELLED/EXPIRED.
- **AI trade summary** in the analyzer — rule-based bias (RSI/VWAP/MACD/structure/PCR votes), ADX momentum, risk grade, confidence %, suggested stop/target from S/R levels; explicit "analytics only, not a trading signal" disclaimer.
- **Universal search** — ⌘K / Ctrl+K palette across recents, symbols, positions, orders, alerts, strategies and quick actions, with keyboard navigation.
- **Notifications center** (top bar bell) — order filled/rejected, position closed, broker token invalidated/removed, market feed down/up, strategy started/stopped; unread badge, persist up to 60 events in `localStorage`.
- **Workspace persistence** — active symbol, analyzer/chain open state, bottom tab, chart interval, drawer prefs (paper/product/order type) and recents survive reload (`tm_ws_prefs`, `tm_drawer_prefs`, `tm_recent_symbols`).
- **Option chain slide-over** — CE/PE LTP + OI per strike, ATM highlight, PCR header, per-row Buy/Sell into the drawer (lazy chunk).

### Changed
- `components/chart.tsx` — controlled `interval` + `onIntervalChange` props; chart wrapped in clipped container so the canvas can't intercept panel clicks.
- `components/quick-order-drawer.tsx` — drawer prefs persisted + `prefillQty` support.
- `components/workspace/top-bar.tsx` — search/notifications slots; `watchlist-panel.tsx` reuses shared `alert-modal.tsx`.
- New: `chart-action-bar.tsx`, `position-card.tsx`, `order-timeline.tsx`, `command-palette.tsx`, `notifications-popover.tsx`, `option-chain-panel.tsx`, `alert-modal.tsx` (shared).
- Fixed during verification: React #185 (workspace restore effect depended on whole zustand state → infinite update loop), React #425/#418 hydration (store no longer reads localStorage at module init; prefs applied post-mount; chart height mount-gated), palette dropdown now closes on blur/Escape without blocking the action bar, legacy ⌘K search overlay disabled on `/workspace` (was covering the bottom tabs), `/auth/me` retried 3× before redirecting to `/auth` (transient API burst on cold load), palette data fetched once on mount with `useMemo` hits (was refetch-looping when the host passed unstable callbacks), palette symbol hits normalized to `NSE:` full keys, palette symbol pool seeded from the watchlist feed (production `/market/instruments` catalog is empty until the 02:30 UTC symbol-master sync, and upstream Fyers/NSE symboldumps are unreachable from the VPS — watchlist gives a live, real symbol catalog).
- `infra/production/docker-compose.yml` — API service `ulimits.nofile` raised to 65535 (container was exhausting the 1024 default at ~1021 fds → `[Errno 24] Too many open files` in `core.safe_query`).

### Regression
- `tsc --noEmit` clean; `next build` clean (`/workspace` 17.5 kB, first load 177 kB). Headless Chromium on prod (minted JWT): action bar, ⌘K palette (focus + symbol search via watchlist catalog), option chain, analyzer + TRADE SUMMARY + AI, position tab, timeline stages, notifications, and persistence (active symbol + bottom tab restored — asserted on the active-tab class) all pass. PAGE_ERRORS = 2, all pre-existing chart color-mix parse warnings (no React errors, no 503s); /portfolio /marketdata /trade /portal /dashboard regressions all 0. Screenshots 08–14 in `/root/web-verify/`. Position card verified in its empty state (`No open position`); the filled card (LONG + ENTRY/CURRENT/RISK/REWARD/RR + Modify/Exit/Reverse/Scale) is pending the live Fyers re-auth click (token expired 2026-08-01 00:30 UTC, positions feed returns empty until then).



### Phase 2 — Trading Workspace V2 (`/workspace`)

### Added
- Single-screen trading workspace at `/workspace` (standalone, no admin chrome):
  - **56px icon sidebar** (Home/Trade/Analyze/Automate/Portfolio/Settings) with active-state highlighting.
  - **Top bar** — LIVE/SIM feed status, broker + token status chip (RE-AUTH NEEDED when expired), symbol search with dropdown results (navigates chart), alert count badge with notification shortcut.
  - **Watchlist panel** (left, 238px) — groups (All/Intraday/Options/Stocks/Swing/ETF) persisted in `localStorage` (`tm_watchlist_groups`), pinned favorites (`tm_watchlist_favs`, sort-to-top), filter box, per-row LTP / % / OI / Volume / Trend / mini sparkline / actions (Buy/Sell/🔬/🔔/★). Windowed rendering (only visible rows mounted), sparkline data fetched lazily for visible rows (5m candles, cached per session). Single-click syncs the chart; double-click opens the order drawer. Add-symbol modal with searchable catalog + free-text entry; in-row price-alert modal (crosses above/below, via `POST /alerts/`).
  - **Center chart** — reuses existing `components/chart.tsx`, re-keyed by active symbol.
  - **Analyzer side panel** (right of chart, `next/dynamic` lazy chunk, opened via 🔬 on a row or the market panel) — live price, VWAP, EMA 9/21, RSI 14, MACD/Signal/Hist, ADX, PCR (from option chain), swing structure (HH/HL/LH/LL), SMC support/resistance levels, risk-to-support + RR chips, rule-based AI summary, and Trade / Backtest / Strategy actions (Trade opens the drawer).
  - **Market panel** (right, 268px) — VIX live + change, PCR, OI bias (CE-PE near ATM), S/R levels from 15m swing data, gainers/losers from the live tick pool, AI summary with bullish/bearish/neutral verdict.
- Quick Order Drawer **collapsible Advanced section** (collapsed by default): SL % / Target % (drive the auto-protection preview), trailing-SL toggle + step, risk-per-trade %, capital, expected RR, risk amount vs capital %, estimated margin (client-side placeholder). Order payload is unchanged from Phase 1.

### Changed
- `components/workspace/` — new `indicator.ts` (pure EMA/RSI/MACD/ADX/VWAP/swings/trend/ai-summary), `mini-chart.tsx`, `sidebar.tsx`, `top-bar.tsx`, `watch-row.tsx` (memoized), `watchlist-panel.tsx`, `market-panel.tsx`, `analyzer-panel.tsx`.
- `components/quick-order-drawer.tsx` — Advanced section + SL/Target % now feed the protection preview.
- `CHANGELOG.md` — this entry.

### Regression
- `tsc --noEmit` clean; `next build` clean; `/workspace` route emitted (14.4 kB, analyzer as separate lazy chunk). Headless Chromium on prod (Playwright, minted JWT): sidebar/topbar/groups/market panel all render, 22 watch rows with B/S/🔬/🔔/★ actions, single-click chart sync, double-click opens drawer, Advanced collapsed by default and expands, analyzer computes RSI/MACD/ADX/VWAP/SMC levels + AI summary with real data, 0 page errors on /portfolio /marketdata /trade /portal regression. Expected-only console noise: option-chain 503 for index symbols (no chain exists) and pre-existing chart color-mix parse warnings.

# Changelog

## v0.2.0-rc.2 (2026-07-31)

### Portfolio Home (new user landing)

### Added
- New `/portfolio` page — user home with: Today's P&L (live unrealised from open positions at current market prices + FIFO-estimated realised today from fills), Broker Status (credentials, active flag, token status + expiry countdown), ⭐ Watchlist with per-symbol Buy/Sell wired to the Quick Order Drawer, Recent Orders, Open Positions, and Market Summary index cards. Live ticks via the existing market feed; auto-refresh via react-query hooks.
- `/portfolio` registered as a standalone route; non-admin users now land here after sign-in (previously `/portal`); landing-page CTAs repointed to `/portfolio`.

### Fixed
- Hydration mismatch on `/portfolio` (React #425/#418/#423): greeting/date now mount-gated so SSR (UTC build-time) matches the client's first render.
- Deploy path bug: `app-layout.tsx` was staged flat into `apps/web/` instead of `components/`, silently leaving the old layout live.

### Regression
- `tsc` clean, `next build` clean, deployed to prod. Headless Chromium verification: all six sections render, 12 Buy + 12 Sell actions, drawer opens from the portfolio watchlist, 0 page errors, no admin sidebar on the standalone page.

# Changelog

## v0.2.0-rc.1 (2026-07-31)

### Phase 1 — Quick Order Drawer (TradeMetrix OS)

### Added
- Global quick-order drawer (`components/quick-order-drawer.tsx`) mounted in the root layout, reachable from any page.
- BUY / SELL quick actions on every Market Data watchlist row (opens the drawer pre-set to that side).
- Drawer features: live LTP + change from the market feed, lot-aware quantity stepper (NIFTY 65 / BANKNIFTY 30 / FINNIFTY 60 / SENSEX 20 / MIDCPNIFTY 75), MARKET/LIMIT order type, INTRADAY (MIS) / NRML product, PAPER / LIVE mode toggle (PAPER default), auto-protection preview (SL −10% / Target +15% from entry, mirrors backend auto-bracket), notional + estimated charges, Esc/backdrop to close.
- Order submission reuses `POST /api/v1/engine/trade` with `is_paper` + `source='quick_drawer'`; success invalidates orders / positions / funds queries.

### Changed
- `lib/api.ts` — `engine.trade` payload type extended with `is_paper` / `source`.
- `lib/stores/ui-store.ts` — added `quickOrder` state + `openQuickOrder` / `closeQuickOrder` actions.
- `styles/components.css` — new drawer primitives (`t-drawer-overlay`, `t-drawer`, `t-drawer-header/body`, `t-drawer-label`, `t-seg`, `t-seg-btn`, `t-stepper`).
- `app/marketdata/page.tsx` — Buy / Sell quick actions added to watchlist rows.

### Regression
- `tsc --noEmit` clean, `next build` clean, deployed to prod, drawer compiled into root layout chunk, Buy/Sell into marketdata chunk, page serves 200.

# Changelog

## v0.1.0-rc.1 (2026-07-28)

### Release Candidate 1 — Production Readiness Validation

### Features Verified
- Fyers OAuth login flow (token exchange, encryption, storage)
- Token refresh and expiry handling
- Broker credentials management (create, list, delete)
- Kill switch (enable, disable, status, survives restart)
- Order placement (MARKET, LIMIT, SL, SLM) via paper broker
- Order modification and cancellation
- Position tracking with cross-restart persistence
- Portfolio P&L computation
- Strategy lifecycle (create, deploy, start engine, execute signal)
- Risk engine (market hours, trading window, cooldown, duplicate, kill switch)
- RBAC (admin, user, blocked roles)

### Fixed since previous sessions
- **CSRF race condition** — middleware now stores token on request.state instead of double-cookie
- **Subscription table column mismatch** — code reads `plan` column with fallback to `tier`
- **Order lifecycle** — `NormalizedOrder.insert` field cleaning for empty `id`
- **Paper order risk exemptions** — `MarketClosedRule`, `TradingWindowRule`, `TradeCooldownRule`, `DuplicateOrderRule` now skip for `is_paper=True`
- **Execution manager paper routing** — `_get_adapter()` uses `"paper"` when `req.is_paper` is True
- **PortfolioManager position access** — dict-model safe access in `_sync_positions`
- **Strategy signal validation** — `EngineService.execute_trade()` now sets `is_paper=True` for active PAPER runs
- **Broker resolution for paper trades** — `gate.py` uses `"paper"` broker directly when `order.is_paper` is True
- **Cross-restart position recovery** — `PaperBroker._restore_positions()` reconstructs from filled orders on `connect()`
- **UserStrategyRunner TypeError** — `days_of_week` string/list parsing fix in `_check_square_off()`
- **Engine positions/funds routing** — checks for active PAPER run before querying live broker

### Known Issues
- Fyers token expires ~24h, no refresh_token — user must re-auth (broker limitation)
- Sentry DSN not configured
- Strategy `user_strategies` table has FK constraint requiring direct SQL insert for new strategies
- Marketdata option-chain returns 503 (external API limitation)
- Rate limiter has 60s cooldown after ~40 requests