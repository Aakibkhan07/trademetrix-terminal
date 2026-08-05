# Production Incidents Log

## INC-015: Kill-Switch Global Gate Silently Disabled + Emergency State Lost on Restart (2026-08-04)

**Severity:** Critical  
**Status:** Resolved (deployed 2026-08-04, commit `fd896ca`)  
**Root Cause:** Two independent defects in `risk/kill_switch.py`:
1. `global_kill_switch_active()` probed `risk_settings` for a row with `user_id='system'`. The column is a uuid FK, so `'system'` was always a `22P02 invalid input syntax for type uuid` (8 failures/48h observed) and the probe always returned False — the global kill switch gate was **silently disabled**. Any "enable global kill switch" action would not actually stop trading.
2. Emergency-stop state was in-memory only. A container restart silently cleared any active emergency stop and there was no restart recovery path.
3. `_persist_audit()` wrote to `risk_audit_log`, which did **not exist** in the prod schema (`PGRST205`, seen 3-4×/48h) — emergency-stop audit records were silently dropped.
**Fix:**
- Global gate reads Redis `global:kill_switch` flag (set/cleared by admin enable/disable).
- Emergency state persisted to Redis (`kill_switch:emergency:{uid}`); `recover()` restores from Redis on startup before trading can resume.
- `_persist_audit()` writes `risk_audit_log` with automatic fallback to the existing `audit_log` table when `risk_audit_log` is missing.
- Idempotent migration `supabase/migrations/20260804_01600_risk_audit_log.sql` (TEXT user_id, index on `(user_id, event, created_at DESC)`) — **not yet applied to prod** (DDL access blocked); fallback keeps audit working meanwhile.
**Files Changed:** `apps/api/risk/kill_switch.py`, `supabase/migrations/20260804_01600_risk_audit_log.sql`, `apps/api/tests/test_kill_switch_hardening.py` (7 tests), `apps/api/tests/test_risk_fail_closed.py`, `apps/api/tests/test_auto_trading.py`
**Verification:** Prod smoke: emergency POST → `kill_switch:emergency:{uid}` set in Redis → fresh `KillSwitch().recover()` sees the stop (restart-safe) → release clears the key; global enable sets Redis flag and `global_kill_switch_active()` returns True; both cleared afterward. Post-deploy logs: 0× `invalid input syntax for type uuid: "system"`.

## INC-016: Raw 500s on `/engine/positions|funds` from Expired Broker Token (2026-08-04)

**Severity:** High  
**Status:** Resolved (deployed 2026-08-04, commit `fd896ca`)  
**Root Cause:** With an expired Fyers token, every positions/funds call produced an ASGI traceback: `RuntimeError: Token refresh failed for {uid}:fyers: CircuitBreaker[broker_fyers] is open` (43×/48h), leaking raw 500s to the web client instead of a structured error.  
**Fix:**
- `TokenManager` fast-fails with `BrokerTokenExpiredError` (401, code `BROKER_TOKEN_EXPIRED`) when the stored token is already past its expiry (before any broker construction), and translates an open circuit breaker during refresh into the same structured error.
- `EngineService.get_positions/get_funds` propagate `BrokerTokenExpiredError` (→ 401 with code, so the UI can prompt broker re-auth) while still degrading transient broker failures (`RuntimeError`/`CircuitBreakerError`) to empty data instead of 500.
**Files Changed:** `apps/api/core/exceptions.py`, `apps/api/brokers/token_manager.py`, `apps/api/application/services/engine_service.py`, `apps/api/tests/test_token_manager_hardening.py` (4 tests), `apps/api/tests/test_engine_service.py` (+4 tests)
**Verification:** Post-deploy logs: 0× `CircuitBreaker[broker_fyers] is open` tracebacks on `/engine/*`. (Live 401 path was unit-tested only — the prod token was re-validated by the auto-refresh cron before the smoke could exercise it; positions/funds returned real 200s.)

## INC-017: Paper Bracket Quote Starvation + 5542-line Log Spam (2026-08-04)

**Severity:** Medium  
**Status:** Resolved (deployed 2026-08-04, commit `fd896ca`)  
**Root Cause:** `_bracket_quote_fetch` resolved SL/TARGET prices for paper bracket orders through the Fyers REST client exclusively. With the expired token, every 5s evaluation logged `Paper bracket quote refresh failed ... CircuitBreaker[broker_fyers] is open` (5542×/48h) and paper exits were starved of quotes.  
**Fix:** Paper brackets now prefer the market cache, then a broker-agnostic Yahoo `fetch_quotes` (with write-back), and only fall back to the broker REST client last. Warning logging is throttled to 1/min/symbol.
**Files Changed:** `apps/api/oms/manager.py`, `apps/api/tests/test_bracket_quote_hardening.py` (4 tests)
**Verification:** Post-deploy logs: 0× `Paper bracket quote refresh failed` since restart.

## INC-001: CSRF Race Condition (2026-07-27)

**Severity:** Critical  
**Status:** Resolved  
**Root Cause:** CSRF middleware set cookie and header independently; on concurrent requests the token from cookie could differ from header, causing 403 on state-modifying requests.  
**Fix:** Route handler stores token on `request.state.csrf_token`, middleware reads from state and sets both cookie + header on every response.  
**Files Changed:** `apps/api/middleware/csrf.py`  
**Verification:** 98/98 PAT pass, all state-modifying operations succeed.

## INC-002: Subscription Table Column Mismatch (2026-07-27)

**Severity:** High  
**Status:** Resolved  
**Root Cause:** Init migration creates `subscriptions` with `plan` column; later migration creates same table with `tier` column (no-op due to `IF NOT EXISTS`). Code expected `tier`.  
**Fix:** Code reads `plan` column with fallback to `tier`.  
**Files Changed:** `apps/api/core/capabilities.py`, `apps/api/application/services/subscription_service.py`  
**Verification:** Subscription endpoint returns correct tier data.

## INC-003: Order Lifecycle Validation Failure for Paper Trades (2026-07-28)

**Severity:** Critical  
**Status:** Resolved  
**Root Cause:** `place_order()` via `/engine/trade` created `NormalizedOrder` without `is_paper=True`. Gate resolved broker from `broker_credentials` (Fyers), not the active PAPER run. Risk validation then rejected with "Validation failed" due to market-hours check.  
**Fix:** 
- `EngineService.execute_trade()` queries `strategy_runs` for active PAPER run → sets `is_paper=True`
- `gate.py execute_order()` checks `order.is_paper` before resolving broker, uses "paper" directly  
**Files Changed:** `apps/api/application/services/engine_service.py`, `apps/api/engine/gate.py`  
**Verification:** Signal → FILLED (broker="paper", is_paper=true, filled_qty=10). 98/98 PAT pass.

## INC-004: Positions Lost After Server Restart (2026-07-28)

**Severity:** High  
**Status:** Resolved  
**Root Cause:** Three layers:
1. `EngineService.get_positions()` resolved broker from `broker_credentials` (Fyers), but paper positions stored under broker="paper" in PortfolioManager  
2. PaperBroker's `_positions` dict was in-memory only; lost on restart  
3. `positions_snapshot` table never written for paper broker  
**Fix:**
- `get_positions()`/`get_funds()` now check for active PAPER run and route to PortfolioManager
- `PaperBroker.connect()` calls `_restore_positions()` from orders table  
**Files Changed:** `apps/api/application/services/engine_service.py`, `apps/api/paper/paper_broker.py`
**Verification:** TCS position (qty=80) restored across restart from 7 filled orders. 98/98 PAT pass.

## INC-005: UserStrategyRunner TypeError (2026-07-28)

**Severity:** Low  
**Status:** Resolved  
**Root Cause:** `current_dow not in days_of_week` raised TypeError when `days_of_week` stored as string in DB (not list).  
**Fix:** Type-safe parsing for both string and list formats.  
**Files Changed:** `apps/api/engine/user_strategy_runner.py`  
**Verification:** No TypeError in logs. 98/98 PAT pass.

## INC-006: Missing Admin API Routes (2026-07-28)

**Severity:** Medium  
**Status:** Resolved  
**Root Cause:** `v1_admin.py` only registered 7 routes (backups + kill-switch) while `AdminService` implements ~40 methods and the frontend admin UI calls ~30 endpoints. All missing routes returned 404.  
**Fix:** Registered all missing admin routes: users CRUD, assignments CRUD + batch/export/import, brokers list + Fyers validate/re-auth, orders, positions, audit-log, risk, active-brokers, admins CRUD, broadcast recipients/send/notify, catalog strategies CRUD, execute-trade.  
**Files Changed:** `apps/api/routes/v1_admin.py`, `apps/api/tests/test_admin_service.py`  
**Verification:** All 30+ admin endpoints now return 401/403 (properly protected) instead of 404. 42 route tests pass, 475 total tests pass.

## INC-007: Market Watchlist Missing Component (2026-07-28)

**Severity:** Low  
**Status:** Resolved (2026-08-06)  
**Root Cause:** `/watchlist` route not registered in Next.js app router; sidebar linked to it → 404.
**Fix:** The watchlist feature now lives in the Workspace (`components/workspace/watchlist-panel.tsx`,
`command-palette.tsx` opens it); the standalone `/watchlist` link no longer exists in
`app-layout.tsx` (only `/workspace` is linked). No 404-able href remains. Verified: sidebar
href list has no `/watchlist`; `watchlist-panel` reachable via Workspace + ⌘K. Documentation
stale — corrected here.

## INC-008: Universal Search Shows No Results (2026-07-28)

**Severity:** Medium  
**Status:** Resolved  
**Root Cause:** Two layers:
1. The `app-layout.tsx` command palette had `searchQuery` state and an empty results div but **never fetched from the API** — no `useEffect` or fetch logic existed.
2. The backend F&O symbol cache (`_fo_cache`) was always empty because `start_auto_sync()` was never called during app startup, and the NSE F&O API endpoint returns 404, so the scheduled sync always yielded 0 symbols.  
**Fix:**
- **Frontend** (`apps/web/components/app-layout.tsx`): Imported `{ api }` from `@/lib/api`, added `searchResults`/`searchLoading` state, added debounced 300ms `useEffect` that calls `api.get('/market/instruments?query=...')`, renders results as clickable `<Link>` items to `/terminal?symbol=...`, shows "No matching symbols found" empty state.
- **Backend** (`apps/api/main.py`): Added `symbol_master.start_auto_sync()` call in the lifespan startup handler.
- **Backend** (`apps/api/market/symbol_master.py`): Reordered `_auto_sync_loop` to sync immediately on startup instead of waiting until 2:30 AM UTC. Added `_seed_common_symbols()` with 68 hardcoded NSE F&O symbols as fallback when NSE API is blocked.  
**Verification:** Search API returns real results. Playwright test confirms ⌘K opens palette, typing "NIFTY" shows 4 matching symbols, clicking navigates to `/terminal?symbol=NIFTY`.

## INC-011: Backtest "Failed to fetch" — CORS + CSRF Race (2026-07-28)

**Severity:** Critical  
**Status:** Resolved  
**Root Cause:** Two layers:
1. **CORS middleware ordering** (`main.py`): `CORSMiddleware` was registered BEFORE `CSRFProtectMiddleware`. Since middlewares are nested innermost-first, the CSRF middleware was the OUTERMOST wrapper. When CSRF validation failed, it returned a 403 response directly without calling inner middlewares, so `CORSMiddleware` (being inner) never got to add CORS headers. The browser saw a CORS error (`net::ERR_FAILED`) and reported "Failed to fetch" instead of the actual 403.
2. **CSRF cookie stale on page refresh** (`middleware/csrf.py`): The `/auth/csrf` route handler generates a NEW random token on every call, while the CSRF middleware only set the cookie when no cookie existed (`if not existing_token`). On page refresh, the client stores the new token from the response body, but the browser sends the OLD cookie — mismatch → 403.

**Fix:**
- **CORS ordering** (`apps/api/main.py`): Moved `CORSMiddleware` registration to LAST (outermost), so CORS headers are added to ALL responses including CSRF 403 errors.
- **CSRF cookie refresh** (`apps/api/middleware/csrf.py`): Changed cookie logic to ALWAYS set the cookie when `request.state.csrf_token` is provided by the route handler, ensuring the cookie matches the returned token on every request.  
**Verification:** Full regression (13 checks): login, search, backtest, strategies, settings, terminal, 5 admin tabs — all pass. Backtest API returns 200 with no CORS or CSRF errors. Replayed through Playwright headless browser — request flow now shows RESP: 200.  
**Files Changed:** `apps/api/main.py`, `apps/api/middleware/csrf.py`

## INC-009: Backend /backtest Fails with "Invalid price" (2026-07-28)

**Severity:** Low  
**Status:** Resolved (2026-08-06)  
**Root Cause:** The backtest/order payload validation rejected MARKET orders with "Invalid price".
**Fix:** `execution/validation.py` now only requires `price` for LIMIT/SL/SLM orders and
`trigger_price` only for SL/SLM (`Price is required for LIMIT/SL/SLM orders`); MARKET orders
pass with price omitted/0. The backtest engine was also rebuilt (v1.5.9–v1.6.1) with its own
fill engine that prices MARKET fills directly. Verified: `execution/validation.py:46-49`.
Documentation stale — corrected here.

## INC-013: Production CSRF Middleware Never Deployed (2026-07-29)

**Severity:** High  
**Status:** Resolved  
**Root Cause:** The CSRF middleware fix from INC-001/INC-011 was applied to the local source tree but NEVER deployed to production. The production container still ran the OLD code:
```python
existing_token = request.cookies.get(CSRF_COOKIE_NAME)
if not existing_token:  # Only sets cookie on FIRST request
```
This meant the `set-cookie` header was only emitted on the very first GET /auth/csrf. Subsequent calls returned a new token in the response body but never updated the cookie. The X-CSRF-Token header was also absent on responses 2+.  
**Fix:** Deployed the local `middleware/csrf.py` to `trademetrix_api:/app/middleware/csrf.py` via hot-deploy + container restart. The fixed code prioritizes `request.state.csrf_token` (set by route handler on every call) over the cookie-exists check, ensuring the cookie is updated on EVERY response.  
**Files Changed:** `apps/api/middleware/csrf.py` (deployed to production container `trademetrix_api`)  
**Verification:** 5/5 sequential GET /auth/csrf calls now return `set-cookie` and `x-csrf-token` headers with matching tokens. CSRF 403 enforcement still works (invalid token → 403, valid → passes).

## INC-014: Fyers Order HTTP 403 — Wrong endpoint `/orders` vs `/orders/sync` (2026-07-29)

**Severity:** Critical  
**Status:** Resolved  
**Root Cause:** The Fyers adapter used `POST https://api-t1.fyers.in/api/v3/orders` to place orders. This endpoint is protected by a strict Cloudflare WAF rule that blocks POST requests from datacenter/VPS IP ranges, returning HTML "Attention Required! | Cloudflare" instead of Fyers JSON. The correct Fyers v3 order placement endpoint is `POST https://api-t1.fyers.in/api/v3/orders/sync` (as documented by the official `fyers_apiv3` SDK at `Config.orders_endpoint = "/orders/sync"`), which has no Cloudflare WAF restrictions.

**Evidence:**
- `GET https://api-t1.fyers.in/api/v3/orders` → Fyers JSON ✅ (Cloudflare allows GET)
- `POST https://api-t1.fyers.in/api/v3/orders` → Cloudflare HTML 403 ❌
- `POST https://api-t1.fyers.in/api/v3/orders/sync` → Fyers JSON ✅
- `POST https://api.fyers.in/api/v3/orders` → Fyers JSON ✅ (different host, no block but also doesn't process orders — returns generic error)

**Fix:** Changed `fyers_adapter.py:257` from `f"{self._v3_url}/orders"` to `f"{self._v3_url}/orders/sync"`. Deployed via hot-deploy + container restart.  

**Verification:** 
- Container test with dummy credentials: POST to `/orders/sync` returns `{"s":"error","code":-16,"message":"Could not authenticate the user"}` — proper Fyers JSON, no Cloudflare block.
- `api.fyers.in/api/v3/orders` POST,
- `api.fyers.in/api/v2/orders` POST both work as fallbacks (return JSON, not HTML).
- The official `fyers_apiv3==3.1.14` SDK's `Config.orders_endpoint = "/orders/sync"` is the authoritative source for the correct endpoint.

**Files Changed:** `apps/api/brokers/fyers_adapter.py` line 257

## INC-010: OpenAPI Schema Duplicate Content-Type (2026-07-28)

**Severity:** Low  
**Status:** Resolved (2026-08-06)  
**Root Cause:** Reported FastAPI auto-generated OpenAPI schema listing `Content-Type: application/json` multiple times, breaking Swagger UI and generated clients.
**Fix:** No fix needed — verified the current schema has **0 duplicate content-types** across all
228 paths (regenerated locally via `app.openapi()` and scanned every response). The duplicate
content-type was a transient/older-framework artifact. Note: `openapi_url=None` in prod
(`main.py:267`) — the schema is only served locally anyway. Documentation stale — corrected here.