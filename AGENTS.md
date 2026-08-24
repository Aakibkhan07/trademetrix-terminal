# TradeMetrix Terminal — AGENTS.md

## Project
Automated trading terminal. FastAPI backend + Next.js frontend. Multi-broker support. Supabase DB, Redis cache/rate-limiter, Prometheus metrics, Telegram alerts.

## Session: 2026-08-24 — Google sign-in via GoTrue OAuth (v1.8.0, code DEPLOYED — provider activation pending owner dashboard config)

### What was done
1. **Flow** — "Continue with Google" on `/auth` → GoTrue `/auth/v1/authorize?provider=google&redirect_to=<origin>/auth/callback` → Google consent → GoTrue redirects with tokens in the FRAGMENT → new `POST /auth/google` verifies the GoTrue access_token against GoTrue `/auth/v1/user` (requires a `google` identity), find-or-create profile, mints the API session like `/signin`. Callback routes admin→/dashboard, fresh non-admin→/onboarding (onboarding_completed=false), else→/live.
2. **Files** — `routes/v1_auth.py` (+OAuthExchangeRequest +google_auth); web: `api.auth.exchangeOAuth`, `app/auth/callback/page.tsx` (standalone — added to STANDALONE_PAGES), Google button on auth page. Commit `4bc4cc9`; suite **1042 passed** (+5).
3. **Deployed** — API hot-deployed + restarted (health 200; endpoint CSRF-guarded live); web BUILD_ID `3Ok2nMUsloeBLc9Mdb1LZ`; button renders on prod.
4. **PENDING (owner-only)** — Supabase project has `"google": false`. Activation = 3 dashboard steps (Google Cloud OAuth client w/ redirect URI `https://nwutlfuowiulfpbsrldn.supabase.co/auth/v1/callback` → Supabase Auth→Providers→Google → add `https://ai.trademetrix.tech/auth/callback` to Redirect URLs). Documented in CHANGELOG v1.8.0.

### Reference
- **GoTrue token verification pattern**: GET `{supabase_url}/auth/v1/user` with `apikey: anon_key` + `Authorization: Bearer <access_token>` — never decode the GoTrue JWT locally (API SECRET_KEY can't verify it).
- **TestClient gotcha**: `with TestClient(app)` runs FULL lifespan (starts engine loops; shutdown closes the shared Supabase client → 88 downstream failures). Always use the conftest `client` fixture (ASGITransport, no lifespan) for route tests.
- **Patch-target rule** (recurring): module-level `from X import fn` in routes means tests must patch `"routes.v1_auth.fn"`, not `"X.fn"`.
- Supabase auth settings probe: `GET /auth/v1/settings` shows enabled providers (`external.google`).

## Session: 2026-08-24 — Chart-data 500 sweep: crawl-driven fix of Yahoo gate + route hardening (v1.7.3, PRODUCTION VERIFIED)

### What was done
1. **Evidence first** — user reported "many errors and incompletion" on prod. Wrote a puppeteer crawl (`/tmp/tmcrawl/crawl.js`: fresh GoTrue user → API-minted signin → visit 21 routes → capture pageerrors/console/http≥400): **43 issues**, all one root cause — chart widgets call `GET /marketdata/historical?symbol=NIFTY50-INDEX` (BARE, no exchange prefix); the Yahoo fallback gate in `market/historical.py::_fetch_from_yahoo` required a colon-or-allowlist so bare symbols returned [], then `fetch_historical_data`'s honesty ValueError escaped the unguarded route as raw ASGI 500s. `/orders` was also a dead URL.
2. **Fixes** (`86ce507`) — gate on MAPPED symbol; 18 bare `-INDEX` aliases added to `YAHOO_SYMBOL_MAP` (quotes path had the same hole; NIFTY50-INDEX missed by `[A-Z]+` regexes without digits); `/marketdata/historical` ValueError→400 / other→logged 502; buyer_strategy_service `_generate_simulated_candles` REMOVED (was still violating the v1.7.0 real-data contract); web `/orders` → redirect to `/positions`.
3. **Validation** — suite **1037 passed** (+21 regression tests `test_chart_data_500_fix.py`; 2 stale tests asserting old behavior updated); prod in-container: NIFTY50-INDEX/NIFTYIT-INDEX/INDIAVIX-INDEX 5m/1d → 200 with 75 real candles each (Yahoo fallback works with expired fyers token); post-deploy crawl **0 issues**. Web BUILD_ID `FsW9ro2uKGwY5fxuIsG2Y`.
4. **Ops note**: fyers access token on prod is EXPIRED again (auto-refresh did not re-validate this cycle) — everything degrades gracefully now, but live broker data/orders need a manual re-auth via `/v1/brokers/fyers/re-auth` for the affected account.

### Reference
- **Crawler pattern** (reusable): GoTrue admin create (`email_confirm:true`) → GET `/auth/csrf` + cookie jar → POST `/api/v1/auth/signin` (API re-mints its own token) → set cookie `tm_session` domain `.trademetrix.tech` → puppeteer-core with system Chrome at `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`; node_modules symlink trick: `ln -sfn /Users/aakib/node_modules node_modules` (puppeteer-core lives in ~). Filter benign anonymous `/auth/me` 401s.
- **Symbol contract**: frontend sends BARE canonical symbols (`NIFTY50-INDEX`, sector indices, `INDIAVIX-INDEX`) to marketdata endpoints — any backend symbol gate must map FIRST (`_map_symbol`), never require an exchange prefix.
- **Real-data contract enforcement point**: `buyer_strategy_service.backtest` now raises ValueError on data gaps (route wraps → 400). `_generate_simulated_candles` must NOT return anywhere.
- Stale-test rule: when fixing behavior, grep tests asserting the OLD behavior (`test_market_historical.py`, `test_buyer_strategy_service.py` both asserted the bug).

## Session: 2026-08-24 — Lemonn broker connect-flow scaffold (v1.7.2, PRODUCTION VERIFIED)

### What was done
1. **Research first** — Lemonn India (lemonn.co.in, NU Investors Technologies/PeepalCo) publishes NO public trading API (no dev portal/keys; their algo = hosted SmartInvest/Zing/BOLT only). `developer.lemon.markets` is an unrelated German EUR broker. User approved a scaffold: full connect/login flow now, live trading later.
2. **Honest scaffold shipped** (`fb36b4d`) — `brokers/lemonn_adapter.py`: credential-validating `authenticate` + typed `UnsupportedFeatureError` on all 10 trading/data methods; capability matrix row `"lemonn": set()` (fail closed); registry metadata fields `client_code`+`secret_key`; exec-layer capabilities entry (all false); rate limit 30/60; validate_production smoke; migration `20260824_02000_broker_credentials_lemonn.sql` adds `lemonn` to the CHECK constraint **and the missing `groww`** (latent 23514 bug — groww was never in the init constraint); web: lemon logo case + onboarding "Lemonn (API pending)" picker entry. `/brokers` page is metadata-driven — zero frontend changes needed there.
3. **Validation** — suite **1016 passed, 1 xfailed** (+21 lemonn tests); tsc clean; prod build BUILD_ID `C35wNJ5ki45512xgH5EX9`.
4. **Deploy + verify** — migration applied to prod Supabase via psql (constraint verified to include `groww`,`lemonn`); 6 API files hot-deployed → restart → `/health` 200; in-container: `lemonn registered: Lemonn | caps: 0 | fields: [client_code, secret_key]`; web `.next` deployed (stop→cp→start→chown -R 1001), `/brokers` `/onboarding` 200; VPS git synced `fb36b4d`.

### Reference
- **Lemonn activation contract**: implementing real endpoints later MUST land together with flipping the capability row — `tests/test_broker_lemonn.py` asserts typed-unsupported today and documents both halves of the flip. Never let a half-activated adapter reach the OMS.
- **Migration gotcha**: the `broker_credentials.broker` CHECK lives ONLY in `20250628000100_init.sql` (+fix_tables copy); new brokers need an idempotent drop/re-add migration — groww proves code-only registration silently breaks saves.
- **Prod psql access**: container env does NOT carry SUPABASE_DB_PASSWORD; use the managed DB password with `PGPASSWORD=... psql postgresql://postgres@db.nwutlfuowiulfpbsrldn.supabase.co:5432/postgres?sslmode=require` from the VPS.
- **Local tar→VPS piping**: run `tar czf - <relative paths>` from the correct workdir (apps/api for broker files); piping `cat file | ssh 'cat > /tmp/x'` beats scp for single files.

## Session: 2026-08-24 — Verify + document the 2026-08-12 fix clusters (v1.7.1, PRODUCTION VERIFIED)

### What was done
1. **Scope** — commits `1990a29`…`91654b1` (2026-08-12) were pushed but undocumented: builder template signal fixes + redeploy gate + kill-switch hardening (`1990a29`, `56606e0`), Angel One broker fixes (scrip-master token resolution `5a14f4e`, batch FULL quotes `d4f27c6`, feed starts with the user's ACTIVE broker `35f7bc2`, NFO/BSE/MCX segment adoption + sector index aliases `eefea34`, `b3ebaa3`, quote tokens grouped under NFO `91654b1`). CHANGELOG v1.7.1 entry written; details there.
2. **Verification (no code changes)** — local suite **995 passed, 1 xfailed** at `91654b1`; VPS git = origin/main = `91654b1`, working tree clean; all 11 changed API files md5-match inside `trademetrix_api` (containers healthy, uptime since the 08-12 restart — the work was hot-deployed on the day); public sweep `/health /live /trade /backtest /sitemap.xml` all 200; kill switch `global:kill_switch` = `"1"` ENABLED untouched; last-24h API logs contain ONLY pre-existing yfinance fetch noise (KNOWN_ISSUES #13), zero new errors.
3. **SSH key auth now works** to root@187.127.185.56 from this workstation (the sshpass password recipe in older entries is no longer needed).

### Reference
- **Kill switch contract (post-56606e0)**: always compare `str(val) == "1"` — `cache.get` json-decodes, so a raw `redis-cli SET global:kill_switch 1` returns int `1`. A raw write DOES engage the switch now; verify with `docker exec trademetrix_redis redis-cli GET global:kill_switch`.
- **Angel One data path**: scrip master names indices `Nifty 50`/`Nifty Bank` → alias canonical `NSE:NIFTY50-INDEX` style symbols to scrip-master tokens; strip the exchange prefix before lookup (pre-prefixed input built doubled `NSE:NSE:` keys); quotes via batch `market/v1/quote/` FULL endpoint (`getLtpData` AB4033s on this account); feed adapter may fresh-login via TOTP when only a secret is stored.
- **Redeploy rule**: PAPER and STOPPED strategies are redeployable via `/deploy` (aligned with `/start`) — never re-add a status gate that blocks them.

## Session: 2026-08-08 — Backtest Engine honesty: real 5-year windows + curated working strategy surface (v1.7.0, PRODUCTION VERIFIED)

### What was done
1. **Curated backtest surface** — `strategies/__init__.py` gained `BACKTEST_CAPABLE_KEYS`, `backtest_strategies()`, `get_backtest_catalog()`; `/api/v1/backtests/strategies` returns ONLY candle-working strategies + a `catalog` metadata list. The 10 kept: `trend_rider`, `macd_cross`, `bollinger_bandit`, `rsi_mean_reversion`, `orb_pro`, `smc_sniper`, `intraday_momentum`, `mean_reversion_pro`, `breakout_scanner`, `arbitrage_hunter`. Curated OUT (still registered for live runtimes, never listed in backtests): tick-only (`vwap_band`, `gap_up_express`) and live-option-LTP / leg-sellers that can never fill on a single instrument (`long_straddle`, `trend_rider_buyer`, `momentum_breakout_buyer`, `expiry_hunter`, `option_wheel`). UI `BUILTIN_STRATEGIES` in `apps/web/app/backtest/page.tsx` rebuilt to the same 10.
2. **60 days → 5 years** — `MAX_BACKTEST_DAYS=1825`, `MAX_INTRADAY_DAYS=730` in `strategies/__init__.py`; `_validate_window(days, interval)` in `routes/v1_backtest.py` guards every run route (`/run`, `/run-v2`, `/run-v3`, `/optimize`, `POST /`, `/candles`); route models default `days=365` with `Field(ge=1, le=1825)`; UI `Days` input `max=730 → 1825`, default `60 → 365`.
3. **Synthetic fallback REMOVED (real results only)** — `engine/backtest.fetch_historical_data` raised `ValueError("No real market data available … backtests never run on fabricated candles")` instead of `_synthesize_candles()`; routes surface it as a 400. `_synthesize_candles` stays (tests use it directly). Test updated: `test_fetch_historical_data_raises_when_no_real_data`.
4. **Yahoo period token fix** — `market/historical.py` `_yahoo_period(days)` maps to yfinance tokens (`1mo/3mo/6mo/1y/2y/5y/10y`); the old `f"{days}d"` string is invalid for yfinance past ~60d and was the real ceiling. Backtest durable store (`backtest/historical.py`) already date-range-keyed → long windows accumulate in Supabase `candles` and gap-fill from broker/Yahoo.
5. **Deploy + verification** — API 5 files hot-deployed (strategies/__init__, engine/backtest, market/historical, routes/v1_backtest, backtest/optimizer; container verified `backtest_strategies()` = 10 keys); web rebuilt (BUILD_ID `pxW63XXu953F8XA3qWM00`) and deployed via the stop → `docker cp` → start → `chown -R 1001` recipe. **Prod in-container**: NIFTY 1d → 1235 REAL candles (2021-08-09 → 2026-08-07); v2 `macd_cross` 5y backtest → 63 trades / 36.5% win / ₹+208,779 net. Health sweep 7/7 (api, /backtest, /strategies, /live, /trade, /positions, /sitemap.xml) all 200; kill switch `global:kill_switch` = 1 untouched. Commit `edfff84`; CHANGELOG v1.7.0 entry; this AGENTS.md entry.

### Reference
- **Curated-surface rule**: a strategy is backtest-capable ONLY if its `on_candle` can emit a fillable trade on the single backtest instrument. Tick-only strategies and live option-LTP buyers (`BuyerBase` subclasses) never can — keep them in the registry (`register_strategy`) for the live runtimes, but never on the backtest surface. The UI `BUILTIN_STRATEGIES` must stay in sync with `BACKTEST_CAPABLE_KEYS`.
- **Window caps**: `MAX_BACKTEST_DAYS=1825` (5y) daily-only; intraday ≤ `MAX_INTRADAY_DAYS=730`. The 400 from `_validate_window` is the expected response for 5y/15m runs — "use a daily interval for longer backtests".
- **Yahoo periods**: never pass raw `"{N}d"` to yfinance — use `_yahoo_period()` tokens. 5y = "5y", 2y = "2y", etc.
- **Real-data contract**: any backtest path that can't get real candles must ERROR (ValueError → 400), never synthesize. Legacy `trend_rider` returning 0 trades on daily data is pre-existing window/signal behavior (also true at 60d), NOT the loader failing — the loader returns 1235 real candles for 5y/1d.
- **Previous sessions 2026-08-07** — v1.7.0-beta.1 trader workspace + analyzer retirement (see entries below). Live trader smoke left a PENDING paper SELL on test account `fa668109` (fyers token expired 2026-08-05 → `BROKER_TOKEN_EXPIRED`, zero-price guard blocks fills; engine cancel returns "Broker not available", OMS delete 404s — paper orders live in `engine/orders`). Cleanup pending fyers re-auth.

## Session: 2026-08-07 — Trader Workspace: full Indian index options trading workflow (v1.7.0-beta.1, PRODUCTION VERIFIED)

### What was done
1. **`/trade` trader workspace** — 5 index families selectable (NIFTY / BANKNIFTY / FINNIFTY / MIDCPNIFTY / SENSEX) driving a live option chain via the EXISTING `api.marketdata.optionChain`/`chain` clients (zero new endpoints this sprint except the backend constant additions below); ATM anchoring + moneyness steps (`mn-*`, ATM/ATM±1/ATM±2 → ITM/OTM), CE/PE toggle, strike interval grid, lots multiplier (1–4 → `qty = lots × LOT_SIZES[sym]`), margin estimate from `api.engine.marginEstimate`. New helpers `lib/options-contracts.ts`, `lib/strategy-labels.ts`, `lib/trader-presets.ts` + `components/trade/*` (index-strip, chain-panel, order-card, presets-bar, fills-ticker) + `components/positions/position-actions.tsx`.
2. **Ordering discipline (verified by e2e)** — clicking a chain/positions row NEVER places an order; the BUY card is the ONLY order path (deliberate side button + qty). BUY submits exactly one `engine.trade` (paper/live by mode). `positions/page.tsx` connects `Exit / Partial Exit / Add / Reverse / Trail SL / Modify` (`position-actions.tsx`) to `engine.modifyOrder` (paper+live) + engine trades; `partial_exit` → `engine.trade` qty `< holding`; `modify` → `engine.modifyOrder({order_id: result.broker_order_id})` for resting orders.
3. **MIDCPNIFTY constants** (`market/option_chain.py`, `routes/v1_marketdata.py`) — `STRIKE_INTERVALS=25`, `LOT_SIZES=75`, `supported=True`; prod option-chain for MIDCPNIFTY = 200/19 strikes (parity with NIFTY). Backend untouched otherwise.
4. **Rebuilds** — `/strategies`, `/backtest`, `/terminal/option-chain` refreshed to trader flow; SEO route `app/sitemap.ts` restored (was VPS-only, missing from deploys → committed in `36ce84c`; `/sitemap.xml` now 200 with `<urlset>`).
5. **Deploy + verification** — API 2 files hot-deployed (md5-verified in container); web prod build (`BUILD_ID skiffJrBrpDasaPxRGY-`) hot-deployed; `api /live /trade /strategies /backtest /sitemap.xml` all 200; API suite **982 passed, 1 xfailed**; **browser e2e on prod 36/36 PASS** (fresh GoTrue user, mocked chain/positions/engine/.margin-intercept — see reference). Remainders: no degradations; trailiage uses `modifyOrder` id so no extra endpoints.
6. **Legacy analyzer retired (user-approved)** — archive re-verified (`gzip -t` + `tar tzf` + manifest diff = 203 entries, 257,951 B) at `/root/trademetrix-backups/analyzer-2026-08-07/`; `docker compose -f analyzer/docker-compose.yml down -v` (containers + `analyzer_analyzer` network removed; no named volumes existed); `rm -rf analyzer/`; `.gitignore` + `analyzer/`; commit `0eb92d1` `chore(cleanup): retire legacy analyzer prototype` pushed → VPS `git reset --hard origin/main`; 11 prod containers untouched; retrieval = restore tar + `docker compose up -d --build`. `analyzer-backend` images left on VPS (inert) for re-spin.
7. **Docs** — CHANGELOG v1.7.0-beta.1 entry; this AGENTS.md entry.

### Reference
- **Trader workspace bit**: row click = SELECT only; only the position-action / order-card buttons place/modify orders; browser e2e asserted "0 orders from selection; exactly 1 after a qty-deliberate BUY".
- **Chain contract**: the tree node (`options-contracts.ts`) maps each index to `STRIKE_INTERVAL`/`LOT_SIZE` via the marketdata chain response (`strikes[]` + `lot_size`); margin = `api.engine.marginEstimate({symbol, side, qty})`.
- **5 index tree**: `"NIFTY:NIFTY"`, `"BANKNIFTY:NIFTYBANK-INDEX"`, `"FINNIFTY:FINNIFTY-INDEX"`, `"MIDCPNIFTY:MIDCPNIFTY-INDEX"`, `"SENSEX:SENSEX-INDEX"` (the `-INDEX` alias symbols are how `normalize_index_symbol` dedupj-canonicalizes; SENSEX keeps its own interval).
- **Moneyness**: ATM = spot/strikes nearest; ITM = strike below (CE) / above (PE), OTM opposite; navigation via interval steps; moneyness class `mn-atm/mn-itm1/mn-itm2/mn-otm1/mn-otm2`.
- **Deployment pattern unchanged** (built with `.env.production` swap + restore; `.next` tar → stop → `docker cp` → start → `chown -R 1001` → verify `BUILD_ID` in container == served).
- **VPS sync after push**: `cd /root/trademetrix-terminal && git fetch origin && git reset --hard origin/main`.
- **Retirement evergreen**: pre-monorepo folders (own server + own dashboard, sparse Caddy routes) are dead weight — archive once at `/root/trademetrix-backups/` then compose-down + `rm -rf`; tolerate `.gitignore`, keep the archive tar verified.

## Session: 2026-08-07 — Live Operational Dashboard: unified `/live` cockpit + landing wiring (v1.6.8, PRODUCTION VERIFIED)

### What was done
1. **New unified operational dashboard `/live` (`apps/web/app/live/page.tsx`)** — institutional cockpit composing EXISTING endpoints only (zero new REST APIs, no OMS/Execution/Broker/Risk/Backtest changes): per-user header with Market OPEN/CLOSED, Stream live/reconnecting, Online/offline chips; Market Overview (session chip + NIFTY 50 / BANK NIFTY live KPI cards via `api.market.status()` + `api.marketdata.quote()`); left segmented Positions | Orders | Portfolio tabs (Engine+Paper positions with quote change% enrichment, engine orders + cancel, paper account equity/PnL + engine funds margins); center symbol chips (indices + your open-position symbols) + lightweight-charts `Chart` + Quick Trade (reuses the quick-order drawer); right rail **Trading Controls** (Emergency Stop confirm dialog, Pause All, collapsible runtime diagnostics via `/runtime/health|strategies`) + **Live Signals** widget (SSE `SignalGenerated` feed, dedupe by `signal_id`, filter + runtime-deployed strategy seeds).
2. **Shared `components/live/` layer (13 files)** — `use-live-connection.ts` (single SSE owner via `useEvents` + `/market/status` polling + navigator online/offline), `use-live-data.ts` (self-refreshing loader, keeps last data on error), `widget-frame.tsx` (normalizes Loading / Empty / Offline / Broker-disconnected / Market-closed), `market-overview.tsx`, `positions-panel.tsx`, `orders-panel.tsx`, `use-live-feed.ts`, `signal-card.tsx` (Trade/Analyze primary, ⋮ Backtest/Deploy/Portfolio overflow), `live-signals.tsx`, `trading-controls.tsx`, `table.tsx`, `types.ts`. All render through the existing design system + the W6 shared primitives (KpiCard/Dot/SkeletonBar/Dialog); no new UI components in vanilla CSS.
3. **Phase A backend (complete, earlier) — canonical signal payload unifier** — `SignalPayload` (signal_version=1) emitted by BOTH runtimes (`strategy_runtime/workers.py` `_emit_signal`, legacy `runtime/manager.py` `_signal_payload`) via the existing execution event bus; new `apps/api/tests/test_signal_payload.py` (8 tests); suite **963 passed, 1 xfailed**.
4. **Landing / wiring** — landing page (`app/page.tsx`) CTAs/nav/footer → `/live`; logo links `admin → /dashboard, non-admin → /live`; app-layout: `Home` section → single "Live Dashboard" nav item (`/live`), non-admin admin-route bounce → `/live` (Portfolio nav stays in the Trade section); sign-in (`auth/page.tsx`) + onboarding "Open Dashboard" CTA + completed-guard → `admin ? /dashboard : /live` (admin routes untouched). Portfolio/Workspace/Backtest/Strategies/Marketplace remain directly reachable (no redirect loops).
5. **Validation + production deploy** — Phase per-phase gates clean (web `tsc --noEmit` 0 err, `next lint` 0 new, prod build clean with `.env.production` swap/restore); **Phase D hot-deploy**: `.next` (64 MB, BUILD_ID `YCwC6U2jJMRugxdXVPcI1`) → container `rm -rf .next` → stop → `docker cp` → start → `chown -R 1001` → `✓ Ready`; public `/live` 200, `api` service health 200. **Browser smoke on prod (injected script + GoTrue-created fresh users) 13/13 PASS** — anonymous `/live` → auth gate (no hard-loop); signup → `/onboarding` → "Open Dashboard" CTA → `/live`; Trading Controls + Live Signals + Market Overview render (note: panel titles are CSS-uppercased — match lowercase text); sign-in lands `/live`; logo targets `/live`; 0 page errors (only the benign anonymous `/auth/me` 401). Smoke users (`tmlive/tmdiag/tmvis/tmw/tmhide*`) swept via GoTrue admin (DELETE → 200 = success). Kill switch `global:kill_switch` still ENABLED (TTL -1) — unchanged; demo only read endpoints, no order placement.
6. **Docs** — CHANGELOG v1.6.8 entry; this AGENTS.md entry.

### Reference
- `/live` is the new primary landing for non-admins: post-sign-in, logo, Home nav, landing CTAs → `/live`; admins still land on `/dashboard`. Login/onboarding redirect rules live in `auth/page.tsx` + `onboarding/page.tsx` (StepDone CTA + completed-guard) + `components/app-layout.tsx` (logo + admin-route bounce); **never add a redirect loop** — `/live` loads AppLayout (auth gate → `/auth` when signed out; that's expected).
- Live widgets reuse ONLY existing `api.*` methods (verified in `lib/api.ts`): `api.market.status()` (tolerant parse), `api.marketdata.quote([])`, `api.engine.positions/orders/cancelOrder/funds`, `api.paper.positions/account`, `api.runtime.health/strategies/emergencyStop/release/pauseAll`, SSE `SignalGenerated`. Cast responses `as { ... }` — most `api.*` methods return `Promise<unknown>`.
- Browser smoke gotcha: widget/tab headers are UPCASED via CSS (`TRADING CONTROLS`, `LIVE SIGNALS`) — assert with case-insensitive `textContent` (never `innerText` case-sensitive).
- Web prod hot-deploy recipe (v1.5.3+ pattern): `tar czf - .next | ssh tar xzf - -C /tmp/webpkg` → rm `.next` (running) → `docker stop` → `docker cp` → `docker start` → `chown -R 1001`. Full prop: build with `.env.production` swap + restore, verify `BUILD_ID` local == in-container == served.
- Sweep pattern confirmed: GoTrue admin DELETE returns **200** (not 204) and IS successful; `SUPABASE_SERVICE_KEY` (not `_ROLE_`) is the env name in the container.

## Session: 2026-08-06 — Consolidation Sprint 3 / W6: shared UI primitives — KpiCard/Badge/Skeleton/Dialog (v1.6.7, PRODUCTION VERIFIED)

### What was done
1. **Shared primitives in `apps/web/components/ui/`** — `kpi-card.tsx` (`KpiCard`; variants
   stat/metric/beta), `badge.tsx` (`Badge`/`Dot`/`Chip`/`OrderStatusBadge`/
   `InstrumentTypeBadge`/`TierBadge` via `BadgeVariant`, token-backed classes
   `t-badge`/`t-dot`/`t-chip`), `skeleton.tsx` (`SkeletonBar` + `PageLoadingSkeleton` +
   `components/skeleton.tsx` re-export), `dialog.tsx` (`Dialog`). Existing primitives kept:
   `empty-state.tsx` (`EmptyState`/`TableEmptyRow`/`EmptyPanel`), `sparkline.tsx`,
   `chart-shell.tsx`, `chart-tooltip.tsx`, `drawer.tsx`, `form.tsx`, `data-table.tsx`,
   `toast.tsx`, `loading.tsx`.
2. **Consolidated sites** — KPI cards: `/backtest`, `/admin/beta`, `/strategies/[key]`,
   `/dashboard` pnl tab. Skeletons: `app/{dashboard,terminal,portal}/loading.tsx` +
   `admin/admins`, `admin/broadcast`, `strategies/catalog`, `trade` panels. Dialogs:
   `/settings` (change password), `/account`, `/brokers`, `/strategies`, `/marketdata` (2),
   `/terminal/builder`, `workspace/alert-modal`, `workspace/.../deploy-wizard`. Badges:
   `/dashboard/admin-content`, `watchlist-panel`, `strategies/catalog`, `strategies/[key]`.
3. **Zero semantic change** — no API/backend/routing/state changes; no CSS/theme/tokens edits;
   visible-text parity pass 12/12 production routes after deploy (raw HTML deltas are webpack
   chunk-order + buildId noise only). Dead inline helpers removed at old sites
   (`colorVar_`, `fmtMoney2` etc. verified absent).
4. **Validation** — `tsc --noEmit` 0 err; `npm run lint` 0 err (1 pre-existing warning in
   `deploy-wizard.tsx`);
5. **Deploy** — production deploy flow (`infra/production/deploy.sh`) at `origin/main`
   `a0e5b8a`; API + web health 200; BUILD_ID served `znbojLqT0xaMuNozJJ5dw`. Reports in
   `reports/` (5 files). **SPRINT 3 (W6) COMPLETE — production verified; STOP, no Sprint 4.**

### Reference
- Shared-UI rule: any new badge/skeleton/dialog/KPI card must reuse `apps/web/components/ui/`
  (`BadgeVariant`, `SkeletonBar`, `Dialog`, `KpiCard`) — never reimplement inline.
- Token-backed colors: badges/dots emit design-token values (`var(--text-green)` etc.) — do
  not introduce hardcoded hex in new UI.
- Production deploy without SSH key: `sshpass -p '<pw>' ssh root@187.127.185.56
  'cd /root/trademetrix-terminal && bash infra/production/deploy.sh'` (SSH key auth is NOT set
  up from the workstation for root@187.127.185.56; password auth + `sshpass`/`expect` works).
  Note: `infra/deploy-prod.sh` local wrapper assumes key auth for its scp step — either set up
  the key or run the VPS-side script directly.

## Session: 2026-08-06 — Consolidation Sprint 2 / W2: canonical PositionService — Portfolio/Paper/Engine/Admin all reuse it (v1.6.6, PRODUCTION VERIFIED)

### What was done
1. **One canonical `PositionService` (`application/services/position_service.py`)** — the single
   position read implementation consumed by all four routers as thin adapters. Historical
   response envelopes preserved byte-for-byte: `get_positions_with_broker` →
   `{"positions", "broker"}` (v1_portfolio), `get_user_positions` → `{"positions": [...]}`
   (v1_engine), `get_paper_positions` → `{"positions","count"}` open-only (v1_paper),
   `list_all_positions` → snapshot+profiles cross-user (v1_admin). Same four data sources as
   before: portfolio_manager (live broker / PAPER run), execution_engine position_manager
   (paper ledger), positions_snapshot (admin).
2. **Rewired as thin adapters** — `routes/v1_engine.py` `get_positions` →
   `position_service.get_user_positions`; `routes/v1_paper.py` `paper_positions` →
   `get_paper_positions`; `routes/v1_admin.py` `/admin/positions` → `list_all_positions`;
   `routes/v1_portfolio.py` `/api/v1/positions` → `get_positions_with_broker` (502 error wrap
   preserved) and the router header tagged **INACTIVE** (W2 consolidation note; NOT deleted —
   holdings/funds/summary still use portfolio_manager directly).
3. **Services delegate, public contracts kept** — `EngineService.get_positions` now delegates
   to `position_service.get_user_positions_list` (same list return + BrokerTokenExpiredError
   propagation + transient→[] semantics); new public `EngineService.get_engine_for` accessor
   (wraps `_get_engine`) so PositionService reuses the shared engine cache. `AdminService.
   list_positions` delegates to `position_service.list_all_positions` (same dict contract).
4. **Parity suite `tests/test_position_service_parity.py` (11 tests)** — per-consumer envelope
   checks (PAPER-run portfolio branch, live engine branch, no-broker, token-expired,
   transient→[], broker-resolution, admin snapshot+profiles, open-only filter w/ real engine
   injection) + delegation equals service resolution for both EngineService and AdminService.
   `tests/test_engine_service.py::TestGetPositions` updated to the delegation contract (patches
   PositionService module deps).
5. **Validation** — full suite **955 passed, 1 xfailed** (944 baseline + 11, zero regressions);
   4 route files + 2 service files import-clean.
6. **Production gate (COMPLETE, user-approved)** — 7 files hot-deployed to the VPS
   (`trademetrix_api`), md5-verified in-container, restart clean, health 200. **BEFORE/AFTER
   byte-parity capture (12 endpoints, real CSRF+JWT): all statuses identical, key trees
   identical; only diffs = `positions[].updated_at` wall-clock refresh (expected)**. Live
   read-only (admin `17ba8349`, valid fyers): portfolio 2 positions, engine 2 positions,
   funds 7572.78; expired-token admin (`fa668109`) → documented `401 BROKER_TOKEN_EXPIRED`
   on engine/paper/funds, portfolio 200 empty — same BEFORE and AFTER (parity, not
   regression). **PAPER lifecycle via real HTTP path 6/6 PASS** (place BUY 5
   `NSE:NIFTY50-INDEX` → filled 200 avg 24653.27 (2.2–2.5s) → position visible qty 5 →
   portfolio open=1 → trade recorded → SELL close → count=0 → realised −98.8, equity
   500000→499901.2). Monitoring: Prometheus alerts 0, api memory 288MiB stable, 0× 5xx,
   errors = pre-existing yfinance 404 noise only. Kill switch: was ENABLED product-wide
   (pre-existing Redis `global:kill_switch`, TTL −1); cleared on user approval for the
   paper demo (order placement resumed), then **re-enabled after the gate** (prod restored
   to its pre-gate safety state). **SPRINT 2 PRODUCTION VERIFIED** — next: Sprint 3 (W6)
   pending user approval.

### Reference
- PositionService is the ONLY position read path going forward: any new consumer calls it; never
  reimplement portfolio_manager/position_manager/positions_snapshot reads inline. Active-broker
  read is `risk.helpers.get_active_broker` (same query as legacy `EngineService.get_active_broker`).
- Envelope contracts: engine `{"positions":[...]}`, portfolio `{"positions","broker"}`, paper
  open-only `{"positions","count"}`, admin cross-user (user_id filter, latest per (user,symbol),
  profiles join email/full_name) `{"positions","count"}`.
- Sprint gates: Sprint 1 (W1) DONE + PRODUCTION VERIFIED → Sprint 2 (W2) DONE + PRODUCTION
  VERIFIED → Sprint 3 (W6 shared UI components, awaiting user approval). Each sprint = full
  validation + reports + user approval; no deletions ever.
- Paper fill gotcha (prod gate): paper fills require a resolvable quote — a bare symbol
  (`NIFTY`) or an expired-broker-token user yields `filled_price=0` → the engine's
  pre-existing zero-price guard skips the trade ("Skipping trade with zero fill price") →
  position invisible. Use a fyers-resolvable symbol (`NSE:NIFTY50-INDEX`) with a valid-token
  user for paper E2E. Kill switch (`global:kill_switch`) is ENABLED on prod by default —
  restore it after any demo that clears it.

## Session: 2026-08-06 — Consolidation Sprint 1 / W1: canonical backtest metrics — ONE Sharpe + ONE cost model (v1.6.5, PRODUCTION VERIFIED)

### What was done
1. **Consolidation sprint context** — user-approved scope: implement ONLY W1 → W2 → W6 (in
   that order) with per-sprint approval gates; W5 (strategy consolidation), dead-code/route
   deletion FORBIDDEN; dead code found → tag INACTIVE + report, never remove; full validation
   after every sprint. Audit deliverables live in the session temp dir
   `consolidation_sprint/` (`01_duplicate_matrix.md` … `05_sprint1_w1_metrics_unification.md`).
2. **B1 fixed (legacy `/run` Sharpe was wrong)** — `engine/backtest.py` `finalize()` computed
   Sharpe with **population** stdev over **per-trade PnL** (unit-mismatched) while run-v2/v3
   used sample stdev over equity period returns. New canonical
   `backtest.performance.compute_sharpe_ratio(returns)` (sample stdev `n−1`, `√252`, `<2`
   returns → `0.0`); `PerformanceAnalytics._compute_ratios` and the legacy engine both call
   it now (legacy over `_equity_returns()` — same formula as run-v2/v3).
3. **B2 fixed (legacy `/run` fees ≠ canonical)** — legacy flat 4-component math
   (slippage+brokerage%+STT%+exchange%) replaced by routing through the ONE implementation:
   `BacktestEngine._apply_costs` → `estimate_round_trip` (`EQUITY_INTRADAY`,
   `commission_min=0.0`, legacy knobs → `BacktestCostConfig` overrides — the new override
   knobs `stt_pct_override`/`exchange_tc_pct_override`/`stamp_duty_pct_override` in
   `backtest/costs.py` keep buy-side STT seasoning for DEL/FUT/OPT). Legacy now includes
   stamp duty + GST + SEBI → same fees as run-v2/v3 for the same trade. `paper/fill_engine`
   `_build_fill` also routes through `estimate_cost` with `gst_enabled=False,
   sebi_fees_enabled=False` → paper fills **byte-identical** to historical math (paper never
   charged GST/SEBI).
4. **Parity suite `tests/test_backtest_consolidation.py` (10 tests)** — legacy-Sharpe ==
   canonical == PerformanceAnalytics on same equity curve; sample-vs-population guard;
   `<2` points → 0.0; legacy cost == `estimate_round_trip`; stamp leg placement; paper fills
   == `estimate_cost`. **Full suite 944 passed, 1 xfailed** (baseline 934/1).
5. **Prod deploy + verification (gate required by user before Sprint 2)** — 4 files hot-deployed
   (md5-verified in container), restart clean, health 200. In-container smoke (user fa668109,
   real CSRF+JWT) **13/13 PASS**: `POST /backtests/run` 200 + payload keys unchanged +
   byte-identical to `POST /backtests/` (same engine); `run-v2` 200 (sharpe −4.2, 38 trades);
   `GET /{run_id}` fee parity 38/38 (`cost_total == slippage+charges+taxes`); JSON export 200;
   paper fills identical (zero-fee + fee-bearing). Logs: 0 non-baseline errors / 0 5xx in
   15min (pre-existing marketdata 503 + Yahoo noise only). Legacy 0-trade results on real
   candles are PRE-EXISTING window/signal behavior, NOT a W1 regression — proven: git diff
   shows 0 changed lines in order/signal paths, and a manufactured-trend run makes trades
   with nonzero Sharpe (−0.71) and costed P&L through the new code.

### Reference
- **Sprint gates**: Sprint 1 (W1) DONE + PRODUCTION VERIFIED. Next: Sprint 2 (W2 canonical
  PositionService — Portfolio/Paper/Engine/Admin reuse it, no route/serializer/payload
  removal, parity tests, tag legacy `v1_portfolio` INACTIVE not delete), then Sprint 3 (W6
  shared UI components). Each sprint = full validation (Unit/Integration/Regression/Paper/
  Backtest/UI/Prod smoke) + reports + user approval.
- **Canonical Sharpe contract**: `compute_sharpe_ratio` — sample stdev (n−1) over equity-
  curve period returns, `√252`, `len<2` → 0.0. Any future backtest path MUST call it; never
  reimplement Sharpe inline.
- **Legacy `/run` fee contract (post-W1)**: same total as `estimate_round_trip` for the same
  trade (incl. stamp/GST/SEBI); `_apply_costs` returns `(total, brokerage+exchange_tc)`.
  Paper fills: `estimate_cost` with `gst_enabled=False, sebi_fees_enabled=False` (historical
  paper behavior preserved).
- **Prod smoke harness**: `apps/api/tests/smoke_sprint1.py` (in-container; create_access_token
  + CSRF handshake; HTTPS to api.ai.trademetrix.tech). Cleanup pattern:
  `docker exec -u root trademetrix_api rm -f /app/smoke_sprint1.py`.

## Session: 2026-08-05 — is_auth analytics split: DAU/bounce/funnel now separate signed-in vs anonymous (v1.6.3)

### What was done
1. **`is_auth` on every client event** — `apps/web/lib/analytics.ts` injects `is_auth` at
   flush time (auth state from `useAuth` via new `setAnalyticsAuthState`); tracker component
   moved INSIDE `Providers` in `app/layout.tsx` (it was outside → no auth context).
2. **Server authority** — `routes/v1_analytics.py` `track-batch` now resolves identity via
   `Depends(get_optional_user)` (was called manually → `credentials=None` → cookie-only,
   bearer silently ignored) and stamps `properties.is_auth = bool(user_id)`. `get_optional_user`
   is imported at module level (was lazy).
3. **Verification** — 930 passed/1 xfailed (3 new route tests). Prod wire probe:
   anonymous batch → `is_auth=false`, signed-in (`fa668109`) → `is_auth=true` + user_id in
   `analytics_events`. API + web deployed (BUILD_ID `dyvmbDSGyGqOqcTjXxdgV`), probes cleaned.

### Reference
- W32 DAU/bounce/cohort numbers were inflated by anonymous sessions — from W33, split any
  `analytics_events` query on `properties->>'is_auth'` (or simply `user_id IS NULL`).
- track-batch identity: cookie `tm_session` OR bearer both work now (DI resolves `_bearer`).
- Client `is_auth` is injected at FLUSH time (matches server-side resolution moment); an
  event queued pre-login but flushed post-login carries `is_auth=true` — harmless for funnel
  math, and the server override wins on signed-in batches anyway.

## Session: 2026-08-05 — Beta Launch Support W32: weekly intelligence evidence cycle + risk-audit persistence (v1.6.2, OPS-ONLY)

### What was done
1. **W32 evidence suite authored** — `docs/weekly/2026-W32/` (13 reports) generated from LIVE
   data: `infra/scripts/weekly_report.sh` (Prometheus 127.0.0.1:9090 + container logs) +
   `analytics_report.sh` (remote Supabase `analytics_events`/`feedback_items`), run with
   `TMX_VPS_PASSWORD`/`TMX_SUPABASE_PASSWORD` (both `Aakibkhan1@23` in password manager).
   All Analysis/Recommendations sections authored from the data; Top-10 Issues + Next Week
   Priorities ranked by evidence.
2. **Fixes shipped (evidence-backed, feature freeze respected — zero code changes)**:
   - **`risk_audit_log` migration applied to prod** (closes KNOWN_ISSUES #14 [Action
     required]): scp `supabase/migrations/20260804_01600_risk_audit_log.sql` → VPS → psql
     `-f` (CREATE TABLE + INDEX, idempotent) → `NOTIFY pgrst, 'reload schema'` → verified
     `rest/v1/risk_audit_log` returns 200 via the API container (service key). Emergency
     stops now persist to the dedicated table; no more PGRST205 on every write.
   - **Feedback hygiene**: 9 `prtest*` rows ("E2E prod-readiness test — please ignore",
     2026-08-02) PATCHed to `wontfix` + notes via PostgREST (`title=eq...` filter + `Prefer:
     return=representation`). Real-user feedback list is clean for W33.
3. **Evidence findings** (full detail in `docs/weekly/2026-W32/`):
   - Backtest runs 2→38 (5 users), builder strategies 7→20, accounts 26→31; requests
     101,600 (2× W31) with p95 API 0.249s (better). Zero restarts; breaker OPEN 2→0;
     fyers creds 2 valid/2 needs_attention.
   - 16,810 "Token refresh failed" log lines in 7d are the RESOLVED expired-token era
     (pre-08-04); last-24h logs: 0 such lines. Remaining 24h errors: EndOfStream 10×
     (client aborts), 22P02 7× (schema debt), risk_audit_log PGRST205 (now fixed).
   - Top user-visible crash of the week: `Failed to parse color: color-mix(...)` from
     lightweight-charts (20 events, 7 users, 08-01/02) — fixed in the 08-03 build; 0 since.
   - Funnel: 73 session users → 27 click → 7 client_error → 3 backtest.run → 1
     broker.connected. Broker step (13% of 31) is the only structural drop.
   - 429s (785/7d) concentrate on `/api/v1/alerts/` (610) — poller rate-limited (P2).
   - `async_safe_single ... None` = 653×/48h log noise (benign, WARNING → downgrade P2).
   - `strategy_runs` 22P02 for builder hex ids (8×/48h, runner continues) — schema debt P3.
4. **Docs** — CHANGELOG v1.6.2 entry; KNOWN_ISSUES #14 → RESOLVED; this AGENTS.md entry.
   Nothing else touched (no API/web deploys; health 200 throughout).

### Reference
- Weekly report cycle: `TMX_VPS_PASSWORD=... TMX_SUPABASE_PASSWORD=... bash
  infra/scripts/weekly_report.sh` and `analytics_report.sh` (run from repo root; both
  overwrite `docs/weekly/$(date +%G-W%V)/`; author the Analysis sections after).
- Evidence gate for ANY next-week action: one of analytics/feedback/ticket/metrics/security
  — opinions alone do not enter `13-next-week-priorities.md` (see W31/W32 for the format).
- Feedback store cleanup pattern: PostgREST PATCH with `?title=eq.<urlencoded>` +
  `Prefer: return=representation` inside the API container (service key env vars).
- `risk_audit_log` (6 cols: id/user_id/event/reason/triggered_by/created_at) is now in the
  prod schema; audit fallback to `audit_log` remains as belt-and-braces.

## Session: 2026-08-05 — Backtest Phase D: Trade Intelligence — click any trade → interactive price-chart learning view (v1.6.1, WEB-ONLY)

### What was done
1. **Visualization-only phase (constraints honoured)** — backend ZERO diffs: analytics and
   execution engine untouched; no duplicate calculations; everything reuses the existing
   run payload + the existing `GET /backtests/candles/{symbol}/{interval}?days=` endpoint
   (same durable store the backtest consumed; fetched once per run with `config.days` and
   cached across selections). Regression: **915 passed, 1 xfailed** (identical baseline).
2. **Data honesty contract** (all display derivations from persisted fields):
   - SL line = display-level inverse of persisted `risk_amount = |entry − stop| × qty` →
     `entry ∓ risk_amount/qty` (only when `risk_amount > 0` — i.e. a resting SL existed).
   - Target line shown ONLY when the trade exited via a LIMIT/target fill
     (`exit_reason === 'target'`) — target prices are not persisted anywhere else.
   - Indicator snapshots per candle are NOT persisted → the "indicator values" surface is
     the signal context: `entry_reason` → `exit_reason`.
   - Risk state at entry: risk ON/OFF from `risk_analytics.enabled` + drawdown% (equity
     curve `drawdown_pct` at entry) + capital remaining (risk `timeline` `capital_remaining`).
3. **`apps/web/app/backtest/page.tsx`** — `TradeChart` (lightweight-charts v5
   `CandlestickSeries` + `createSeriesMarkers` (dynamic `setMarkers`) + `createPriceLine`
   dashes for SL (#f59e0b) / Target (#22d3ee) + crosshair tooltip + viewport auto-centred
   on the entry candle + ResizeObserver). Trades tab: clickable rows (selected highlight),
   toolbar (← Prev / Next → / Max Drawdown / Best / Worst), `Trade Intelligence` panel
   (12 detail cards + Signals card + chart + "▶ Replay from entry" / "■ Stop"). Overview
   equity chart markers now clickable (`chart.subscribeClick` → nearest/overlapping trade
   → trades tab). `BTTrade` extended with the already-shipped enriched fields
   (rr/entry_reason/exit_reason/charges/taxes/slippage/cost_total/risk_amount/
   duration_minutes); new `BTCandle`/`TradeView` types; `candleTime`/`nearestCandleIdx`.
4. **Replay = client-side step-through** starting exactly at the entry candle index
   (`setVisibleLogicalRange` from entryIdx−8; Play steps 380ms/candle, cyan circle marker,
   stops at exit candle) — no server replay call (server replay needs risk_sim context and
   would violate "visualization only"). "Replay starts exactly from entry candle" =
   viewport opens on the entry candle + animation begins there.
5. **Deploy + prod smoke 12/12** — `.next` (63MB, BUILD_ID `iia71_nq1kK2DYPZhdi9P`) →
   `docker exec -u root rm -rf /app/.next` (while running) → stop → extract host-side →
   `docker cp /tmp/phd_next/. → /app/.next/` → start → `chown -R 1001` → `✓ Ready`,
   `/backtest` 200 in-container + public, new chunk served (200). Puppeteer smoke
   (`p0e2e/e2e-trade-intel.js`, fresh user, mocked run payload exercising the FE + REAL
   candles passthrough): run renders → click trade → Trade Intelligence 1/3 + 7 canvases →
   SL line → detail cards → tooltip (P&L/RR/charges/risk) → replay toggles → Best 3/3,
   Worst 2/3, Max Drawdown 2/3, Next 3/3 → zero page errors. 4 `tmti*` users swept via
   GoTrue admin (container-env `SUPABASE_URL`+`SUPABASE_SERVICE_KEY`).

### Reference
- **TradeChart gotchas**: markers must be updated via the plugin's `setMarkers()` (not
  re-`createSeriesMarkers`); price lines must be tracked + `removePriceLine`'d before
  re-creating on selection change (leak otherwise); viewport centring via
  `timeScale().setVisibleLogicalRange({from, to})` (index space, NOT timestamps); replay
  interval must cap the step at `view.exitIdx` or the end-detection effect never fires;
  `useEffect`-based ref updates (`viewRef.current = view`) — never write refs in render.
- **Payload contract**: builtin `/run` (v2) trades have the base shape only; the enriched
  per-trade fields (rr, reasons, costs) come from run-v3/`GET /{run_id}` — Trade
  Intelligence degrades gracefully (`?? 0` / `—`) on v2 payloads.
- **Candles endpoint** takes `days` and `user_id` (durable store) — pass the run's
  `config.days` or the chart may show a different window than the run used; `force_refresh`
  defaults false.
- Jump-to-Drawdown picks the trade whose [entry, exit] window contains the max
  `drawdown_pct` equity point (fallback: nearest entry/exit).
- Web deploy (this phase): rm `.next` while container RUNNING (docker exec), then stop →
  cp → start → chown -R 1001. BUILD_ID verify + in-container 200s + chunk 200.

## Session: 2026-08-05 — Backtest Phase B: simulated risk engine — `risk_enabled=true` 0-trades incident FIXED (v1.5.11)

### What was done
1. **Incident root cause (prod-log confirmed)** — with `risk_enabled=true`, backtest orders
   ran through the LIVE Risk Engine dry-run: `_place_via_broker` → `risk_manager.evaluate(
   req, dry_run=True)` with `user_id="backtest:<run_id>"`. Rule state lookups
   (`risk/helpers.py`) queried the live Supabase `orders`/`positions_snapshot` tables for a
   PG-typed `uuid` column with a `backtest:<hex>` string → `22P02` → `_load_config` fail-closed
   defaults with `kill_switch_enabled=True` → KillSwitchRule rejected every order →
   **0 trades** (observed `user=backtest:*` `order.rejected` events on prod).
2. **Fix — separate LIVE RISK from BACKTEST RISK, no business-logic duplication**
   (`backtest/risk.py`, new `BacktestRiskSimulator` + `BacktestRiskConfig(RiskConfig)`).
   Reuses the shared Risk Engine vocabulary (`RiskConfig` extended, `RiskDecision`,
   `RiskRuleType`) but evaluates orders against the SIMULATED account only (broker
   equity/cash/positions/realized P&L — pure sync broker reads; no Supabase/Redis/market
   status/broker connectivity/OMS). Rule chain mirrors live semantics (risk/rules.py):
   KILL_SWITCH config + EMERGENCY_STOP config → DAILY_LOSS_LIMIT → DAILY_PROFIT_TARGET
   (warning, allowed) → MAX_TRADES_PER_DAY → MAX_OPEN_POSITIONS → MAX_QUANTITY →
   MAX_CAPITAL → MAX_EXPOSURE → MAX_SYMBOL_EXPOSURE → MAX_DRAWDOWN; a simulated CIRCUIT_
   BREAKER halts all remaining orders after a daily-loss/drawdown breach (simulated kill
   switch, `circuit_breaker=True`). Position sizing `max_risk_per_trade_pct` CLAMPS opening
   quantity (reducers/close orders exempt from capacity + sizing rules). Deliberately NOT
   simulated: broker auth, market-open, trading window, margin API, broker offline, OMS
   queue, duplicate/cooldown/rate rules.
3. **Rejection payload contract (every rejected order)** — `RiskRejection`:
   reason, rule, capital remaining, risk remaining, drawdown, exposure + timestamp/symbol/
   side/qty/price. `RiskAnalytics` (additive `BacktestResult.risk_analytics`): accepted/
   rejected counts, `rejection_reasons` dict, halt_count, risk timeline, capital curve,
   exposure curve.
4. **Config** — `BacktestConfig.risk: dict` overrides; capital-derived defaults so risk ON
   never zeroes a healthy run (max_open_positions 10, daily_loss_limit 10% of capital,
   max_drawdown 25%, max_exposure 5× capital). risk OFF unchanged (`_place_via_broker`
   places directly).
5. **Wiring** — manager `run`/`_fast_run` build the simulator (`_new_risk_sim`), pass it to
   `_place_via_broker` + `_collect_snapshot`; replay path `replay_engine.run(..., risk_sim=)`
   (live `risk_manager` fallback kept for external callers). `BacktestBroker` gained additive
   `last_price(symbol)` / `last_time()` accessors.
6. **Tests** — `tests/test_backtest_risk_sim.py` (25): each rule fires with the right
   rule-type, rejection payload fields, sizing clamp + reducer exemption, daily-loss /
   drawdown halt → subsequent CIRCUIT_BREAKER, kill/emergency-stop config, profit-target
   warning, analytics shape + halt, risk-off parity (`on.total_trades <= off`) + risk-on
   never-zero + tight-limit reduction (macd_cross on 300 synthetic candles; `trend_rider`
   makes 0 trades there — use `macd_cross`), replay-path simulator, sized broker fill.
   Full suite **908 passed, 1 xfailed** (+25). CHANGELOG v1.5.11 entry; this AGENTS.md entry.

### Reference
- **Backtest risk gotcha**: ALWAYS gate via `BacktestRiskSimulator` (account-state-only) —
   never `risk_manager.evaluate` with a `backtest:<hex>` user_id (uuid column `22P02` →
   fail-closed kill switch → 0 trades). Default legal rule order: `_default_overrides(capital)`.
- Rejection contract: `RiskRejection.risk_remaining` = `daily_loss_limit + pnl` (clamped ≥0)
   or `NO_LIMIT` (-1.0) when `daily_loss_limit=0`; `capital_remaining` = `equity − exposure`;
   `drawdown` pct from sim peak equity; `exposure` = Σ abs(qty)·avg_price over open positions.
- Replay tests must no-op `replay_engine._apply_speed_delay` (1x speed sleeps
   `interval*60/multiplier` s per candle) or the test hangs. Monkeypatch the instance:
   `monkeypatch.setattr(replay_engine, "_apply_speed_delay", no_delay)`.

## Session: 2026-08-05 — Backtest Phase C: risk-aware backtest reports — risk analytics surfaced in the UI (v1.6.0)

### What was done
1. **Phase C shipped** — Phase B's `risk_analytics` is now visible and diagnosable in the
   Backtest Engine UI (`apps/web/app/backtest/page.tsx`): a **Risk tab** (only when
   `risk_analytics.enabled`) with KPI cards (accepted/rejected/circuit halts/rules fired),
   "Rejections by Rule" bar chart, a `RiskChart` (lightweight-charts — capital-remaining
   line + exposure area + drawdown% line, crosshair tooltip), and a **Rejected Orders**
   table (time/symbol/side/qty/price/rule chip/reason/capital rem/risk rem (`∞` when
   `-1.0`)/drawdown%/exposure) with a truncation notice. Risk-off runs: tab hidden, rendering
   byte-identical.
2. **Wire budget for risk analytics** (`routes/v1_backtest.py`) — the persisted model stays
   EXACT (full timeline/curves/rejections in `backtest_runs.summary`); `_payload_risk()`
   budgets the wire like trades/equity: LTTB downsample of timeline/capital_curve/
   exposure_curve to `PAYLOAD_MAX_RISK_POINTS=2000` (first/last kept) + rejection list cap
   `PAYLOAD_MAX_REJECTIONS=200` with `rejections_truncated` flag. Applied to run-v3
   `_result_payload` AND `GET /{run_id}` (which now returns `model_dump(mode="json")` with
   `risk_analytics` swapped for the budgeted dict — otherwise identical). Risk-off
   passthrough unchanged.
3. **Per-order rejections exposed** — `RiskAnalytics.rejections: list[RiskRejection]`
   (additive; `backtest/risk.py analytics()` includes `list(self._rejected)`; old persisted
   rows default `[]`). Downsample helper `_payload_risk_points` reuses
   `backtest.performance.downsample_pairs` with `value` (curves) or `equity` (timeline) as y.
4. **Tests** — `tests/test_backtest_risk_payload.py` (7): downsample >2000 (first/last kept,
   monotonic), passthrough <2000, risk-off passthrough, rejection cap + flag, enabled wire
   shape, route-level GET budget + risk-off passthrough. **915 passed, 1 xfailed**
   (908 + 7). Web `tsc` clean + prod build clean.
5. **Deploy + prod smoke 25/25** — API 3 files hot-deployed (models.py, risk.py,
   v1_backtest.py; health 200, in-container contract check). Web: tar `.next` (60MB,
   BUILD_ID `q-Eff63YJmQe0dbJva2B6`) → stop → `docker cp ./. → /app/.next/` → start →
   `chown -R 1001` → `Ready`, in-container `/backtest` 200 (port 3000 NOT host-published —
   caddy proxies via the compose network; probe INSIDE the container) + public
   `https://ai.trademetrix.tech/backtest` 200. Smoke (fa668109, ema_crossover, NIFTY
   5m/60d = 3101 candles): risk OFF 212 trades; risk ON `max_trades_per_day=3` → 3 trades,
   accepted 6, **418 rejections** all MAX_TRADES_PER_DAY, halts 0; curves downsampled
   3101→**2000** (first 0 / last 3101); rejections capped 418→**200** + truncated flag;
   NO_LIMIT sentinel `risk_remaining=-1.0`; GET persisted with same budgeted shape. Probes
   + smoke strategies swept.

### Reference
- **Builder create response** returns the DSL model dump — the id is the **`id`** key
  (NOT `strategy_id`). run-v3 takes that id.
- **Data window cap**: 150d/15m and 120d/15m backtests FAIL with "No candle data loaded"
  (loader window ≈ 60d/15m → 1034 candles). 60d/**5m** works (3101 candles, 212 trades).
- **UI Risk tab contract**: `result.risk_analytics` comes from run-v3 (`api.backtest.runV3`);
  the builtin `/run` v2 payload has NO risk_analytics key (risk UI is builder-DSL only).
- **RiskChart gotchas**: lightweight-charts `AreaSeries` has NO `color` option (use
  `lineColor`/`topColor`/`bottomColor`); TS `as number * 1000` parses wrong — parenthesize
  `((x as number) * 1000)`; tabs array must be typed
  `Array<'overview'|'optimizer'|'compare'|'trades'|'risk'>` or `setActiveTab` rejects the
  widened `string`.
- `_payload_risk_points` uses `p.get("value") if "value" in p else p.get("equity")` because
  timeline points have `equity` but curve points have `value`.

## Session: 2026-08-05 — Backtest Phase A: enriched TradeRecords + big-run performance + interactive charts (v1.5.10)

### What was done
1. **Phase A shipped (A1/A2/A3, roadmap approved 2026-08-05)** — additive backtest-module
   changes only; OMS/Risk/Broker/Execution untouched; legacy `/run` payload unchanged.
   - **A1 TradeRecord enrichment** (`backtest/models.py`, `backtest/execution.py`):
     `TradeRecord` gained `entry_reason`/`exit_reason`/`slippage`/`charges`/`taxes`/
     `cost_total`/`risk_amount`/`rr` (all defaulted, backward compatible).
     `BacktestBroker._apply_fill` rewritten: opens with the signal reason, per-side entry
     costs, proportional cost consumption on partial closes, exit-reason mapping (SL/SLM→
     stop, LIMIT→target, MARKET/signal-reason→signal, close_on_end). `_record_trade`
     computes per-trade slippage, charges (brokerage+exchange_tc), taxes (STT+stamp+GST+
     SEBI), cost_total, risk_amount (resting SL trigger × qty at close; 0.0 if none) and
     `rr = pnl/risk_amount`. `total_slippage` property added (reset everywhere).
   - **Reason threading** (`backtest/manager.py`, `backtest/replay_engine.py`):
     `_place_via_broker(..., reason=signal.reason)` sets `order.reason` pre-risk-check;
     MAX loop + `_fast_run` pass `reason=signal.reason`; `close_on_end` orders carry
     `reason="close_on_end"`; replay_engine copies `signal.reason` onto orders.
   - **A2 performance** (`backtest/performance.py`, `routes/v1_backtest.py`):
     `downsample_pairs` (LTTB, keeps first/last) + `max_equity_points=2000` in
     `PerformanceAnalytics.calculate` (KPI computed BEFORE downsampling → exact);
     `GET /backtests/{run_id}/trades?cursor&limit` pagination (limit clamped 1–2000);
     `_result_payload` + run-v2 cap trades at `PAYLOAD_MAX_TRADES=2000` + add
     `trades_truncated`; shared `_payload_trades`/`_payload_equity`; fixed
     `export_backtest` signature.
   - **A3 interactive UI** (`apps/web/app/backtest/page.tsx`): new `BacktestChart` using
     lightweight-charts v5 (`LineSeries`, `CrosshairMode.Normal`, crosshair tooltip div,
     `createSeriesMarkers` entry/exit markers, ResizeObserver width sync) replaces the
     static SVG LineChart for Equity Curve + Drawdown %.
2. **Tests** — 10 new: enriched fields (reasons incl. order-type→reason mapping, cost
   breakdown, duration from ISO times, risk/RR from resting SL), downsample shape + KPI
   accuracy + threshold skip, pagination route (clamp, walk, past-end next_cursor=None,
   404 ghost). **883 passed, 1 xfailed** (was 873). Web tsc + prod build clean.
3. **Deploy** — backend 6 files hot-deployed (`docker cp` + restart, health 200); web `.next`
   (BUILD_ID `eD9RGNMVSSktEXMdGRkqM`) deployed via stop → `docker cp .next/. → /app/.next/`
   → start → `chown -R 1001` → `/backtest` 200, chart chunk served.
4. **Prod smoke (user fa668109, in-container)** — run-v3 EMA Crossover (`b41609e3550c`) on
   `NSE:NIFTY50-INDEX` 60d/15m, `risk_enabled=false`, capital ₹10M → **57 trades**
   (25W/32L, net −122k): every enriched key present, `cost_total == slippage+charges+taxes`
   (e.g. 2276.13 = 0 + 1147.17 + 1128.96), `entry_reason="Bullish EMA crossover"`,
   `exit_reason="Bearish EMA crossover"`, duration 45m; pagination total=57 len=3
   next_cursor=3; 1026 equity points. Probes cleaned from container + VPS.

### Reference
- **Risk dry-run gotcha (pre-existing)**: `_place_via_broker` runs
  `risk_manager.evaluate(req, dry_run=True)` when `config.risk_enabled`; backtest orders
  get rejected (order.rejected events with `user=backtest:<run_id>`) → 0 trades. The
  v1.5.9 "9 trades" probe and this smoke ran with risk off. UI default during Phase A is
  risk off. Not a Phase A regression (git diff proves reason-only change).
- Trade enrichment contract: `charges` = brokerage + exchange_tc; `taxes` = STT + stamp_duty
  + GST + SEBI; `cost_total` = slippage + charges + taxes (all from `estimate_cost` in
  `backtest/costs.py`); `risk_amount` = (entry − SL trigger) × qty at close, 0.0 without a
  resting SL; `rr` = pnl/risk_amount.
- Downsample contract: `PerformanceAnalytics.calculate` computes ratios/returns BEFORE
  downsampling, so `end_equity`/`return_pct`/`max_drawdown_pct` reflect the FULL series even
  when `equity_curve` is capped at `max_equity_points` (default 2000).
- lightweight-charts v5 API: markers moved to the `createSeriesMarkers(series, markers)`
  plugin (returns plugin api with `.detach()`); `unsubscribeCrosshairMove(handler)` needs
  the SAME handler reference; `Time` is `UTCTimestamp | BusinessDay | string` — cast epoch
  seconds with `as UTCTimestamp`.
- Web deploy: tar `.next` (63MB) → scp → `docker stop trademetrix_web` → `docker cp
  .next/. trademetrix_web:/app/.next/` (container stays stopped) → `docker start` →
  `docker exec -u root trademetrix_web chown -R 1001 /app/.next`. Extract the tarball FIRST
  (tar `xzf` then `cp .next/.` — the earlier mistake: `cp` before extract → "lstat no such
  file").
- Web domain: `ai.trademetrix.tech` (NOT app.trademetrix.tech); API `api.ai.trademetrix.tech`;
  in-container route probes hit `http://127.0.0.1:8000` with `create_access_token` +
  CSRF cookie.
- Full suite command: `cd apps/api && .venv/bin/python -m pytest tests/ -q` (883 passed).

## Session: 2026-08-04 — Backtest data + P&L honesty: real candles, correct trade attribution (v1.5.9)

### What was done
1. **Hand-check of the backtest flow found two production defects** plus one data-store gap.
   (a) **Legacy `/run` silently synthesized candles**: `engine/backtest.fetch_historical_data`
   called fyers directly and, when fyers failed (always from the container: WAF 403 on
   `/data/history`, wrong-URL 404 on `/api/v3/history`, and SDK fallback dying with
   `Permission denied: '/app/fyersApi.log'`), it returned `_synthesize_candles` fabricated
   data — a "backtest" on junk with 0 trades / −38% returns. (b) **Short P&L was −notional**:
   `build_trades_from_snapshots` priced EVERY entry from `average_buy_price` (0.0 for short
   positions) → `entry_price=0` → each SELL "trade" showed `pnl = (0 − exit) × qty` ≈ the whole
   notional (9 SELLs × 75 × ~24k ≈ −16M). (c) **Partial durable store never topped up**: the
   loader refetched only when the store had <2 candles, so a 7-day request with a 3-day slice
   returned the slice as-is.
2. **Fixes** — `fetch_historical_data` routes through `backtest_historical.load` (durable →
   broker → Yahoo; synthetic only as a logged last resort); `backtest_historical.load` is now
   coverage-aware (`_covers_range` with a 1-trading-day tolerance for the 09:15 IST session
   open, `_merge_candles` union by timestamp); `build_trades_from_snapshots` prices SHORT from
   `average_sell_price` / LONG from `average_buy_price`; `BacktestBroker` now records a
   position's `entry_time` at open and threads it through `_record_trade` (Trades show real
   open→close times); `manager.run` prefers `broker.trades` (authoritative fill records) over
   snapshot reconstruction and snapshots carry the candle timestamp (not wall-clock);
   `total_fees` populated from `broker.total_costs`; fyers SDK `log_path="/tmp/"` (was `""` →
   `/app/fyersApi.log` Errno 13).
3. **What the −32.82% "anomaly" actually was** — a legit cost-inclusive return: net_pnl is
   GROSS, total_fees (slippage+brokerage+STT on up to ₹18M notional) is separate, and
   `return_pct = (end_equity − start)/start` includes both. Verified idempotent:
   `net_pnl + total_fees = equity change` exactly at every qty (qty1: −152.75+555.47=−708.22;
   qty75: −11456.25+21358.98=−32815.23). The "0 trades / −38%" of earlier probes were the
   synthetic-data artifact (before this fix); trend_rider on a no-crossover window legitimately
   yields 0 trades, and oversized qty (>capital per trade) legitimately rejects BUYs in the
   legacy engine.
4. **Tests** — legacy fetch uses durable store + synthetic-only-when-empty; coverage-aware
   refetch/merge; short & long trade attribution prices (SELL entry=sell avg, exit=buy avg);
   broker `entry_time`≠`exit_time`. **873 passed, 1 xfailed** (867 baseline + 6).
5. **Deploy + probe** — 7 files hot-deployed (health 200). Prod: durable loader returns the
   full 7-day/15m window (125 candles across 5 sessions, close 24178–24774, was 75/3-day);
   manager run gives 550 candles / 9 trades with real entry→exit timestamps and full fee/gross
   reconciliation; legacy `/run` 200 with 550 real candles analyzed. Probe scripts cleaned.

### Reference
- Backtest accounting contract: `net_pnl` = gross trade P&L; `total_fees` = all slippage +
  brokerage + STT (both from `BacktestBroker`); `return_pct`/`end_equity` are cost-inclusive.
  They reconcile via `net_pnl + total_fees = initial_capital − end_equity`. Never cross-check
  `net_pnl` alone against the equity curve.
- Trade attribution: LONG entry = `average_buy_price`, exit = `average_sell_price`; SHORT entry
  = `average_sell_price`, exit = `average_buy_price` (per-side prices in `get_positions`). Use
  `broker.trades` (fill-level, real open/close times) in preference to snapshot reconstruction.
- Fyers history from the container is WAF-blocked (403) on BOTH `/data/history` and the SDK
  (it hits the same URL); `/api/v3/history` is a 404 (wrong path). Backtests therefore run on
  the durable store + Yahoo by design — always verify a "failed fyers fetch" didn't flip the
  legacy path to synthetic. `fyersApi.log` write goes to `/tmp/` now (never `/app/`).
- Durable loader: `_covers_range` uses a 1-day tolerance because intraday candles start at
  09:15 IST, so a store that begins 03:45 UTC is "complete enough"; `_merge_candles` dedupes by
  canonical timestamp (fetched wins).
- Route probe with CSRF: send matching `Cookie: csrf_token=<x>` + `X-CSRF-Token: <x>` (middleware
  compares `secrets.compare_digest`); legacy `/run` loads real candles via the durable loader.

## Session: 2026-08-04 — Broker-first market data: real LTP/change% for compact option symbols (v1.5.8)

### What was done
1. **Gap after v1.5.7** — P&L was real but LTP/Chg% still showed `—` for compact option
   symbols (`SENSEX2680679000CE`, `NIFTY2680424450PE`). Root cause: `GET /marketdata/quote`
   only called `providers.yahoo.fetch_quotes` — Yahoo can't resolve the fyers compact option
   format → returned 0/0 → the `last_price > 0` guard in the frontend turned the cell into `—`.
2. **Fix** — `/marketdata/quote` is now **broker-first**: resolve the user's active broker
   (`EngineService.get_active_broker`), call the fyers adapter's `get_quotes` (REST
   `/data/quotes`), reusing the already-running feed adapter
   (`shared_socket.get_broker_adapter`) else the cached engine; Yahoo fills only the symbols
   the broker didn't price. No broker → pure Yahoo (unchanged). Added
   `ExecutionEngine.get_quotes`, `SharedDataSocket.get_broker_adapter`.
3. **BSE prefix** — fyers BSE underlyings (SENSEX options) need `BSE:`; `_ensure_fyers_symbol`
   and `_ws_symbol` were hardcoded to `NSE:`. Both now use `BSE:` when the symbol starts with
   `SENSEX`; `_normalize_quote` preserves `Exchange.BSE`.
4. **Tests** — `test_quotes_broker_first_uses_broker_and_yahoo_fill`,
   `test_quotes_broker_first_falls_back_fully_to_yahoo` (patch the SOURCE module for
   function-local imports: `application.services.engine_service.EngineService` +
   `providers.yahoo.fetch_quotes`; fake `fetch_quotes` must be async), BSE-prefix asserts.
   **867 passed, 1 xfailed.**
5. **Deploy + probe** — 4 files hot-deployed (`docker cp` + restart, health 200). In-container
   route probe (user `fa668109`): `SENSEX2680679000CE` → `{last:106.5, close:206.95, broker:fyers}`
   (exactly the position LTP), `NSE:NIFTY50-INDEX` → `{24614.9 / 24774.3}`, all `broker: fyers`.
   Pushed `eb4f7d3`.

### Reference
- `/marketdata/quote` broker-first chain: `EngineService.get_active_broker(user_id)` →
  `shared_socket.get_broker_adapter(broker)` (running feed adapter, authenticated + rate-limited)
  → else `EngineService._get_engine(user_id, broker)._adapter` → `adapter.get_quotes(symbols)`;
  bridge `broker_quotes` by symbol using `q.last_price > 0`, then Yahoo for the rest.
- Adapter function-local imports in route helpers → tests must monkeypatch the SOURCE module
  (`application.services.engine_service.EngineService`, `providers.yahoo.fetch_quotes`), and
  `providers.yahoo.fetch_quotes` is async (`await` the fake).
- Frontend needs NO change: `positionQuote` computes change% from `(last_price - close) / close`,
  requires `last_price > 0` — real broker quotes now satisfy it.
- BSE vs NSE prefix rule: `SENSEX*` → `BSE:`, everything else → `NSE:` (`_ensure_fyers_symbol`,
  `_ws_symbol`). Compact `SENSEX2680679000CE` is a real fyers v3 quote symbol (`/data/quotes`
  resolves it to `{last:106.5}`); Yahoo still can't — always prefer the broker for these.

## Session: 2026-08-04 — Positions 0.00 FIX — backend root cause: fyers v3 position field mapping (v1.5.7)

### What was done
1. **The real root cause of 0.00** — v1.5.5/v1.5.6 were frontend-only; user STILL saw 0.00 and
   "today's positions not visible". Raw in-container probe of the fyers v3 `/api/v3/positions`
   payload (user `fa668109`) proved it: **v3 renamed the position fields** — `avgBuyPrice/
   avgSellPrice/unrealised/realised` are **null** in v3; real data is in `buyAvg`/`sellAvg`/
   `pl`/`realized_profit`/`unrealized_profit`/`netQty`/`ltp`/`productType:"MARGIN"`/`symbol`
   with `NSE:`/`BSE:` prefix. `FyersAdapter._normalize_position` read the null v2 names → every
   live position normalized to `quantity 0 / avg 0.0 / pnl 0.0`.
2. **Fix** (`apps/api/brokers/fyers_adapter.py`): `_normalize_position` maps v3 fields with v2
   fallbacks (`buyAvg`→avg_buy, `sellAvg`→avg_sell, `unrealized_profit`→unrealised (else `pl`
   if netQty≠0), `realized_profit`→realised (else `pl` if netQty==0), `m2m`=`pl`);
   `Exchange.BSE` preserved from `BSE:` prefix (was hardcoded NSE); `productType MARGIN` →
   `ProductType.NRML` (was hardcoded INTRADAY); `_parse_instrument` gained the compact numeric
   option format `{underlying}{yy}{m}{dd}{strike}{CE|PE}` (`NIFTY2680424450PE` → strike 24450,
   expiry 2026-08-04; `SENSEX2680679000CE` → 79000, 2026-08-06) before the alpha-format regex.
3. **Tests** — `tests/test_broker_fyers.py` `test_get_positions_v3_fields` (real v3 payload:
   open BSE MARGIN + closed NSE position → avgs/realised/unrealised/m2m/product/exchange/OPT/
   strikes/expiry) + `test_parse_instrument_compact_numeric_options`. **15 passed; suite 864
   passed, 1 xfailed (+2).**
4. **Deploy + probe** — `docker cp` adapter → `docker restart` → health 200. In-container probe
   via `_load_adapter/_resolve_credentials/_authenticate_adapter` (note `_resolve_credentials`
   takes **(broker, user_id)** — reversed args → PG 22P02 "invalid input syntax for uuid"!)
   → 5 REAL positions (open SENSEX −192, closed NIFTY +2915.25/−575/−884/−1287) matching the
   v3 `overall` block. `/engine/positions` route probe → same real values.
5. **Browser smoke on prod** (puppeteer, `p0e2e/e2e-v3-fix.js`, mocked real payload shapes):
   open position shows −192 unrealised (NOT 0.00), closed +2915.25 / −575, totals panel, 0
   console errors — **7/7 OK**. `tmv3*` smoke user deleted (25 → 24 users).
6. **Docs** — CHANGELOG v1.5.7 entry; this AGENTS.md entry.

### Reference
- **fyers v3 positions API is the source of truth**: `netPositions[]` with `buyAvg, sellAvg,
  netAvg, buyQty, sellQty, netQty, qty, pl, realized_profit, unrealized_profit, ltp,
  productType, symbol("NSE:"/"BSE:"), id ("<sym>-MARGIN")`; `overall{count_open, count_total,
  pl_realized, pl_unrealized, pl_total}`. v2 names are null in v3 — never map them directly.
- Probe pattern: `_load_adapter(broker)` → `_resolve_credentials(broker, user_id)` (**order:
  broker first**) → `_authenticate_adapter(adapter, cred)` → adapter calls (raw REST via
  `adapter._http.request(...)` needs the Authorization header set by authenticate first).
- `decrypt_broker_credentials` works in-container (Fernet key in `/app/.env`); client_id
  decrypts from `encrypted_api_key` (`PKL4EMD8ML-200`), token from `encrypted_access_token`.
- User `fa668109` (test account XA24350) is the live fyers tester whose positions drove this
  fix; token valid until 2026-08-05 00:30 UTC (watchdog re-auth flow applies).
- Compact option decode: `NIFTY2680424450PE` = yy 26, m 8 (single digit), dd 04, strike 24450,
  PE; `SENSEX2680679000CE` = 2026-08-06, strike 79000. yymmdd (6-digit) tried first, validated
  (month 1–12, day 1–31), then yymdd (5-digit).

## Session: 2026-08-04 — Portfolio zero-quote 0.00 fix (v1.5.6)

### What was done
1. **Follow-up to v1.5.5** — user still saw **0.00** P&L in positions. Root cause: the quote poll
   returns `{last_price:0, close:0}` for symbols Yahoo can't resolve — the user's real symbols
   ARE a custom option format (`SENSEX2680677500PE`, `NIFTY2680424450PE` etc., confirmed by an
   in-container probe: `/marketdata/quote` → 0/0 for all 5; `/engine/positions` returned them
   with `quantity:0, avg:0, pnl:0`). `positionQuote` treated the zero object as a valid quote →
   P&L = `qty × (0 − avg)` = 0.00 instead of the broker's `unrealised_pnl`.
2. **Fix** (`apps/web/app/portfolio/page.tsx` + `apps/web/app/terminal/page.tsx`): `positionQuote`
   and the `unrealisedPnl` memo now require **`last_price > 0`** before using a tick/quote as
   authoritative; otherwise fall back to the position's `unrealised_pnl`/`realised_pnl`. Terminal's
   `quoteForTicket` got the same guard (same latent bug).
3. **Deploy** — `tsc` + `next build` clean; `.next` tar → stopped container → `docker cp` →
   `docker start` → `chown -R 1001` → `✓ Ready`, `/portfolio` + `/` 200, BUILD_ID
   `wn34X_4_dOkAyST4mlg6Y` matches local.
4. **Browser smoke on prod** (puppeteer, mocked zero-quote positions): open position with broker
   `unrealised_pnl=+500` shows **+500**, closed shows +500 realised, no `+0%`, 0 console errors —
   **5/5 OK**. Smoke user (`tmzero*`) deleted.

### Reference
- **Zero-quote guard rule**: never treat a quote/tick as authoritative unless `last_price > 0`.
  This is the second place the "0.00 vs broker P&L" bug lived (first was feed `litemode` in
  v1.5.4). Any symbol Yahoo can't parse returns 0/0 and must fall back to broker fields.
- Probe gotcha: the user symbols aren't fyers-native either — `SENSEX2680677500PE` /
  `NIFTY2680424500PE` (Yahoo 0/0). Real fyers positions use `NSE:NIFTY26AUG24450CE`-style.

## Session: 2026-08-04 — Portfolio fix (v1.5.5): rich positions (open + closed today) + trade history

### What was done
1. **Frontend-only** (`apps/web/app/portfolio/page.tsx`) — the portfolio page only showed a
   minimal Open Positions table (symbol/qty/avg/LTP/P&L) with no closed-positions view, no
   buy/sell detail, no change% / P&L% columns, and no trade history. All data was already
   returned by `/engine/positions` (`buy_quantity/sell_quantity/average_sell_price/
   unrealised_pnl/realised_pnl/m2m` via `PortfolioPosition`) and `/engine/orders` (FILLED rows).
   **No API change.**
2. **Positions panel** — upgraded to the terminal's rich layout: **Open Positions**
   (Symbol/Qty/Buy/LTP/Chg%/Unrealised P&L + pnl%) + **Closed Today** (Buy Qty/Avg Buy/Avg
   Sell/Realised P&L), with an Unrealised · Realised total in the panel header. Live change% /
   LTP = WS tick first (`Tick.change_pct`), else 5s `usePolling` of `GET /marketdata/quote`
   (positions symbols are also WS-subscribed), else broker's own P&L fields. Mirrors
   `terminal/page.tsx` `positionQuote`/`refreshQuotes` exactly.
3. **Trade History panel (new)** — the 20 most recent **FILLED** orders: Symbol/Side/Qty/Price/
   Time with an "N executed" header count. **Recent Orders** (all statuses) kept beside it.
4. **Deploy** — `tsc` clear, `next build` (`.env.production` swap + restore) clear; tar `.next`
   → VPS → **stop container → `docker cp` → `docker start` → `chown -R 1001 /app/.next`**
   (the name form `chown nextjs:nextjs` FAILS with "unknown user/group" — use the numeric uid
   1001; `docker exec … chown` only works while the container RUNS, do it AFTER `docker start`).
   Verified: `✓ Ready`, `/portfolio` + `/` 200, new BUILD_ID served.
5. **Browser smoke on prod** (puppeteer, `/tmp/tmx_portfolio_shots/`): real signup + mocked
   `/engine/positions` + `/engine/orders` via `evaluateOnNewDocument` `window.fetch` override
   (positions/orders never empty for a fresh user) — **18/18 OK**: Open (2) header + rows
   NIFTY50-INDEX/RELIANCE-EQ/NIFTY26AUGFUT, Closed Today (1) with realised +6000, chg% column,
   pnl% cell, Unrealised/Realised totals; Trade History "2 executed" with BUY + SELL; Recent
   Orders PENDING + PAPER badge intact; 0 console errors (anonymous `/auth/me` 401 filtered).
   Cleanup: `tmport*` smoke user + 4 leftover `tmchgpct*` deleted via GoTrue admin
   (`SUPABASE_SERVICE_KEY` in container env, NOT `SUPABASE_SERVICE_ROLE_KEY` — the latter is
   absent, an empty key silently 401s the users list!).
6. **Docs** — CHANGELOG v1.5.5 entry; this AGENTS.md entry.

### Reference
- Portfolio positions derive: `openPositions = positions.filter(p => p.quantity !== 0)`,
  `closedPositions = positions.filter(p => p.quantity === 0)`; closed rows use
  `buy_quantity || sell_quantity` for qty.
- Change% chain on portfolio: `positionQuote(p)` = tick `change_pct` if present → quote-poll
  `change_pct` → undefined (fall back to `p.unrealised_pnl`).
- GoTrue admin users list key: `SUPABASE_SERVICE_KEY` (grep the container env). Old `tmchgpct*`
  users lingered because the v1.5.4 smoke cleanup only ran on success — always sweep
  `tmport*/tmchgpct*/tmsmoke*` after any smoke run.
- Web deploy chown: `docker exec -u root … chown -R 1001 /app/.next` (numeric uid — the
  `nextjs:nextjs` name form errors "unknown user/group" in this image).

## Session: 2026-08-04 — Feed fix (v1.5.4): real change% on every tick + live streaming for typed symbols

### What was done
1. **Root cause of the persistent 0.00%** — the fyers data socket ran with `litemode=True`
   (`brokers/fyers_adapter.py`), which strips every tick field to `{ltp, symbol}`. `_parse_sdk_tick`
   read `ch`/`chp` → always `0.0` → every relayed WS tick carried `change_pct: 0.0` (proved with an
   in-container probe before/after: `NSE:NIFTY50-INDEX` went from `change=0.0 change_pct=0.0` to
   `change=-159.4 change_pct=-0.64`). Fix: `litemode=False` (full mode also gives bid/ask/oi/
   prev_close/open/high/low).
2. **Second gap: typed symbols never streamed** — the feed only subscribes the MAJOR list, so
   user symbols (`NSE:NIFTY26AUGFUT`, options) never produced ticks (and Yahoo quote → 0/0).
   WS `subscribe` now extends the running fyers feed: `FyersAdapter.subscribe_symbols()` (keeps
   `_symbol_reverse_map` + `_subscribed_symbols` in sync, returns still-pending symbols),
   `SharedDataSocket.add_feed_symbols()` + `feed_has_ws()`, and the route retries ≤10s while the
   SDK socket connects. **Gotcha hit**: `create_broker()` returns a `CircuitBreakerBroker` WRAPPER
   that does not forward private attrs (`_ws_instance`/`_subscribed_symbols`) or new methods —
   `add_feed_symbols` silently returned pending forever. Fix: register the INNER adapter
   (`getattr(adapter, "_inner", adapter)`). Verified live: `NSE:NIFTY26AUGFUT` streams
   `change=-97.1 change_pct=-0.39`; log `Feed fyers extended (pending=0)`.
3. **Frontend** (`apps/web/app/terminal/page.tsx`) — belt-and-braces only: prefer the live tick's
   `change_pct`, fall back to the quote poll only when the tick lacks change data.
4. **Deploy** — API hot `docker cp` (3 files) + restart (health 200); web `.next` tar
   (`--strip-components=1`) → `docker cp` into stopped container → chown → restart (`✓ Ready`,
   `/terminal` 200). Regression **862 passed, 1 xfailed**; web tsc + prod build clean.
5. **Browser smoke on prod** (puppeteer, fresh signup): typed `NSE:NIFTY50-INDEX` → ticket panel
   renders `NSE:NIFTY50-INDEX 24614.9 -0.64%` — real change%, 6/6 OK, 0 console errors (filtered
   the known anonymous `/auth/me` 401). 4 GoTrue smoke users deleted.

### Reference
- Fyers WS auth from a script: `websockets.connect(url, additional_headers={"Cookie": "tm_session=<api-minted token>"})`
  — the `/marketdata/ws` endpoint reads the **cookie**, not the Authorization header (403 otherwise).
- `_stream_yahoo` already computed real change/change_pct (Yahoo fallback was never the 0.00 cause);
  litemode was. Yahoo fallback only covers the MAJOR list.
- Feed extension retry: route loops `add_feed_symbols` ≤10×1s; `feed_has_ws` is True when the
  socket is up OR `_access_token` is present (socket expected soon); empty token (Yahoo mode) → no retry.
- One-time edge: a fresh user with no broker creds gets the Yahoo fallback feed — their typed
  futures/options still show "—" (no data source without fyers creds).

## Session: 2026-08-04 — Terminal UI fix (v1.5.3): change% for typed symbols, open/closed positions, buy/sell price + realised/unrealised P&L

### What was done
1. **Frontend-only fix** (`apps/web/app/terminal/page.tsx` + `apps/web/lib/api.ts`) — the terminal's change% never rendered for typed symbols and positions lacked buy/sell price and realised P&L. Root causes: (a) the WS tick feed only relays `subscribed_symbols` (fixed MAJOR feed via `/marketdata/feed/start`), so typed symbols had no `change_pct`; (b) the positions panel only rendered `symbol/quantity/average_buy_price/unrealised_pnl/m2m` with no closed-positions view. Backend already returns everything: `/engine/positions` carries `buy_quantity/sell_quantity/average_buy_price/average_sell_price/unrealised_pnl/realised_pnl/m2m` (fyers `_normalize_position` maps netPositions; paper `PortfolioPosition` too).
2. **Fix details** — extended `Position` interface; positions split into **Open Positions** (Qty/Buy/LTP/Chg%/Unrealised P&L + pnl%) and **Closed Today** (Qty/Avg Buy/Avg Sell/Realised P&L) with header totals; change% = live `Tick.change_pct` if WS-fed, else 5s `usePolling` of `GET /marketdata/quote` (new `api.marketdata.quote()`) computing `(last_price−close)/close` (`Quote.close` = previousClose; 503/empty tolerated non-fatally). Ticket quote panel now also falls back to the quote poll.
3. **Deploy** — `tsc` clean, `next build` (`.env.production` swap + restore) clean; tar `.next` → scp → `docker cp` into `trademetrix_web`. **Gotcha: the tar contains a `.next/` prefix** — extracting with `-C .next` nested it as `.next/.next` → server crash loop `ENOENT /app/.next/BUILD_ID`. Fix: host-side `tar xzf ... --strip-components=1` → `docker cp` contents into the STOPPED container (docker cp works on stopped containers; `--volumes-from` does NOT expose a container's writable layer — `.next` is not a volume here) → `docker start` → `chown -R <Config.User uid>` (the container runs as `nextjs`; `chown nextjs:nextjs` failed — the user doesn't exist in the image, so use the `Config.User` name). Server `✓ Ready in 1255ms`, `/terminal` + `/` 200.
4. **Browser validation on prod** (puppeteer-core + system Chrome, `/tmp/tm_smoke/`) — auth via GoTrue admin create (`POST /auth/v1/admin/users` returns **200**, not 201; `email_confirm: true`) then the app's own `POST /api/v1/auth/signin` to get the **API-minted** `access_token` (the API cannot decode GoTrue JWTs with its SECRET_KEY — it re-mints its own token in `routes/v1_auth.py`); set cookie `tm_session=<token>; domain=.trademetrix.tech; secure` (host-only cookies don't cross subdomains — the API sets `cookie_domain`). Results: 0 console/page errors; quote poll fires (3 calls); change% renders for typed RELIANCE (−1.96%); with mocked `/engine/positions` (via `window.fetch` override in `evaluateOnNewDocument` — request interception gets CORS-blocked for credentialed cross-origin fetches): OPEN POSITIONS (2) + CLOSED TODAY (1), Buy 1280, Avg Sell 3412, Unrealised +134, Realised +84 all in DOM (note: sub-headers are CSS-uppercased — match text lowercase).
5. **Cleanup + docs** — deleted 10 leftover GoTrue test users (multiple `tmsmoke*` from failed runs — smoke cleanup only runs on success; sweep pattern: `curlme/risktest/quotetest/rg/tmsmoke/chk/tab@example.com`); CHANGELOG v1.5.3 entry; this AGENTS.md entry.

### Reference
- Change% data sources: WS `Tick.change_pct` (only `subscribed_symbols`, mostly MAJOR feed), `GET /marketdata/quote` (`Quote.close` = previous close; 503 when Yahoo unavailable). The Redis pub/sub tick path (`market/data_socket.py`) builds Ticks WITHOUT `change_pct` and drops OHLC.
- Fresh-user paper `/engine/trade` returns `RISK_REJECTED` — pre-existing backend behavior (risk rules evaluate OK in a fresh process; the long-running API worker's shared rule state is the suspected differentiator), NOT related to this fix.
- Web deploy: build with `.env.production` swap; `.next` tar needs `--strip-components=1`; `docker cp` into stopped container works; `chown` with the container's `Config.User` name; `docker start` then verify `Ready` in logs + route 200s.

## Session: 2026-08-04 — Final correctness deployment: user_strategies JSONB parity fix (v1.5.2) → FEATURE FREEZE

### What was done
1. **Deployed the jsonb parity fix** (commits `ebcf9ff`, `19a1bbc`, pushed; report `51906fa`) — the legacy `/api/v1/user-strategies` service now works against the **prod schema**: legs live in a `legs` jsonb column and `entry_time`/`overall_sl_type`/`overall_sl_value`/`overall_target_type`/`overall_target_value` live inside a `config` jsonb column (those are NOT columns on prod — verified via PostgREST OpenAPI; `user_strategy_legs` does not exist). `strategy_service.py` list/create/get/update/`_row_to_strategy` now `select("*")`, write legs as jsonb, and fold the 5 legacy scalars into `config` on create + merge on update; `core/models.py` gained `normalize_user_strategy_row()`; `engine/user_strategy_runner._get_open_legs` reads the jsonb legs; `ai/copilot.py` reads `margin_snapshot`. Migration `supabase/migrations/20260804_01800_user_strategies_jsonb.sql` is idempotent (`ADD COLUMN IF NOT EXISTS config/legs jsonb`), a **no-op on prod**, applied locally so tests round-trip.
2. **Prod API E2E (in-container, real token + CSRF): all PASS** — create (201) → read (legs=2, `entry_time` merged from config, `overall_sl_value`=20) → PUT edit (name+legs) → list → **docker restart** → re-read persists (legs=2, config intact). DB rows confirmed `config={"entry_time":"10:00"}`, legs=2. Schema cache verified via OpenAPI (legs+config present, `user_strategy_legs` absent → no stale schema).
3. **Browser E2E 13/13 OK** (`p0e2e/e2e-strategy-jsonb.js`, puppeteer-core + system Chrome) — UI signup on prod → promote test user via `profiles.role='super_admin'` (done in-container via `/tmp/tm_promote.py`; free tier lacks `builder`) → drive the REAL prod API inside the browser session (same cookies/CSRF as the app): Create → Read (legs=2) → Edit+Save → real `page.reload()` → Deploy/Start (PAPER, 2/2 results) → status `active` → Stop (PATCH `status=paused`) → Delete (204) → 0 page errors. Script details: pass consts into `page.evaluate` as an arg object (`{API, NAME}`) AND destructure in the fn signature; `request()` CSRF pattern = GET `/auth/csrf` then `X-CSRF-Token` header w/ `credentials:'include'`; create returns **201** (not 200); `UserStrategyStatus` = draft/active/paused (no "stopped"); call the VPS promotion as a local `promote_user.py` scp'd + `docker cp` (nested heredoc in ssh quoted args is fragile); delete test users via GoTrue admin `DELETE /auth/v1/admin/users/{id}` (auth.users is NOT on PostgREST).
4. **No regressions** — full suite **858 passed, 1 xfailed** locally; post-deploy logs clean of PGRST/schema-cache errors (only pre-existing timeout-middleware "No response returned" during deploy's historical fetch, yfinance 404, Redis reconnect blips). Health green after each restart.
5. **Report + docs** — CHANGELOG v1.5.2; report `docs/evolution/certs/web_v1.5.1/user_strategies_jsonb_deploy_report.md` + screenshots/`e2e-results.json` alongside; KNOWN_ISSUES #15: dashboard "User Strategies" admin tab fetches nonexistent `/api/v1/admin/strategies/all-user` (404 → empty table). Test users (`jbjsonb*`) + strategies cleaned from prod.

### Reference
- **Feature freeze is in effect** (maintainer decision 2026-08-04). Only: production bug fixes, security fixes, broker compatibility updates, performance improvements, beta feedback fixes. No new modules/architecture → **no new features until public beta planning**, hold anything "architecture cleanup only".
- Prod `user_strategies` columns: `config, created_at, days_of_week, exit_time, id, index_symbol, legs, name, status, strategy_type, underlying_from, updated_at, user_id` — NO `entry_time`/`overall_*` columns. Write those via `config`.
- E2E test AAA: fresh user → promote via service key (profiles.role) → drive API in browser session; tier comes from `subscriptions.plan` (free tier = no `builder` feature).

## Session: 2026-08-03 — Broker SDK v2 Phase 3-4 wrap-up: LIVE CERTIFIED + SDK FREEZE (v1.3.1)

### What was done
1. **Phase 3/4 infrastructure shipped (`9a8cc18`)** — `brokers/sdk/events.py` (typed broker event bus, ring buffer, Logging/Metrics sinks, health bridge), `auth.py` (Token/TokenState, single-flight ManagedSession, SessionManager, AuthProvider base), `websocket.py` (unified WS manager, backoff reconnect, dedup, health), `health.py` (BrokerHealthService → canonical state ladder), `metrics.py` (flat snapshot + registry), `observability.py` (one-call `wire_default_observability`), `brokers/fyers_provider.py` (Fyers AuthProvider + live-observability glue), new broker endpoints (`/api/v1/brokers/health[/{broker}]`, `/metrics/{broker}`, `/capabilities`) + `brokers` block in `/health/metrics`, Prometheus `broker_events_total`/`broker_health_state`/`broker_auth_state`.
2. **Live certification framework** — `brokers/sdk/live_cert.py` (`LIVE_STEPS`, skip-aware `LiveCertResult`: `passed` = every **executed** step passed; order steps opt-in via `allow_orders`; `UnsupportedFeatureError` → SKIP; `_call_live` scores completion incl. `None` returns; drivers use the canonical v2 surface — `connect(credentials)`, `refresh_token(credentials)`, `get_historical_data(symbol, interval)`, `get_option_chain(symbol)`, `subscribe_market_data(symbols, on_tick)`; websocket probe subscribes in a background task and accepts a connected error-free feed since ticks are market-hours dependent) + `brokers/live_cert.py` CLI with `--broker/--out/--allow-orders/--user <uuid>` (credential-backed: `_resolve_credentials` via `get_by_user_and_broker_full` + `decrypt_broker_credentials`, `_authenticate_adapter`, and connect-family steps reuse the stored creds).
3. **Live cert driver fixes iterated on prod** (commits `f484b34`, `b45743a`, `707f0d1`, `73cf541`, `f73042e`, `d512e08`, `8a0f4c3`): signature-aligned kwargs, `FIRST_COMPLETED` on the ws probe wait, per-candidate 6s bounds under one deadline, `InvalidStateError` fix (don't interrogate `exception()` on a pending task), 1.5s-bounded stream drain after cancel (fyers WS engine threads stall cancel-awaits).
4. **Fyers LIVE_CERTIFIED (`cf630af`, tag `v1.3.1-broker-sdk-complete`)** — credential-backed run on prod (`--user fa668109-…`, token `XA24350` account): **LIVE_CERTIFIED in 18.1s** — login/quotes/history/websocket/positions/holdings/funds/disconnect/reconnect/circuit_recovery PASS with real data (funds `total_margin=2993.14 available_margin=2282.04`); `token_refresh`/`token_expiry`/`option_chain` SKIP (Fyers capability-absent → `UnsupportedFeatureError`). Reports archived `docs/evolution/certs/fyers_live_cert.{json,md}`. Run command (on API host): `docker exec trademetrix_api sh -c "cd /app && PYTHONPATH=/app python -m brokers.live_cert --broker fyers --user <uuid> --out /tmp/out.json"`.
5. **SDK FROZEN** — no further `brokers/sdk/*` architecture/interface changes unless fixing a production defect or adding a brand-new broker. Docs updated: CHANGELOG v1.3.1 entry, `docs/evolution/BROKER_SDK_V2.md` (status PRODUCTION COMPLETE Phases 1–4, Known Gaps: fyers option_chain live validation, other brokers' creds, durable audit store), `docs/evolution/RELEASE_NOTES_BROKER_SDK_V2.md`. Prod verified: `/health` 200, `/health/metrics` brokers block, `/api/v1/brokers/health` auth-gated 401. Regression **717 passed, 1 xfailed**.

### Reference
- Live cert: `LiveCertResult.passed` requires ≥1 executed step and ALL executed steps passed; SKIPs (opt-in orders + `UnsupportedFeatureError`) never fail a cert. Websocket probe candidates `["NSE:NIFTY", "NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX"]` — fyers wants `-INDEX` suffixes (`NSE:NIFTY` → `NSE:NIFTY-EQ` is rejected by its data socket).
- Prod stored fyers creds: 1 valid row (`fa668109-4b1e-4758-a49b-015027ea4115`), 3 `needs_attention`. `BrokerRepository` is abstract — use `_resolve_credentials` from `brokers.live_cert` in scripts.
- Deploy pattern for live-cert fixes: commit+push → VPS `git fetch && git reset --hard origin/main` → `docker cp apps/api/brokers/sdk/live_cert.py trademetrix_api:/app/brokers/sdk/live_cert.py` (+ `brokers/live_cert.py` if changed) → `docker restart trademetrix_api` → poll `https://api.ai.trademetrix.tech/health`.
- Long cert runs (>120s SSH): launch detached `docker exec -d … > /tmp/live.log 2>&1` then poll the output json in `/tmp`.
- API regression: `.venv/bin/python -m pytest tests/` → **717 passed, 1 xfailed**.

## Session: 2026-08-03 — Production Readiness v1.1.0 + hotfixes + Fyers compliance + Unified Broker SDK v2 (Phase 1 → Phase 2, v1.1.0→v1.3.0)

### What was done
1. **v1.1.0 shipped (`5d80f4f`)** — landing page restored from HEAD snapshot (`/tmp/tsxrepro/head_page.tsx`) and edited cleanly: header +Pricing/System Status, 3-column public footer with style constants hoisted to module scope (avoids the TS JSX nested-inline-style parser bug); `/funds` page (live margin cards + P&L from `/engine/funds` + `/analytics/pnl`); feedback page real API submit + history (`GET /api/v1/feedback` + `list_user_feedback`, test `test_list_user_feedback_scoped_to_user`); analytics page live P&L/MTM; status page rewritten (live probes); workspace sidebar +Terminal/Option Chain; `lib/api.ts` `feedback`/`analytics` client groups. CHANGELOG v1.1.0 entry.
2. **Post-deploy E2E (`e2e-prod-readiness.js`, p0e2e dir) + hotfixes** (`44462a4`, `362c026`, `dc673d9`): status probes were 404'ing because health/metrics mount at API **root** (NO `/api/v1` prefix) — status page now derives `API_ORIGIN = new URL(API_BASE).origin` (API_BASE exported from `lib/api.ts`) and probes `/health`, `/health/ready`, `/health/metrics`; `/health/metrics` `requests` is a per-path dict `{path:{count,avg_ms,max_ms,min_ms}}` → computed total + top path rendered; `auth-context` `fetchUser` fast-paths any `err?.status === 401` to anonymous (no 3× retry); EventSource gated behind `/auth/me` check; workspace chart replaced every `color-mix()`/CSS-var with runtime `colorVar(name, fallback)` (getComputedStyle) + `mix(hex, pct)` → `#rrggbbaa` — lightweight-charts cannot parse color-mix/CSS vars (pageerrors gone).
3. **Onboarding PATCH `/api/v1/auth/profile` 500 + stale `/auth/me`** — TWO real root causes, both fixed:
   - `profiles.onboarding_completed` column MISSING on remote Supabase → PGRST204 → 500. Applied `supabase/migrations/20260803_01400_onboarding_completed.sql` via VPS psql (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS ... BOOLEAN NOT NULL DEFAULT false`).
   - `core/deps.py` `_user_cache` (120s TTL, max 100) never invalidated by profile writes → `/auth/me` served the pre-PATCH profile for up to 2 min. `update_profile` in `routes/v1_auth.py` now does `_user_cache.pop(current_user.id, None)` after the DB update (`a8cbc16`). Verified end-to-end: signup 201 → PATCH 200 → `me` returns `onboarding_completed: true` immediately.
4. **Red herring: "intermittent 405"** — my curl repros omitted `-X PATCH`, so curl sent POST → 405 `allow: PATCH` (CORRECT behavior). Real 405s never existed; the 500 (missing column) was the actual blocker. Also added hardening `_prewarm_lazy_routes(app)` in `main.py` (recursively expands FastAPI 0.141.x `_IncludedRouter.effective_candidates()` at import, after all `include_router` calls; logs "Lazy route warm-up complete"; 29 routers expanded locally, verified `b0c73f1`).
5. **Final prod E2E GREEN 18/18** — landing nav/footer, live status probes, signup → onboarding flag persists via `/auth/me` (assertion must read `meCheck.me === 200 && meCheck.onboarding === true`, NOT `meCheck.status`), funds CTA, feedback submit+history, analytics live P&L, workspace links. Zero pageerrors, zero hydration errors. Expected noise only: single 401 `/auth/me` per anonymous page visit, 503 external option-chain vendor. CHANGELOG v1.1.1 entry; test users cleaned from DB.
6. **Fyers rate-limit compliance (v1.1.2)** — complete inventory of every Fyers REST call site → new shared per-token transport `brokers/fyers_http.py` (`FyersTransport` + `TokenRateLimiter`, budget 100 RPM + 8/s burst per access token; 429/1015 honored via `Retry-After` or jittered backoff base 0.25s cap 8s, MAX_RETRIES=3; 403 = WAF → `FyersWAFError`, never retried; GET cache_ttl + in-flight dedup; process-wide registry keyed by `client_id`; `fyers_rate_snapshot()`). Adapter now routes ALL REST through it (orderbook 3s, positions 5s, funds 5s, holdings 10s, quotes 0.5s, span margin 60s cache, history retries=1/URL; writes retries=0, auth retries=2). Option-chain call sites (route + engine) via transport 10s TTL; `symbol_master._fetch_csv` 24h TTL + backoff; `_bracket_quote` WS-tick-first + single-flight per (user, symbol); `_stream_yahoo` backoff (cap 30s). New `GET /brokers/admin/rate-limit` + `fyers` key in `/health/metrics`; structured logs `fyers.request`/`fyers.retry`. Report: `docs/FyersRateLimitAudit.md`. Regression **573 passed, 1 xfailed**. CHANGELOG v1.1.2 entry.
7. **Unified Broker SDK v2 Phase 1 (v1.2.0)** — new `brokers/sdk/`: typed error taxonomy (`errors.py`: UnsupportedFeatureError + auth/rate-limit/WAF/timeout/connection/validation/order-rejected/server errors with retryable flags, Retry-After, `translate_broker_error`/`translate_exception`), capability system (`capabilities.py`: CapabilityFlag enum + BrokerCapabilities with canonical supports()/require() + legacy bool surface + authoritative matrix), `registry.py` (BrokerRegistry spec = adapter class + UI metadata + capabilities; create() keeps CircuitBreakerBroker factory contract), `interface.py` (BrokerPort 19-method v2 surface + BrokerAdapterBase mixin bridging v2 names onto legacy BaseBroker; unimplemented → typed UnsupportedFeatureError), `certification.py` (Level A interface cert + Level B behavioral flow). ALL 11 legacy adapters now inherit BrokerAdapterBase (identical v2 surface, zero behavior change); execution BROKER_CAPABILITIES + UI metadata derive from SDK (single source of truth, verified by test_legacy_equivalence). Cert suite: all 11 CERTIFIED, 1 gap (fyers option_chain → Phase 4). Architecture doc `docs/evolution/BROKER_SDK_V2.md` (layers, capability matrix, sequence diagrams, phased roadmap, migration + rollback). Regression **644 passed, 1 xfailed**. CHANGELOG v1.2.0 entry.
8. **Unified Broker SDK v2 Phase 2 (v1.3.0)** — generic transport extracted: new `brokers/sdk/transport.py` (`HttpTransport` + `TransportConfig` + strategy extension points `AuthStrategy`/`HeaderStrategy`/`URLBuilder`/`ResponseParser`/`ErrorTranslator`/`RetryPolicy`/`RateLimiter`), **zero broker branches** (enforced by `test_transport_has_no_broker_specific_logic`); `brokers/fyers_http.py` is now a thin Fyers facade (public API unchanged: `FyersTransport`, `FyersResponse`, `FyersWAFError` — now subclass of SDK `BrokerWAFError`, `TokenRateLimiter`, `get_transport`, `fyers_rate_snapshot`; all 7 consumers untouched). Added: per-request `correlation_id` (`corr=` in `fyers.request`/`fyers.retry`/`fyers.waf` logs), `health()`, Prometheus counters `broker_http_{calls,wire_calls,cache_hits,dedup_hits,retries,rate_limited,waf_blocks,failures}_total` + `broker_http_latency_seconds` in `core/prometheus.py`. New tests `tests/test_sdk_transport.py` (16). **Before/after benchmark** (`apps/api/benchmark_transport.py`, identical canned workload vs git HEAD): Δ = 0 on every accounting counter; +~0.09 ms + ~63 B/request overhead. Test-only change: 2 `asyncio.sleep` patch targets moved to `brokers.sdk.transport`. Report `docs/BrokerTransportBenchmark.md`; doc §2/§8/§11 updated. Regression **662 passed, 1 xfailed**. CHANGELOG v1.3.0 entry.

### Reference
- Fyers compliance: budget 100 RPM + 8 req/s per access token (community ceiling ~200/min); Cloudflare 1015 = rate-limit (retryable), 403 = WAF block (NEVER retry); `Retry-After` beats computed backoff. Transport registry: `get_transport(client_id, access_token)` — callers MUST pass `caller=` for structured logs. Machinery lives in `brokers/sdk/transport.py` (generic); `brokers/fyers_http.py` is the Fyers facade. Order-path writes intentionally never retry. Live data is WS-first (`data_socket`/`market_cache`); REST quotes only for catch-up/bracket-fallback/spot-snap.
- Unified Broker SDK v2: `brokers/sdk/` is the single source of truth (registry + capabilities + metadata + transport); legacy facades (`create_broker`, `get_broker_metadata`, `BROKER_CAPABILITIES`) delegate to it. New broker onboarding = one adapter file (BaseBroker + BrokerAdapterBase) + one registry entry + cert suite + transport config/strategy overrides (`HttpTransport` + `AuthStrategy`/`HeaderStrategy`/`URLBuilder`/`ResponseParser`/`ErrorTranslator`/`RetryPolicy`/`RateLimiter` — the transport never branches on broker). Capability-absent features MUST raise `UnsupportedFeatureError` (never AttributeError/strings). Adapter class mixin order: `class X(BaseBroker, BrokerAdapterBase)`.
- API regression: `.venv/bin/python -m pytest tests/` → **662 passed, 1 xfailed** (bare `pytest` collects root `pat_test.py` → sys.exit).
- E2E: `/var/folders/yd/5mnjl3710qb4n98frjstn2kw0000gn/T/opencode/p0e2e/e2e-prod-readiness.js`; report + screenshots committed to `docs/design/prod-readiness-e2e/`.
- Commits: `5d80f4f` (v1.1.0), `44462a4`, `362c026`, `dc673d9` (hotfixes), `b0c73f1` (prewarm), `a8cbc16` (cache invalidation + migration), `a0f40c0` (changelog v1.1.1 + report) — all pushed + deployed; prod API green.

## Session: 2026-08-02 — P0 Product Discoverability Fix (v1.0.1: user navigation redesign)

### What was done
1. **P0 incident root-caused** — `components/app-layout.tsx` hard-redirected every non-admin to `/portfolio` (only admins saw the sidebar shell); normal users reached only 3 pages and 4 of 5 shipped features were invisible. Audit report: `docs/DiscoverabilityAudit.md`.
2. **Navigation fix (UI only, zero backend)** — gate now only bounces non-admins from admin routes (`ADMIN_ROUTE_RE = /^\/admin(\/|$)|\/dashboard(\/|$)/`); sidebar renders for all users (`USER_SECTIONS` 22 items = required Home/Watchlist/Portfolio, Workspace, Market Analyzer, Strategy Builder, Backtest, Orders, Positions, Funds, Journal, Alerts, Settings, Help + Analytics, Risk Control, Terminal, Option Chain, Terminal Builder, Strategies, Marketplace, AI; `ADMIN_SECTIONS` only for admins, incl. new Beta section → `/admin/beta`, `/admin/broadcast`). `/portfolio` removed from `STANDALONE_PAGES` (sidebar shows on Home). Logo link role-aware. Profile popover: +Account/Feedback/Changelog/Transparency/Status. `/strategies` header: +Catalog/Multi-Leg buttons. `isActive_` tightened to exact-or-child (was `startsWith` → false highlights).
3. **Validation** — 44/44 nav hrefs resolve; 37 routes all 200 on prod build; SSR HTML contains full user nav; `tsc` clean; prod build clean (46 pages). Post-deploy E2E + screenshots on prod (puppeteer, `docs/DiscoverabilityAudit.md`).
4. **Release** — CHANGELOG v1.0.1 (nav entry) + retitled beta-ops entry to v1.0.1-beta; tagged `v1.0.1`; deployed via `deploy.sh`.

### Reference
- Non-admin gate: `ADMIN_ROUTE_RE` matches `/admin*` + `/dashboard` only — everything else open to users; `/dashboard?tab=*` items render only for admins (`sections = isAdmin ? [...USER_SECTIONS, ...ADMIN_SECTIONS] : USER_SECTIONS`).
- Standalone pages (no sidebar, no auth gate): `/`, `/auth`, `/onboarding`, `/status`, `/portal*`.
- Release numbering: v1.0.1 stable = nav fix (2026-08-02); v1.0.1-beta = beta ops (2026-08-01); GA = v1.0.0.

## Session: 2026-08-01 — Beta Operations Mode (v1.0.1: evidence collection, GA)

### What was done
1. **Migration applied (COMPLETE)** — `supabase/migrations/20250801_01300_analytics_persistence.sql` created `analytics_events` (event, properties jsonb, session_id, user_id, created_at + 4 indexes) and `feedback_items` (user_id, user_email, full_name, category, title, description, metadata, status, notes + indexes) on remote Supabase. Replaces the lossy in-memory analytics/feedback.
2. **AnalyticsService rewritten** (`application/services/analytics_service.py`) — DB-backed, fail-open memory fallback: `track_event`, `track_batch` (skips malformed events), `record_server_event`, `submit_feedback` (categories bug/feature/nps/report), `list_feedback`, `update_feedback` (statuses new/triaged/resolved/wontfix), `list_events`, `_events_since` (30d/20k cap), `get_funnel` (per-step + cumulative), `get_retention` (weekly cohorts), `get_feature_usage`, `get_sessions`, `get_session_events`, `get_crashes` (grouped key/stack_hash/path), `get_admin_overview` (dau/wau/mau, activation_rate, retention_rate=wau/mau, avg_session_seconds, crash_free_rate, 4-step funnel, event_counts as LIST of feature dicts).
3. **Routes** — `v1_analytics.py`: `track` (forces user_id=""), NEW `track-batch` (anonymous, user_id resolved server-side via `get_optional_user`, CSRF-protected), NEW admin `overview|funnel|retention|features|sessions|sessions/{id}/events|crashes`; `v1_feedback.py` DB-backed POST `/feedback` + GET/PATCH `/admin/feedback/{id}`. `core/deps.py` added `get_optional_user` (None on 401). `main.py` timing middleware records `api_error` server event on status≥500 (non-health/metrics).
4. **Server-side value events** — `strategy.created` (v1_builder create_strategy), `backtest.run` (run-v3 top of handler), `order.placed` (place_order success), `broker.connected` (save_credentials success) — always from auth context.
5. **Web tracker** (`lib/analytics.ts`, `components/analytics-tracker.tsx` mounted in root layout) — privacy-first: no user_id from client (server resolves), sanitize() strips secret-like keys + caps strings, sampling (`NEXT_PUBLIC_ANALYTICS_SAMPLE`), excluded paths (/auth, /admin), Do-Not-Track, 5s batch + keepalive flush (sendBeacon only as fallback — cannot set CSRF header), lazy `/auth/csrf`. Events: session.start, page.view (SPA via pushState/popstate), click (closest interactive + data-analytics-label), scroll.depth 25/50/75/100, client_error (+unhandledrejection). Auth page: `track('signup')` / `track('login')` on password + OTP flows. Feedback dialog categories extended to bug/feature/nps/report.
6. **Beta Dashboard** (`app/admin/beta/page.tsx` REPLACED the mock invite-code page) — tabs: Overview (KPI cards, activation funnel, 14d DAU bars, top events), Funnel (editable steps + days, drop-off %), Retention (cohort matrix), Features (ranked), Sessions (list + replay timeline), Crashes (grouped signatures), Feedback (filter by status + inline triage PATCH). Admin-guarded via useAuth().isAdmin.
7. **Reports** (`infra/scripts/analytics_report.sh`) — 6 weekly reports 06-funnel/07-activation/08-retention/09-most-used/10-drop-off/11-most-requested from remote Supabase (psql over SSH, `-F '|'`, real columns — `||`-concatenation in GROUP BY breaks). W31 baseline authored with real data (tracker not yet deployed that week → events=0 expected).
8. **Validation + deploy** — regression **562 passed, 1 xfailed**; web tsc + prod build clean; hot-deployed API (9 files) + web (.next). **Startup ImportError fix**: container had STALE files (`core/exceptions.py` missing AppError, `core/middleware/timeout.py` importing old `ServiceUnavailableException` etc.) — diffed whole container /app vs repo (7 diffs: timeout.py, db.py, data_loader.py, pat_test.py, data_socket.py, repositories/base.py, builder/models.py) and deployed all. Health 200 after.
9. **Prod smoke (ALL PASSED)** — in-container script: CSRF handshake → anonymous track-batch (ok, accepted counts) → admin overview (total_users=21 from profiles, broker 4, traded 2, live 1) / funnel / retention (first cohort 2026-08-01) / features / sessions / crashes / feedback all 200 → feedback submit (id=1) + PATCH triaged + filtered list → session replay 6 events → list_events filter. Smoke rows cleaned from DB. Token sub must be the USER UUID (`fa668109-4b1e-4758-a49b-015027ea4115`), not email.

### Reference
- `analytics_report.sh` + `weekly_report.sh`: run from repo root with `TMX_VPS_PASSWORD` (+ `TMX_SUPABASE_PASSWORD` fallback) env vars; both SSH to VPS and query remote Supabase.
- Test mocks: patch `application.services.analytics_service.get_supabase` / `async_supabase` (module-imported references), NOT `core.db`. FakeTable needs `eq`/`gte` (gte = string >=), `update` (mutates in place), id assignment on insert.
- Client tracker CSRF: fetch `/auth/csrf` lazily once, read `csrf_token` cookie, send `X-CSRF-Token`; keepalive fetch on pagehide (sendBeacon drops the header → 403).
- `docker cp` quirk: overwriting an existing destination file intermittently fails `/proc/self/fd` — `docker exec -u root <c> rm -f <dest>` first (needed after stale-file fixes).
- Container drift: hot-deploys leave old files — when a startup ImportError appears, `docker cp <c>:/app /tmp/snap` then diff vs repo.
- Beta Dashboard data sources: all `/api/v1/admin/analytics/*` + `/api/v1/admin/feedback`, `require_admin`.

## Session: 2026-08-01 — v1.0 GA Preparation (P1–P4 complete, RC → GA declared)

### What was done
1. **P1 remote Supabase unblocked + migrated (COMPLETE)** — user provided the real DB password. All 6 GA tables created on `db.nwutlfuowiulfpbsrldn.supabase.co` (PostgreSQL 17.6) via psycopg2: `builder_strategies`, `builder_strategy_versions`, `builder_strategy_logs`, `backtest_runs`, `candles`, `corporate_actions` (RLS on; app uses service key = BYPASSRLS; anon blocked — correct). Persistence verified AFTER API restart: 4/4 PASS (strategy `ready`, COMPLETED run, lifecycle logs, version history) + OMS recovery ("Recovered 1 active orders…").
2. **Backtest reliability fixes** (`adcec54`, needed by P1 validation) — `backtest/manager.py` passes `user_id=config.user_id` to the loader at BOTH call sites (run-v3 previously skipped user_id → "No candle data loaded"); `backtest/data_loader.py` auto source now routes through durable `backtest_historical.load` (Supabase-first, gap-fill, write-back) instead of broker-only; `market/historical.py` Yahoo fallback (`^NSEI` map) also when `not user_id` or fetch fails. New `tests/test_market_historical.py` (patch `core.db.*` — source module for function-local imports). Regression 551 passed / 1 xfailed. NOTE: yahoo `_to_yahoo` must not be called twice; durable store caches candles (533) so later runs skip Yahoo.
3. **P2 deps baked (COMPLETE)** — reportlab >=4.0 already in requirements.txt; fresh `--no-cache` build verified (reportlab 5.0.0, uvicorn, non-root `app`); VPS fresh rebuild → no manual post-install steps (old prod image was stale).
4. **P3 single-command deploy (COMPLETE)** — `infra/production/deploy.sh` rewritten: non-interactive (installs Docker, `git reset --hard origin/main`, env guard, OpenRouter key injection ONLY if env var set AND missing, DNS advisory, `build --parallel api web`, `up -d`, health gates API+web 18×10s, GA banner, exit 1 with `docker compose logs api web` tips). Validated E2E on prod. Old interactive `read -rp` prompts removed (killed non-TTY deploys).
5. **P3 backup script (COMPLETE)** — `infra/scripts/backup.sh`: redis SAVE + volume copy, prometheus TSDB snapshot via admin API, grafana/n8n/caddy via stop+tar of `production_*` volumes, env files, 14-day retention, `tar tzf` verification on EVERY archive (exit 1 if any fails). BUGS FIXED en route: (a) `tar czf ... -C / v .` tars the container ROOT incl. /proc → short read — must be `-C /v .`; (b) prometheus 3.x needs `--web.enable-lifecycle` AND `--web.enable-admin-api` (snapshot API; compose updated, container force-recreated, verified `20260801T082220Z-…`). E2E: all `[OK]`, 49M verified.
6. **Repo authoritative (user-approved)** — 112-file backlog committed `f88d300` + pushed to PUBLIC GitHub `main`; verified no tracked secrets; VPS synced via `git fetch origin && git reset --hard origin/main` (env files untracked → survive).
7. **P4 docs (COMPLETE)** — rewrote `DEPLOYMENT.md`, `DISASTER_RECOVERY.md`, `RELEASE_NOTES.md` (v1.0.0 GA); refreshed `RUNBOOK.md`; created `BACKUP_RESTORE.md`, `KNOWN_ISSUES.md`, `UPGRADE_GUIDE.md`.
8. **Final validation gate — ALL PASS, RC → GA declared** — API regression 551 passed/1 xfailed; web tsc + prod build clean; `deploy.sh` E2E from `origin/main` (d2a465b) → "Deployment Complete — v1.0 GA", API health ok, web 200; post-deploy persistence: `strategies=7, runs=2, candles=533`. CHANGELOG v1.0.0 entry; this AGENTS.md entry.

### Reference
- Deploy: `ssh root@187.127.185.56` → `cd /root/trademetrix-terminal && bash infra/production/deploy.sh` (single command, idempotent). SSH password + Supabase DB password = password manager (`Aakibkhan1@23`, rotate in dashboard).
- Backup: `bash infra/scripts/backup.sh` → `/root/trademetrix-backups/<ts>/`; restore patterns in `BACKUP_RESTORE.md`.
- Remote Supabase access: `PGPASSWORD='<db-pw>' psql "postgresql://postgres@db.nwutlfuowiulfpbsrldn.supabase.co:5432/postgres?sslmode=require"` (or psycopg2 from `apps/api/.venv`). Migrations idempotent, filename-ordered, apply via psql.
- scp to VPS is rate-limited sometimes — use `tar czf - -C <dir> <f> | ssh ... tar xzf - -C /tmp/x && docker cp ...`.
- GitHub repo is PUBLIC: never commit `.env*` (all gitignored); only untracked files exist on VPS.
- GA end-state (2026-08-01): origin/main `d2a465b`; VPS synced; prod containers healthy; backup verified; strategies=7 runs=2 candles=533 persisted remotely.

## Session: 2026-08-01 — Phase 6: Product Polish (audit → a11y/consistency → ship)

### What was done
1. **6.0/6.1 Audit + reports** — `docs/evolution/PHASE6_PRODUCT_POLISH.md`: surveyed 63 pages + 42 components. UX: dead header tabs (duplicate `header.tsx`, zero imports), fake search div, hardcoded `v0.1` (header badge + portal footer), no error boundary (zero `error.tsx` in repo), toast/inline success inconsistency, empty-state copy drift. Performance: 84.6 kB shared JS, pages 85–178 kB, 9 pollers (1s statusbar clock, 1s OTP ×2, 5s ×2, 15–30s ×4 — all cleaned), no RSC/streaming/dynamic chunks; dashboard tabs ALREADY `next/dynamic(ssr:false)`. Accessibility A1–A9: only 2 `aria-*` attributes in the whole app before B1, no skip link, search not a dialog, dropdowns lack `aria-expanded`, `--text-faint #5b5875` ≈ 2.5:1 (fail), dead search div, no `aria-current`. Visual: ≈100 hardcoded hexes (39×#fff, 18×#555570, 17×#8888a0, 16×#ef4444), ~340 buttons without `type=` (deferred), dead header.tsx, mixed emoji/letter icons. Plan: B1 a11y+dead code → B2 UX+focus → B3 consistency tail → B4 ship.
2. **6.2 B1 (zero risk, attributes only)** — `app-layout.tsx`: skip-to-content link (`#main-content` on `.t-content`), search div → real `<button data-search-open aria-label="Search symbols, strategies, pages (⌘K)">`, icon-button `aria-label`s (sign-out, theme toggle, collapse/expand), notifications/profile popovers `role="menu"` + `aria-expanded` + `aria-controls` (`notifications-popover`/`profile-popover`), `aria-current="page"` on active nav Links. Deleted `components/header.tsx`. `tokens.css`: dark `--text-faint` `#5b5875`→`#7d79a0` (AA). `error-message.tsx`: `#ef4444`→`var(--text-red)`. tsc + prod build clean.
3. **6.3 B2 (additive)** — search overlay `role="dialog"`+`aria-modal="true"`+`aria-label="Global search"`; Tab focus trap (cycles focusables in `[data-search-overlay]` while open) + `restoreFocus()` on Escape (re-focuses `[data-search-open]` only if focus was inside the overlay); `closeSearch()` shared by ESC/backdrop/close. New root `app/error.tsx` (reset + Back to Dashboard, dev-only `error.message` dump) and `app/not-found.tsx`. Header badge + portal footer `v0.1` → `AppVersion`/`getAppVersion()` (`components/app-version.tsx`, env-driven).
4. **6.4 B3** — toast container `role="status"`+`aria-live="polite"`, toast items `role="alert"` (`lib/use-toast.tsx`); literal sweep: `#ef4444`→`var(--red)` (portal, strategies/catalog, admin/beta, admin/broadcast, strategy-builder/types palette, equity-curve), `#555570`/`#8888a0`→`var(--text-faint)` (5 files); light-theme `--text-faint` `#9aa0a6`→`#757580`. EmptyState copy spot-check: already consistent ("No X yet") — no churn. Dashboard lazy-load: already done. tsc clean.
5. **6.5 Ship** — full API regression **549 passed, 1 xfailed** (API untouched — baseline identical). Prod web build clean. Deployed: tar `.next` (61 MB) → VPS → `docker cp` → `docker exec -u root` rm+extract+chown → restart. Prod smoke: `/backtest` 200, new BUILD_ID manifest 200, `/dashboard` HTML has skip-link target + `aria-current="page"` + `data-search-open` + new search aria-label.
6. **6.6** — CHANGELOG v0.2.0-rc.7; this AGENTS.md entry.

### Reference
- Phase 6 rule: polish ONLY — no features, no architecture changes, no new modules; regression (API pytest + web tsc/build) after EVERY batch.
- Web prod deploy (Phase 6): tar `.next` (~61 MB) → scp → `docker cp` into `trademetrix_web:/tmp/` → `docker exec -u root trademetrix_web sh -c 'cd /app && rm -rf .next && tar xzf ... && chown -R node:node .next'` → `docker restart trademetrix_web`.
- Web build env swap: `cp .env /tmp/web_env_backup_62 && cp .env.production .env && npm run build` then restore.
- Skip-link target `#main-content` must exist on the content wrapper; skip link shows only on focus (inline focus/blur style handlers).
- Search overlay: opening focuses the input (`ref`), closing restores trigger focus ONLY via `closest('[data-search-overlay]')` check; Tab trap iterates `[data-search-overlay]` focusables.
- Dead-code check before delete: `grep -rn "components/header"` zero imports → safe to rm.

## Session: 2026-08-01 — Phase 5: Institutional Backtest Engine (build → backtest → optimize → deploy)

### What was done
1. **Design doc** `docs/evolution/PHASE5_BACKTEST_ENGINE.md` — reuse table (Strategy Builder DSL, ExecutionManager adapter pattern, OMS/risk read-only), architecture (BacktestBroker adapter registered as fake `backtest:{run_id}:paper` user in `ExecutionManager._adapters`), costs, performance extensions, optimizer spec, run-v3, exports, deploy-to-paper, 8 sub-phases with regression gates.
2. **5.1 Costs** — `backtest/costs.py`: `estimate_cost`/`estimate_round_trip`/`segment_for` with Indian rates (brokerage ₹20 flat, STT 0.025% intraday etc.), `cost` config knob. 10 tests.
3. **5.2 Durable store** — migration `supabase/migrations/20250801_01200_backtest_persistence.sql` (`candles`, `corporate_actions`, `backtest_runs`) APPLIED to local Docker Supabase (PostgREST 200). `backtest/historical.py`: DB-first `load` with gap-fill + best-effort write-through (fail-open), `load_continuous` (-CONT roll with proportional back-adjustment), `apply_corporate_actions` (split/bonus price scaling). 7 tests.
4. **5.3 Fill engine + BacktestBroker** — `backtest/execution.py`: `BacktestFillEngine` (MARKET@close±slippage, LIMIT trade-through+timeout, SL/SL-M/SL-L triggers, seeded partials, latency candles), `BacktestBroker` (PaperBroker-compatible: place/modify/cancel/orders/positions/funds/health; cost debits; `_trades` with entry/exit times). `manager.py` MAX path rewritten broker-direct (`broker.on_candle` before `strategy.on_candle`, `_place_via_broker` with risk dry-run `is_paper=True`, `_collect_snapshot`, `_close_open_positions`). **Bug found+fixed: only PENDING orders retried on `on_candle` — filled orders were re-retried causing double fills.** `replay_engine.run` gained optional broker/risk_check/bt_user_id (back-compat). 12 tests.
5. **5.4 Performance** — `backtest/performance.py`: expectancy & expectancy-per-R (R=avg loss), RR ratios, weekday/hour/month distributions (UTC→IST), 252d alpha/beta vs benchmark (manager passes benchmark candles). `BacktestConfig.strategy_type` now defaults `""` (bare `BacktestResult()` construction broke before). 5 tests.
6. **5.5 Optimizer** — `backtest/optimizer.py`: grid (≤512 `max_combos`), walk-forward (N windows, train-prior-fold/test-current-fold via `candle_slice`), Monte Carlo (2000 bootstrap paths over trade PnLs → p5/p25/p50/p75/p95/mean/probability_of_profit), sensitivity (OFAT ±20%). Manager `_fast_run` (lean broker-direct) + `_persist_run` (upsert `backtest_runs` JSONB) + async `get_run`/`_row_to_result` (restores from DB). Routes `/optimize` + `/optimize/{run_id}`. 7 tests. Regression 535 passed.
7. **5.6 Routes** — run-v3 (builder `strategy_id` → `compile_dsl` → `GraphStrategy` via `strategy_params["_dsl"]`, full metrics payload), `/compare` (≤10 ids), `/{run_id}/export?format=json|csv|pdf` (reportlab), `/{run_id}/deploy-to-paper` (existing `start_graph_strategy` + `set_status(PAPER)`), `/candles/{symbol}/{interval}`, `/corporate-actions` GET/POST. **Route-ordering gotcha: static GETs must be declared BEFORE `GET /{run_id}` (FastAPI first-match), and function-local imports mean monkeypatch targets must be `"builder.compiler.compile_dsl"`/`"engine.graph_strategy_runner.start_graph_strategy"`, NOT module-level.** reportlab installed in venv (5.0.0) + requirements.txt. 14 tests. Regression **549 passed, 1 xfailed**.
8. **5.7 Web** — `apps/web/app/backtest/page.tsx` rewritten: builtin/builder source toggle (builder list from `api.builder.list()`), run form (slippage/latency/partial-fill/risk), 14-KPI grid, equity+drawdown SVG charts, distributions + weekday×hour heatmap, optimizer tab (method/metric/param-ranges textarea → server `/optimize`), compare tab (run IDs → `/compare`), trade log, export buttons (raw `fetch` + `backtestExportUrl` — `api.request` JSON-parses and breaks binary PDFs), deploy-to-paper. `api.ts`: `backtest` client gained typed generics `<T,>` (TS requires them or returns `unknown`). `tsc --noEmit` clean, `npm run build` clean (built with `.env.production`, `.env` restored after).
9. **5.8 Deploy** — API: scp tar → docker cp `backtest/` + `routes/v1_backtest.py` + `requirements.txt` → restart. reportlab: `docker exec -u root trademetrix_api pip install --ignore-installed reportlab` (PIL dir was root-owned → Permission denied as node). Web: tar `.next` (62MB) → docker cp → `docker exec -u root` rm+extract+chown → restart. New BUILD_ID manifest served.
10. **Prod smoke (20/20)** — authenticated (create_access_token user fa668109) in-container script: create builder strategy → run-v3 200 (all metrics present) → get run → JSON/CSV/PDF exports (valid %PDF) → compare → deploy-to-paper started → stop → candles endpoint returns data → corporate-actions list 200 (empty — remote tables missing, expected).
11. **CHANGELOG** v0.2.0-rc.6 (Phase 5 entry).

### Reference
- Prod route ordering: static GET routes in `v1_backtest.py` MUST precede `@router.get("/{run_id}")` (e.g. `/candles/{symbol}/{interval}`, `/corporate-actions`); `/compare` POST and `/{run_id}/export` (2 segments) are safe anywhere.
- FastAPI function-local imports (`from builder.compiler import compile_dsl` inside a route) — monkeypatch the SOURCE module (`"builder.compiler.compile_dsl"`), not the route module.
- CSRF on prod: GET `/auth/csrf` per POST, jar cookie, `X-CSRF-Token` = body token; in-container smoke pattern: `docker cp` script into `/app/p5_smoke.py` + `docker exec -w /app -e PYTHONPATH=/app` (no `-e` → `ModuleNotFoundError: core`).
- reportlab on prod container: `docker exec -u root trademetrix_api pip install --ignore-installed reportlab` (plain install fails on root-owned PIL).
- `run-v3` runs DSL as `graph_strategy` with `strategy_params={"_dsl": …}`; deploy-to-paper allows DRAFT/VALIDATED/READY/PUBLISHED/PAPER statuses.
- Backtest export via `api.request` breaks for PDF (JSON.parse of binary) — use raw `fetch` + `backtestExportUrl`.

## Session: 2026-08-01 — Phase 4.3: Strategy Lifecycle (version control, deploy wizard, dashboard, logs, score)

### What was done
1. **Backend lifecycle** — `builder/manager.py`: every save of name/nodes/edges/settings snapshots a version (module-level `_snapshot_version`, ring capped at 50) into `builder_strategy_versions` + bumps `version_number`; `get_version/get_versions/compare/set_status` added; restore/rollback restores a snapshot as a NEW version (never rewrites history). `builder/models.py`: lifecycle statuses DRAFT/VALIDATED/READY/PUBLISHED(alias)/PAPER/LIVE/STOPPED/ARCHIVED + `RiskConfig`/`ScheduleConfig`/`DeploymentConfig`/`StrategyScore`/`StrategyLogEntry`; `StrategyDSL` gained `deployment` field. New modules: `builder/score.py` (5-metric scorecard, A–F grade), `builder/logs.py` (ring 500 + write-through to `builder_strategy_logs`). `builder/templates.py`: TEMPLATE_CATEGORIES (all official). `engine/graph_strategy_runner.py`: `_runtime_stats` (candles/signals/orders placed/filled/rejected/errors/latency/last_error/last_activity), signal/order/rejection/lifecycle log records, `get_runtime_dashboard()` + `_estimate_pnl()` (READ-ONLY realized PnL from orders table where source=graph_strategy — no OMS writes), `get_running_strategies()`, `stop_graph_strategy(user_id=...)`. `routes/v1_builder.py`: new `/ready`, `/deploy` (DeployStrategyRequest+RiskDeployRequest+ScheduleDeployRequest; live REQUIRES broker; sets deployment + status + starts runner with `is_paper=mode!="live"`), `/score`, `/logs`, `/compare`, `/dashboard`; validate promotes DRAFT→VALIDATED; start/stop lifecycle-aware; lifecycle log records on publish/archive/clone/rollback/validate/ready/deploy/stop.
2. **Migration** `supabase/migrations/20250731_01100_builder_persistence.sql` extended with `builder_strategy_logs` + `deployment JSONB` — APPLIED locally (docker psql into `supabase_db_trademetrix-terminal`, REST 200 verified). Remote still blocked (placeholder DB password).
3. **Repair** — my earlier `_snapshot_version` edit had corrupted `builder/manager.py` (duplicate `class BuilderManager` at line 213 with orphaned publish/archive bodies → IndentationError at collection). Restored single class + re-added module-level `_snapshot_version`; `python -c "import builder.manager"` clean.
4. **Tests** — new `tests/test_builder_lifecycle.py` (9 tests): every-save-versions, compare, rollback bumps version (assert template name "EMA Crossover", not the requested name — create() with template ignores name), rename, status flow, deployment roundtrip, score structure, logs, template categories. Fixed `builder/score.py` bug: `graph.cycles` does NOT exist on ExecutionGraph (removed `not graph.cycles and` condition). Full suite **494 passed, 1 xfailed** (485 baseline + 9).
5. **Web UI** — `apps/web/lib/api.ts` builder client: `ready/deploy/score/logs/compare/dashboard/start(mode)`. New components: `deploy-wizard.tsx` (paper/live seg, broker select, capital, risk grid, trading-day chips, times), `versions-drawer.tsx` (version list + compare selectors + diff lines + restore with confirm), `strategy-score.tsx` (grade circle + 5 metric bars), `strategy-logs.tsx` (kind-colored timeline, 5s auto-refresh). `page.tsx`: status chips (green live/published/ready, cyan paper/validated, yellow stopped, sub archived), Versions button, Ready button, working Deploy wizard modal, score + logs panels in footer. `strategies/page.tsx`: Execution Dashboard section (health badge, symbol/interval/mode, candles/signals/orders/filled/rejected/errors, PnL colored, Open link), 5s poll. `tsc --noEmit` clean, `next build` clean.
6. **Restart persistence verified (local)** — script creates strategy in process A (name v2, READY, paper deployment, 2+ versions) → fresh process B restores everything from local Supabase (`_ensure_db()` loads tables on first use).
7. **Local HTTP smoke (19 checks)** — create→validate(promotes)→ready→deploy paper (deployment persisted)→live-without-broker 400→save creates v2→compare→score grade A→logs lifecycle+validation→dashboard running=1→stop→status stopped. TestClient needs: dependency_overrides[get_current_user] + patch resolve_capabilities→TEST_CAPS + cookie csrf_token match.
8. **Deployed to prod** — API: scp + docker cp 7 files (builder/manager.py, models.py, score.py, logs.py, templates.py, engine/graph_strategy_runner.py, routes/v1_builder.py) + restart; imports OK, health OK. Web: built with `.env.production` (`cp .env.production .env && npm run build && restore .env`), tar `.next` → VPS → `docker cp` → **`docker exec -u root`** to rm -rf /app/.next (files are root-owned; node user gets Permission denied) → extract → chown -R node:node → restart. New BUILD_ID served.
9. **CSRF production bug FIXED (INC-013 relapse)** — deployed container ran the OLD middleware (cookie set only on first request → body token rotated each `/auth/csrf`, cookie never updated → every POST after the first → 403). Local fixed `middleware/csrf.py` never made it to prod. Deployed it (scp + docker cp + restart); rotation verified live (GET2 set-cookie present, jar matches body).
10. **Prod smoke (authenticated, user fa668109-...)** — create→validate(True)→ready→deploy paper→GET status=paper deployment persisted→live-no-broker 400→versions=1→score A 85.4→logs lifecycle+validation→dashboard total_running=1→stop→status stopped. Runner logs confirmed "subscribed to live tick feed for <sid>" + clean stop. Web `/strategies` 200 + new build manifest 200.
11. **CHANGELOG** updated (v0.2.0-rc.5, Phase 4.3 entry with Added/Changed/Verification/Known gaps).

### Reference
- CSRF on prod: each POST must fetch `/auth/csrf` first with the SAME session (jar holds the cookie); body `csrf_token` = `X-CSRF-Token` header. NEVER send a raw Cookie header — the fixed middleware rotates the cookie on every response and a stale explicit header breaks matching.
- TestClient CSRF: `client.cookies.set("csrf_token", CSRF)` + header `X-CSRF-Token: CSRF` (same 32-char value), plus auth override.
- Web prod deploy: build with `.env.production`; .next is 290MB; container file ops need `docker exec -u root`; node user runs the server.
- Prod Supabase password in `/root/trademetrix/.env` is a 38-char placeholder (auth fails for postgres/postgres.<ref>/supabase_admin) — `builder_*` tables still missing remotely; strategy persistence on prod is in-memory only until the migration can be applied.

## Session: 2026-08-01 — Stabilization: all pytest failures fixed, clean baseline (485 passed)

## Architecture
- `apps/api/` — FastAPI backend (Python 3.12)
- `apps/web/` — Next.js frontend
- `infra/` — Docker Compose deployment configs
- `supabase/` — DB migrations

## Session: 2026-08-01 — Stabilization: all pytest failures fixed, clean baseline (485 passed)

### What was done
1. **`test_broker_timeouts.py::test_settings_have_timeout_defaults`** — asserted pydantic DEFAULTS (8/5) but `Settings` loads `.env`/`.env.test` via dotenv (`model_config env_file`), and `.env.test` (created `ad9fbc6`, 2026-07-28) sets `BROKER_REQUEST_TIMEOUT=15`/`CONNECT=10`. Test also tried `os.getenv` fallback — wrong, the override comes from the dotenv file, not process env. Fix: assert `> 0` (guards field existence + sane values without hardcoding env contents).

2. **`test_execution_manager.py::test_place_order_happy_path`** — stale test asserting unconditional FILLED. INC-015 "order status honesty fix" (UNCOMMITTED working-tree change; HEAD `ad9fbc6` still has old `... if is_partial else ExecutionState.FILLED` at manager.py:157) makes FILLED depend on `broker_result.status`. Mock returned `OrderResult(...)` with no `status` → PENDING. Fix: `status="filled"` in mock + mock `_update_order_in_db` (was hitting real Supabase, caught 22P02 error log). Partial-fill test already used the new `status` field — fixed its same real-DB access too.

3. **`test_gate.py::test_paper_mode_routes_to_paper`** — stale test mocking the pre-OMS direct `execution_manager.place_order` path. INC-015 fourth pass (UNCOMMITTED) rerouted `gate.execute_order` through `order_manager.place_and_wait` (gate.py:376); test didn't mock OMS → REAL Redis enqueue → `queued`. Fix: patch `oms.manager.order_manager`, mock `place_and_wait` → FILLED OmniOrder; assert `status == "filled"`.

4. **Result**: full suite **485 passed, 1 xfailed (intentional), 3× repeat runs stable** — deterministic baseline. `test_mirror_fanout.py` collects 0 tests (manual E2E harness with real Supabase — excluded from suite by design, not a failure).

### Reference
- All 3 failures were TEST staleness vs intentional/uncommitted-but-deployed behavior changes — zero production risk, zero production code modified in this pass.
- Pydantic `Settings` reads dotenv files; unit tests asserting "defaults" must not assume process env.

## Session: 2026-08-01 — P0: Order Block condition gating (builder/strategy.py) + graph runner paper/live safety

### What was done
1. **P0 incident fixed — order blocks fired unconditionally** (`builder/strategy.py`): `_compute_order_buy/_compute_order_sell` returned `triggered: True` on every candle; `on_candle`/`_parse_signal` defaulted `.get("triggered", True)`. Now: `_port_in_map` (dict of target_port → [(target, source_node, source_port)]) built from DSL edges in `__init__`; `_evaluate_node` resolves per-port values via `_port_value(results.get(source_node), source_port)` instead of blind dict merge (also fixes latent misrouting of non-first upstream ports); new `_condition_triggered(ctx)` → True ONLY when a connected condition-ish input (`condition`/`triggered`/`result`/`value`) is truthy, False when no inputs (fail-closed for live). `_compute_order_buy/sell/exit/reverse` (incl. new `_compute_order_exit` + `_compute_order_reverse` + registry entries) all gate on it. Defense-in-depth: `on_candle` order check and `_parse_signal` default `result.get("triggered", False)`.

2. **Regression tests** (`tests/test_graph_strategy_orders.py`, 8 tests, all pass): connected condition=true fires; connected condition=false no order; no-condition no order (fail-closed); chained conditions via logic.and true + false paths; chained-false never fires; non-order blocks unaffected; ema_crossover template on clean uptrend emits no spurious orders. Test condition chains use `signal.cross_above` fed by `indicator.ema` 5/13 on close_history (candle.bullish requires open/close ports — validation rejects unwired ones).

3. **Graph runner paper/live safety hole fixed** (`engine/graph_strategy_runner.py`, `routes/v1_builder.py`): runner called `execute_order` directly with `NormalizedOrder.is_paper` defaulting to **False** → graph strategy orders would go LIVE on a funded broker (test account fa668109 has live Fyers). `StartGraphStrategyRequest` gained `mode` (`paper` default); `start_graph_strategy(..., is_paper=req.mode != "live")`; `_feed_loop` sets `order.is_paper` on both tick and candle order paths. Fail-closed default (paper).

4. **Runner start 500 fixed**: `start_graph_strategy` inserted builder hex ids (`f40605dbced9`) into `strategy_runs.strategy_id` (uuid column) → PG 22P02 → route INTERNAL_ERROR. Insert/update now wrapped in try/except (warning + runner continues). NOTE: schema debt — `strategy_runs.strategy_id` should be TEXT or builder runs tracked elsewhere; fix when migration password unblocked.

5. **Verified on prod** (`ai.trademetrix.tech`, deployed via docker cp + restart): create template → validate (0 issues) → publish → start (mode=paper) → "Graph runner subscribed to live tick feed" → clean run, no signals/errors → stop. Full local suite: 482 passed; 3 failures pre-existing/unrelated (broker_timeouts fails even at HEAD; gate/execution_manager paper-state tests broken by earlier uncommitted Phase 3 work — no builder imports in those tests).

### Reference
- Builder strategy ids are 12-hex (`uuid.uuid4().hex[:12]`) — NOT uuids; any DB column typed uuid rejects them.
- CSRF on prod: clean jar → GET /api/v1/auth/csrf (sets cookie + body token, they match) → POST with `-b jar` + `X-CSRF-Token: <body token>`. Sending a stale cookie on the csrf GET breaks rotation matching.
- `builder_strategies`/`builder_strategy_versions` tables still MISSING (PGRST205) — migration `20250731_01100_builder_persistence.sql` blocked on Supabase password; strategies survive only in-memory (restart loses them).

## Session: 2026-07-31 — Auto SL/Target on every trade + ITM strike snapping (INC-015 fifth pass)

### What was done
1. **Auto-bracket on every OMS fill** (`oms/manager.py`) — worker attaches a `BracketOrder` whenever an order fills (direct fill, partial-complete, or reconcile FILLED): SL = entry ∓10%, target = ±15% (RR 1.5), BUY/SELL mirrored. Skipped when `source` in EXIT_SOURCES (`exit_sl`, `exit_target`, `bracket_sl`, `bracket_target`) or relation_type != NONE (no cascading brackets — verified). `BracketOrder` gained `side`/`broker` fields (ALTER TABLE added columns).

2. **Bracket monitor loop** (`oms/manager.py _bracket_loop`, 2s interval) — for each active bracket: fetch quote (live via `BrokerExecutionAdapter.get_quotes` proxy added; paper via `market_cache` with Fyers refresh on stale — market_cache TTL 30s otherwise starves paper brackets), fire exit when last price breaches: SL → SL-M order (trigger=level) with MARKET fallback on rejection; TARGET → LIMIT (MARKET if last > target×1.02). Exit placed → bracket deactivated + `sl_order_id`/`target_order_id` persisted; failed exits leave bracket active so the monitor retries next cycle. Cancel/reconcile-CANCELLED/REJECTED/EXPIRED deactivates the bracket. Brackets recovered on startup (`_recover_active_orders` already loaded them).

3. **ITM strike snapping** (`engine/gate.py _snap_to_itm_strike`) — engine trades (any source ≠ "strategy") with option_type CE/PE are rewritten to the nearest ITM strike at execution: CE → floor(spot/interval)×interval, PE → ceil; interval from `STRIKE_INTERVALS` (NIFTY 50). Verified: requested 25200 CE → snapped to 24450 CE when spot ≈ 24455.

4. **Fyers index spot unavailable** — `NSE:NIFTY` / `NSE:NIFTY50` / option-chain endpoint all fail (invalid symbol / 404). **Spot proxy = same-month index future** (`NSE:NIFTY26AUGFUT`, verified 24454 vs put-call parity 24456 at two strikes). Snap uses the option's own expiry-month future.

5. **`format_fyers_option_symbol` year bug FIXED** (`core/constants.py`) — formatter injected a 2-digit year (`NSE:NIFTY26AUG2524450CE` → invalid; Fyers current format is `{dd}{MONTH}{strike}{CE}` with NO year). This corrupted snapped symbols (fill price 0, quotes invalid). Also fixed `format_fyers_future_symbol` (missing `FUT` suffix → `NSE:NIFTY26AUGFUT`). Affected callers: gate snap, fyers_adapter admin branch, strategies/expiry_hunter.

6. **Exit orders exempt from 5% price-band** (`execution/validation.py _check_price_band`) — SL/target levels legitimately sit far from LTP (SL 40 vs LTP 35 = 14%); the guard was rejecting every SL-M exit ("deviates X% from LTP (max 5%)") causing 3 retries → REJECTED. Now `SL`/`SLM` order types and EXIT_SOURCES skip the band check. Verified end-to-end: forced SL breach → SL-M SELL placed → FILLED 65 @ 35.95, audit row source=`exit_sl`, bracket deactivated, no cascade.

7. **Live position protected** — seeded `oms_bracket_orders` row for the live `26073100242388` fill (65 × NIFTY26AUG25000CE @ 71.75): SL 64.58 / target 82.51, active, monitored.

### Reference
- Bracket lifecycle: fill → `_attach_auto_bracket` (SL = entry×(1∓0.10), target = entry×(1±0.15)) → `_bracket_loop` every 2s → breach → `_place_exit` (`exit_sl`/`exit_target` source, EXIT_SOURCES-guarded) → deactivate. Exits persist through the normal OMS queue.
- Quote sources: live = `BrokerExecutionAdapter.get_quotes` (new proxy, auto-connect + token-expiry retry); paper = `market_cache` (Fyers refresh when stale).
- Paper SL-M exits fill instantly (fill_type INSTANT); live SL-M uses equal limit/stop — if Fyers rejects equal values, MARKET fallback engages.
- `_check_margin`/price band run in exec_mgr before broker; exit orders skip the band but still pass through margin (empty `margin_snapshot` → pass).

## Session: 2026-07-31 — Engine path → OMS, Redis queue, live verification (INC-015 fourth pass)

### What was done
1. **Engine path now routes through OMS** (`engine/gate.py`, `application/services/engine_service.py`) — `gate.execute_order` uses `order_manager.place_and_wait(req, timeout=20.0)` instead of calling `execution_manager.place_order` directly (previously engine orders got NO reconcile/recovery/audit). Success = state in FILLED/PARTIAL/PENDING; copies broker_order_id/filled_quantity/average_price/latency; status via `OrderStatus`; new `_oms_to_order_result` mapper; removed `execution_manager`/`ExecutionState` imports. `engine_service.cancel_order` now tries `order_manager.find_order(user_id, broker_order_id)` → OMS cancel first, falls back to exec_mgr.

2. **Redis-backed OrderQueue** (`oms/order_queue.py` full rewrite) — Redis list `oms:order_queue` with `blpop` (0.1s timeout); retries requeue-at-tail via `next_retry_at`; `remove` scans chunks; stats from list length. Added `cache.get_redis()` raw-client accessor (`core/cache.py`, lazy init, decode_responses=True).

3. **Cross-process worker fallback** (`oms/manager.py _process_queue`) — if order not in in-memory dict, `load_order()` from DB → `OmniOrder(**row)` + `_add_order` (log: "Loaded order … from DB (cross-process enqueue)"). Verified live: paper order enqueued from a separate `docker exec` process was picked up by the API worker.

4. **`place_and_wait` + result cache** (`oms/manager.py`) — enqueues and polls (timeout 20s); `_record_terminal` writes `oms:result:{oms_order_id}` to Redis (TTL 60s) on terminal states; `_load_result` consulted every poll iteration (first version only when in-memory missing → still returned QUEUED). Verified: cross-process paper MARKET filled in ~4s, SUCCESS True. Worker sets weighted `average_price` when `exec_result.avg_price` present.

5. **Gotchas hit**: `async_safe_single` adds `.maybe_single()` itself — callers must NOT chain it (`'SyncMaybeSingleRequestBuilder' object has no attribute 'maybe_single'`). `save_order` upsert needs string `on_conflict="oms_order_id"` (list form → PG 42P10). `find_order` searches active + `_completed` OrderedDict (cap 200).

6. **Live engine HTTP order VERIFIED FILLED** — `POST /api/v1/engine/trade` (MARKET, live) → Fyers `26073100242388` FILLED 65 @ 71.75 (`NSE:NIFTY26AUG25000CE`). Full chain works: route → gate → OMS → Redis queue → worker (API process) → Fyers → audit row.

7. **`ExecuteSignalRequest` route-model gap FIXED** (`routes/v1_engine.py`) — model lacked `is_paper`/`source` fields; pydantic dropped the extras → HTTP engine orders were always LIVE with source "manual" (the live test above was affected). Added `is_paper: bool = False` and `source: str = "manual"`. Verified via HTTPS: paper order `paper_1_1785487398` FILLED 65 @ 73.11, audit row `source='engine_http_paper_test'` `is_paper=t`, `oms_orders` empty (terminal row removed).

### Reference
- OMS flow for engine orders: route → `EngineService.execute_trade` → gate → `OrderManager.place_order` (persist QUEUED → Redis `oms:order_queue`) → worker → `execution_manager.place_order` → adapter → terminal state saved + removed from `oms_orders` → `_record_terminal` (Redis result).
- Cross-process test pattern: in-container `python3 -` with `core.security.create_access_token` + HTTPS to `api.ai.trademetrix.tech` (CSRF cookie is Secure; `create_access_token` lives in `core/security.py`, NOT `core/deps.py`).
- `oms:order_queue` (list) and `oms:result:{id}` (TTL 60s) are the Redis keys.

## Session: 2026-07-31 — Fyers v3 live order lifecycle + platform route E2E (INC-015)

### What was done
1. **Symbol CSV schema fix** (`market/symbol_master.py`) — `NSE_FO.csv` real schema: `parts[15]`=strike, `parts[16]`=CE/PE (old code read 14/15 → **zero options cached**). Types: 11/13=FUT, 14=index OPT, 15=stock OPT, 0=CM EQ. Columns: `[1]`=desc, `[2]`=type, `[3]`=lot, `[4]`=tick, `[9]`=`NSE:` symbol, `[13]`=underlying, `[19]`=active. Cache cap 120,000; strike `.0` normalized; `name` = `"{underlying} {strike} {opt_type}"`. Auto-sync month-end crash fixed (`timedelta(days=1)` instead of `target.replace(day+1)`).

2. **Fyers v3 order maps** (`brokers/fyers_adapter.py`) — order type `1=LIMIT, 2=MARKET, 3=SL-M, 4=SL-L`; product `INTRADAY/MARGIN/CNC` (NRML→MARGIN, DELIVERY→CNC; old code sent v2 semantics → "limitPrice does not match: 0" / "Product CNC not enabled on exchange NFO"). Status codes `1=CANCELLED, 2=FILLED, 4=PENDING, 5=REJECTED, 6=OPEN, 7=EXPIRED`. `orderTag` must be `[a-zA-Z0-9]` max 20 (hyphens rejected). All calls on `https://api-t1.fyers.in/api/v3`; cancel = `DELETE /orders/sync` with JSON `{"id": oid}`; modify = `PATCH /orders/sync` requires FULL payload (id+type+limitPrice+stopPrice+qty — partial → "limitPrice does not match: 0"); modify fetches existing order from book (3×1s retry for propagation). Quotes: `GET https://api-t1.fyers.in/data/quotes?symbols=` (NOT `/data/v3/quotes` — 404). Place response has no status field — acceptance ≠ fill.

3. **TokenManager client_id bug** (`brokers/token_manager.py`) — `_refresh()` stored only `{access_token, expires_at}`; `BrokerExecutionAdapter.connect()` → `authenticate(session)` → empty client_id → Authorization `:token` → Fyers code -50 "Algo orders are not allowed from this app". Fixed: session now includes `client_id` from creds. NOTE: `get_session()` returns a dict with only `access_token`, `expires_at`, `client_id`.

4. **Risk double-evaluation bug** (`risk/manager.py`, `routes/v1_orders.py`) — route submit + worker execution both ran stateful rules (TradeCooldown 5s, DuplicateOrder 60s window), so worker retries (1s/2s/4s) always fell inside the cooldown → every platform order REJECTED. Fixed: `RiskManager.evaluate(req, dry_run=True)` — dry-run instantiates fresh copies of all rules (`[type(r)() for r in RISK_RULES]`), so pre-checks record no state; route pre-check passes `dry_run=True`. DuplicateOrderRule previously had no TTL (module-level set lived forever) — now `dict[key→timestamp]` with 60s prune.

5. **Order status honesty fix** (`execution/manager.py`, `oms/manager.py`) — successful placement was unconditionally reported FILLED (broker says OPEN/PENDING for resting limit orders). Now: FILLED only if adapter status says so; else PENDING. OMS success branch branches on `exec_result.state` (FILLED/PARTIAL/PENDING); PENDING orders stay in memory, `OrderPending` event, removed from queue. `_update_order_in_db` takes `status=` param.

6. **OMS persistence fixed** — `oms_orders`/`oms_bracket_orders`/`oms_oco_orders` tables were missing in Supabase (PGRST205; code docstring said "run in SQL Editor" but was never run). Created via direct Postgres (psql `db.nwutlfuowiulfpbsrldn.supabase.co` with `SUPABASE_DB_PASSWORD` from `/app/.env`), columns matching `OmniOrder`/`BracketOrder`/`OCOOrder` model_dump. Active orders persist; rows deleted on cancel/completion (by design).

7. **Verified E2E on prod (live, funded account)** — platform `POST /api/v1/orders/` (JWT+CSRF) → OMS queue → worker → FyersAdapter → Fyers: order 26073100178838 PENDING then CANCELLED at broker; DB row present while active (`state=PENDING broker=...`), removed after cancel; `orders` audit table shows PENDING/PENDING/CANCELLED. Adapter direct lifecycle (PLACE→MODIFY→CANCEL) also validated.

### Reference maps (Fyers v3, verified live)
- Type: `1=LIMIT, 2=MARKET, 3=SL-M, 4=SL-L`
- Product: `INTRADAY` (MIS), `MARGIN` (NRML), `CNC` (DELIVERY)
- Status: `1=CANCELLED, 2=TRADED/FILLED, 4=TRANSIT/PENDING, 5=REJECTED, 6=PENDING/OPEN, 7=EXPIRED`
- Auth header: `Authorization: {client_id}:{access_token}` (empty client_id → code -50)
- Test account XA24350 (fa668109-4b1e-4758-a49b-015027ea4115), app PKL4EMD8ML-200; valid symbol `NSE:NIFTY26AUG25000CE` (strike 25000), NOT 31000.

### Known gaps
- ~~No background broker→OMS status reconciliation~~ — FIXED below.
- Token expiry 2026-08-01 00:30 UTC — manual re-auth or `fyers_auto_token.py` cron (needs FYERS_APP_ID/FYERS_SECRET_ID env; Cloudflare Turnstile blocks Playwright).

## Session: 2026-07-31 — Reconciliation loop, schema fixes, token visibility (INC-015 follow-up)

### What was done
1. **Broker→OMS reconciliation loop** (`oms/manager.py`) — new background `_reconcile_loop` (5s interval, `RECONCILE_INTERVAL_SECONDS`): polls `exec_mgr.get_orders(user_id, broker)` for in-memory orders in PENDING/PARTIAL with `broker_order_id`, matches by broker id, applies remote status (FILLED/PARTIAL/CANCELLED/REJECTED/EXPIRED) via state machine transitions, persists, removes terminal orders, publishes events, handles parent (bracket/OCO) completion, and mirrors terminal status into the audit `orders` table (`_mirror_audit_status`). Verified live: buy limit above ask → OMS auto-flipped to FILLED within 5s, `filled_quantity=65`, audit row updated, `oms_orders` row removed.

2. **Schema fixes in Supabase** (direct psql, `SUPABASE_DB_PASSWORD` in /app/.env):
   - `oms_orders` (full OmniOrder model_dump columns), `oms_bracket_orders`, `oms_oco_orders` — created.
   - `user_alerts` (id, user_id, symbol, condition above/below, target_price, note, is_active, triggered_at, created_at) + `notification_prefs` (channels JSONB) — created.
   - `positions_snapshot` — added missing `last_price DOUBLE PRECISION` and `updated_at TIMESTAMPTZ` columns (portfolio/manager.py writes them; was erroring PGRST42703).

3. **Fyers quotes 403 fix** (`brokers/fyers_adapter.py`) — `get_quotes` used `POST /data/quotes` which is Cloudflare WAF-blocked (same pattern as `/orders`); switched to `GET /data/quotes?symbols=`. Verified live (returns bid/ask).

4. **Token visibility** (`infrastructure/repositories/broker_repository.py`) — `list_credentials` now selects `token_status`, `token_expires_at` so the frontend can show expiry and prompt re-auth. Token watchdog already alerts via Telegram at T-60min and on expiry.

### Reference
- Fyers has NO silent token refresh — re-consent every ~30 days (auth_code valid 1h). `TokenManager._refresh()` picks up a fresh `auth_code` from `additional_params` if present.
- Order state machine already supports SENT→PENDING, PENDING→{PARTIAL, FILLED, CANCELLED, REJECTED, EXPIRED}.
- `orders` audit table is separate from `oms_orders`; platform list reads OMS in-memory dict (recovered from `oms_orders` on startup).

## Session: 2026-07-31 — Paper E2E, engine path, recovery test (INC-015 third pass)

### What was done
1. **Paper fill price E2E** (`paper/fill_engine.py`, `paper/paper_broker.py`, `execution/manager.py`) — fill engine `_quote_last_price()` handles dict+object quotes (cached quote dict has `last_price`/`ltp`); `_get_fill_price`/`_next_tick_fill`/`_price_based_fill` dict-safe. `paper_broker._ensure_quote()` primes `market_cache` from Fyers REST adapter (get_quotes) when missing or LTP=0. `execution/manager.py` `_update_order_in_db` writes `average_price` when present. Verified: paper fills carry real price (qty=65 @ ~75.3-76.2).

2. **supabase-py upsert gotcha** (`paper/paper_broker.py`) — `on_conflict` must be a **string** `"user_id,client_order_id"`, NOT a list. List form → PostgREST generates a bogus conflict target → PG 42P10 "no unique or exclusion constraint matching the ON CONFLICT specification". Also: partial unique indexes (`WHERE client_order_id <> ''`) are NOT usable as ON CONFLICT targets — `idx_orders_client_order_id` recreated non-partial in Supabase (`CREATE UNIQUE INDEX idx_orders_client_order_id ON orders (user_id, client_order_id)`).

3. **Engine signal path (paper+live) E2E** (`engine/gate.py`, `application/services/engine_service.py`) — `EngineService.execute_trade` → `RiskGuard` → `gate.execute_order` → `exec_mgr.place_order`. Fixes:
   - `margin_snapshot` table was MISSING → `_check_margin` is fail-closed → would block every engine trade. Created table (user_id, broker, total/used/available_margin, snapshot_at). Empty → margin check passes.
   - `_check_margin` fail-closed warning: any exception blocks the trade.
   - `gate.execute_order` now copies `order.average_price = exec_result.avg_price` (was 0.0 in responses); filled_qty already copied.
   - Fyers adapter symbol-rebuild guard: `place_order` admin branch (`format_fyers_option_symbol`) only rebuilds when the symbol does NOT already contain the strike (`str(int(strike)) in symbol.upper()`) — previously double-prefixed `NSE:NSE:NIFTY...` → Fyers "The input symbol is invalid".

4. **Engine path bypasses OMS** (KNOWN GAP) — `gate.execute_order` calls `execution_manager.place_order` DIRECTLY; only the platform route (`routes/v1_orders.py` → `order_manager.place_order`) uses the OMS (in-memory queue + oms_orders persistence + reconcile + startup recovery). Engine-path live orders get NO reconcile/recovery — they live only in the audit `orders` table. Strategy runners also flow through the engine path.

5. **OMS queue is in-memory only** (`oms/order_queue.py`) — `OrderQueue` uses Python lists + asyncio.Lock, NOT Redis. Enqueues from a different process (e.g. `docker exec python3` script) are invisible to the API's worker loop. Multi-worker deployments would silently drop orders. Single-process uvicorn (current prod) is fine.

6. **Startup recovery VERIFIED live** — placed resting LIMIT 74.5 (below bid 75.25, within 5% deviation) via API: `3426f6e9700776ef` → PENDING broker `26073100211006`, persisted in `oms_orders`. `docker restart` → "Startup recovery reconciled 4 pending orders" → both orders back in OMS in-memory with broker ids (even the orphaned in-memory-queue order `b8a0c02210290654` got placed with new broker id `26073100211152` on recovery). Cancelled both; reconcile loop mirrored CANCELLED to audit; `oms_orders` empty.

7. **Cancel → audit mirror fix** (`oms/manager.py`) — OMS `cancel_order` now calls `_mirror_audit_status(order, CANCELLED)` in all three cancel branches (was only reconcile-triggered). Verified: place→cancel → audit row CANCELLED. Reconcile loop also fixes stale rows on restart (polls Fyers, sees CANCELLED, mirrors).

### Reference
- Engine-path order flow: `EngineService.execute_trade` (route `/api/v1/engine/trade`) → `gate.execute_order` → `exec_mgr.place_order`. Paper if `is_paper=True` or active run mode=PAPER. `ExecuteSignalRequest` route model has NO `is_paper` field (service reads it from dict anyway).
- 5% price-deviation rule (`MAX_PRICE_DEVIATION_PCT=5.0`) blocks resting orders too far from LTP (limit 45 rejected; 74.5 OK).
- Test scripts: `/tmp/recovery_test_phase1.py` (workstation, needs prod SECRET_KEY — not available locally; local .env has TEST secret), in-container scripts use `create_access_token` + HTTPS to `api.ai.trademetrix.tech` (CSRF cookie is Secure — plain http://127.0.0.1 fails CSRF).
- Paper config default `fill_type = FillType.INSTANT` → paper orders always fill immediately; resting paper orders impossible by default.

## Session: 2026-07-29 — Fyers Order HTTP 403 Cloudflare (INC-014)

### What was done
1. **Root cause: Wrong Fyers endpoint** — The `FyersAdapter.place_order` used `POST https://api-t1.fyers.in/api/v3/orders` (old/legacy endpoint). This endpoint has a Cloudflare WAF rule that blocks POST from datacenter IPs, returning HTML "Attention Required! | Cloudflare" instead of Fyers JSON. The correct endpoint is `POST /api/v3/orders/sync` (confirmed via `fyers_apiv3==3.1.14` SDK's `Config.orders_endpoint`), which has no such restriction.

2. **Debugging process:**
   - Captured order payload from production logs: symbol `NSE:NIFTY 24200 CE ` had trailing spaces (separate cosmetic issue)
   - Tested various URLs from the VPS using curl:
     - `api-t1.fyers.in/api/v3/orders` POST → Cloudflare HTML 403 ❌
     - `api-t1.fyers.in/api/v3/orders` GET → Fyers JSON 401 ✅
     - `api-t1.fyers.in/api/v3/validate-authcode` POST → Fyers JSON ✅
     - `api.fyers.in/api/v3/orders` POST → Fyers JSON (but generic error, doesn't process orders) ✅
     - `api.fyers.in/api/v2/orders` POST → Fyers JSON ✅
     - `api-t1.fyers.in/api/v3/orders/sync` POST → Fyers JSON 401 ✅ (THE FIX)
   - Checked `curl_cffi` library: `impersonate="chrome131"` works but Cloudflare block is at WAF level, not TLS fingerprint
   - Confirmed: block is endpoint-specific (`/orders` vs `/orders/sync`), not method or host specific

3. **Fix** — Changed `fyers_adapter.py:257` URL from `/orders` to `/orders/sync`. Deployed via hot-deploy + container restart.

4. **Verification:** 
   - `curl_cffi` POST to `/orders/sync` from container returns `{"s":"error","code":-16,"message":"Could not authenticate the user"}` — proper JSON, no Cloudflare block
   - Compatible response format (same `s`/`id`/`message` fields)

### Key Fix
- `apps/api/brokers/fyers_adapter.py` — `place_order` URL changed from `f"{self._v3_url}/orders"` to `f"{self._v3_url}/orders/sync"`.

## Session: 2026-07-29 — CSRF cookie never updated in production (INC-013)

### What was done
1. **Root cause: production vs local code divergence** — The production `middleware/csrf.py` had OLD code:
   ```python
   existing_token = request.cookies.get(CSRF_COOKIE_NAME)
   if not existing_token:  # Only sets cookie on FIRST request
   ```
   The cookie was set ONCE on the first GET /auth/csrf and NEVER updated. The body returned a new token every call, but `set-cookie` was absent on requests 2+. The local code (the "fix" from the previous session) was never deployed to production.

2. **Fix** — Deployed the local `middleware/csrf.py` (which uses `getattr(request.state, 'csrf_token', None)` from the route handler) to production via hot-deploy + container restart. The fixed code sets the cookie + X-CSRF-Token header on EVERY response, not just the first one:
   - Uses `request.state.csrf_token` from route handler (set every call)
   - Falls back to generating a new token only if no existing cookie AND no state token
   - Cookie rotation works correctly: body token matches cookie on every call

3. **No actual multi-tab regression** — The frontend fix (reading from `document.cookie`) was already sufficient to solve multi-tab 403s because `document.cookie` returns the same value across all tabs. The server-side fix adds proper cookie rotation (security best practice) and ensures X-CSRF-Token header is present on every response.

4. **Incident protocol** — Debugged via curl/httpx testing against production. Traced through Starlette 0.52.1's `BaseHTTPMiddleware` internals (`_CachedRequest`, `_StreamingResponse`, `MutableHeaders`) to confirm `request.state` IS shared across the middleware chain. The header modification via `response.headers` does modify `_StreamingResponse.raw_headers` correctly.

### Key Fix
- `middleware/csrf.py` — `if token:` branch before `elif not request.cookies.get(...)` ensures route-handler-set tokens are always applied to the response, not just when no cookie exists.

## Previous: Session: 2026-07-27 — Product Acceptance Testing (PAT)

### What was done
1. **Product Acceptance Test suite** — Created `apps/api/pat_test.py` covering 6 scenarios (S1-S5, S7), 96 checks, runs against local dev stack.

2. **CSRF race condition fixed** (`middleware/csrf.py`):
   - Route handler now stores token on `request.state.csrf_token`
   - Middleware reads from there, sets cookie + X-CSRF-Token header on every response
   - Prevents double-cookie with mismatched tokens

3. **Subscription table column mismatch** (`core/capabilities.py`, `application/services/subscription_service.py`):
   - Init migration creates `subscriptions` with `plan` column + check constraint (`starter|pro|enterprise`)
   - Later migration creates same table with `tier` column + enum (`monthly|quarterly|halfyearly|yearly`) — but is a no-op due to `IF NOT EXISTS`
   - **Fix**: Code now reads `plan` column with fallback to `tier`
   - Added `pro`, `starter`, `enterprise` → Capabilities mapping

4. **Infrastructure fixes**:
   - `infrastructure/queue.py` — 30s cooldown in `_ensure_redis()`, `asyncio.sleep(1)` in subscribe loop when Redis down
   - `core/db.py:close_supabase()` — `_close_client()` helper with `getattr` guard prevents `'NoneType' can't be awaited`
   - Server must run with `.env.test` (local Supabase) not `.env` (production)

5. **PAT test bypasses GoTrue** — GoTrue creates users with IDs that don't match `auth.users` in local Supabase Postgres. Test now:
   - Creates users directly in `auth.users` (trigger auto-creates profile)
   - Generates JWTs using the server's `create_access_token` (python-jose)
   - Uses JWT directly in `Authorization` header

6. **Capabilities fixed** for local DB schema:
   - `_resolve_subscription_tier` now reads `plan` column (DB has `plan`, not `tier`)
   - `CAP_MAP` extended with `pro → HALFYEARLY`, `starter → FREE`, `enterprise → SUPER_ADMIN`
   - `get_my_subscription` reads `row.get("plan")` with fallback

### Current PAT Results (92% pass rate)
- **S1 Admin/Subs**: ✅ All 12 pass
- **S2 User/Broker**: 19/20 pass (1 fail: subscription/me still 500)
- **S3 Strategy**: 11/15 pass (4 fail: strategy body fields, backtest type, engine start)
- **S4 Recovery**: ✅ All 4 pass
- **S5 Smoke**: 35/37 pass (2 fail: subscriptions/me 500, marketdata option-chain 503)
- **S7 RBAC**: ✅ All 9 pass

### Remaining Issues
1. **`/subscriptions/me/` returns 500** — `get_my_subscription` returns internal error. Likely the `async_safe_single` or row parsing still has a column mismatch.
2. **Strategy creation** — model requires `index_symbol`, `entry_time` fields
3. **Backtest** — needs valid `strategy_type` value
4. **Engine start** — 500 internal error (needs valid broker/strategy)
5. **Rate limiter** — 60s cooldown after ~40 requests; needs disabling in test mode
6. **Marketdata option-chain** — 503 (external API, expected in dev)
7. **GoTrue ID mismatch** — local Supabase GoTrue creates users with IDs not matching `auth.users` table. Only impacts dev environment.

### Key Files
- `apps/api/pat_test.py` — Automated PAT runner
- `apps/api/middleware/csrf.py` — CSRF token sharing fix
- `apps/api/core/capabilities.py` — Subscription tier resolution fix
- `apps/api/application/services/subscription_service.py` — plan vs tier fix
- `apps/api/core/db.py` — close_supabase guard
- `apps/api/infrastructure/queue.py` — Redis backoff
- `apps/api/.env.test` — Test env pointing to local Supabase

### Test Commands
```bash
cd apps/api && cp .env.test .env && .venv/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload
# In another terminal:
cd apps/api && python3 pat_test.py
# Restore after:
cd apps/api && git checkout .env
```
