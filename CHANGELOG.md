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