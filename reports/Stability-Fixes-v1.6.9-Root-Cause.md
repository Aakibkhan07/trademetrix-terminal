# Root Cause Report — v1.6.9 Stability Sprint

**Date:** 07 Aug 2026 · **Scope:** the four verified product-acceptance defects (P1-1, P1-2, P1-3, P2-1)
from `reports/Product-Acceptance-Audit-v1.6.8.md`
**Status:** ALL FIXED, code-verified locally (979 API tests passed, web tsc/lint/build clean)

---

## Summary table

| Defect | Symptom on prod | Root cause (verified) | Fix location | Status |
|--------|-----------------|------------------------|--------------|--------|
| P1-1 | `/workspace` option chain always 503 (`symbol=NIFTY50-INDEX`) | (a) index symbols not normalized to provider form; (b) dead-code bug in Fyers parser returned `None` on success; (c) buggy mock generator crashes | `apps/api/market/option_chain.py` + `apps/api/routes/v1_marketdata.py` | FIXED |
| P1-2 | AI Journal `GET /ai/journal` CORS-blocked → insights never render | (a) `trades.created_at` missing on prod → 500; (b) unhandled 500 served by ServerErrorMiddleware bypasses CORSMiddleware | migration + `apps/api/ai/journal.py` + `apps/api/routes/v1_ai.py` + `apps/api/main.py` + `apps/api/core/response.py` | FIXED |
| P1-3 | 3 admin dashboard tabs show 404 HTML | (a) routers `/admin/users/with-brokers` + `/admin/ip-whitelist*` don't exist; (b) relative fetches hit the Next.js origin, not the API | `apps/api/routes/v1_admin.py` + 3 web tab components + `apps/web/lib/api.ts` | FIXED |
| P2-1 | 6 wrong passwords → 401 each, 7th correct → 200 (no throttle) | `signin` proxies straight to Supabase token endpoint with no in-app attempt limiter | `apps/api/routes/v1_auth.py` | FIXED |

---

## 2. P1-1 — Option chain index symbols 503

**Observed:** `/workspace` fetches `option-chain?symbol=NIFTY50-INDEX` → 503 on every load; `SENSEX` also 503; only `NIFTY`/`BANKNIFTY` return 200.

**Root causes (three, all confirmed by source inspection):**
1. **Symbol normalization missing.** The workspace default symbol is `NIFTY50-INDEX` (the frontend strips the `NSE:` prefix in `watchlist-panel.tsx:21`). Because the raw symbol never matched the Fyers/NSE symbol map, unsupported symbols fell through to `None` → 503.
2. **Fyers dead-code bug (`_fetch_fyers_option_chain`).** The entire success-parsing block was nested under `if data.get("s") != "ok" and data.get("code") != 200:` — it was **only reachable on error responses**, indent was wrong so successful Fyers chains always returned `None`. Fix: dedent the block into the success path.
3. **Buggy local mock fallback.** `v1_marketdata.py` `_generate_mock_option_chain` had a loop where `option_chain.append` was outside the `for` loop, causing wrong indentation so the mocked chain was never appended correctly.

**Fix:** a shared, single `normalize_index_symbol()` in the engine (strips `NSE:`/`BSE:`/`NFO:`, maps `NIFTY50-INDEX→NIFTY`, `NIFTYBANK-INDEX→BANKNIFTY`, `FINNIFTY-INDEX→FINNIFTY`, `SENSEX-INDEX→SENSEX`); engine `get_option_chain`/`get_expiries` normalize first; supported families always get a chain (live NSE → Fyers → deterministic simulated fallback flagged `is_simulated`), never 503; unsupported symbols → `None` (engine returns `{}`, route 503 as designed, but supported symbols now always resolve).

**Verification:** 7 new unit tests in `apps/api/tests/test_option_chain_normalize.py` (normalization, aliases, passthrough, simulated chain shape for all 4 index symbols, unsupported→`None`, ATM-around, PCR/max-pain math).

---

## 3. P1-2 — AI Journal CORS-blocked 500

**Root cause (two layers):**
1. **Data layer:** prod `trades` table is schema-drifted — ONLY `id, user_id, symbol, quantity, pnl` (verified by column probing); it is MISSING `created_at, order_id, side, price, value, broker, exchange, is_paper, strategy_id, trade_time`. `ai/journal.py::_get_recent_trades` queried `trades.created_at` → PostgREST `42703` → unhandled → 500. The canonical `orders` table has the full schema incl. `created_at` and is the real fill ledger.
2. **CORS layer:** 500 responses never carry `access-control-allow-origin`. Verified on prod: journal 500 has NO ACAO; 200s carry ACAO + `Vary: Origin`. Starlette 1.3.1 `build_middleware_stack` = `[ServerErrorMiddleware] + user_middleware + [ExceptionMiddleware]` applied **reversed**, so ServerErrorMiddleware (which serves unhandled 500s) is OUTERMOST, **outside CORSMiddleware** — CORS never runs on error-path responses.

**Fix:**
- Migration `supabase/migrations/20260807_01900_trades_schema_align.sql` — idempotent `ADD COLUMN IF NOT EXISTS` per canonical `init.sql` (order_id, strategy_id, broker, exchange, side, price, value, trade_time, is_paper, created_at) + index.
- `_get_recent_trades` hardened: **orders-first** (FILLED, ordered `created_at desc`, normalized row shape), `trades` table fallback if no orders, and both queries wrapped in try/except → empty list. Journal never 500s on schema drift.
- Graceful route: `get_journal` wraps `analyze_trades` in try/except → returns `{"analysis": "AI journal is temporarily unavailable.", "stats": {}}` instead of 500.
- CORS on unhandled 500s: `core/response.py::error_response` (and `api_response`) gained `headers:` param; `main.py` added `_cors_headers_for(request)` (echoes allowed origin + `Vary: Origin` + credentials, mirroring CORSMiddleware) and the global `@app.exception_handler(Exception)` now passes those headers.

**Verification:** `apps/api/tests/test_journal_resilience.py` (5 tests) — orders-first wins, trades fallback, orders-error→trades, schema-drift → `[]`, graceful analysis when no trades.

---

## 4. P1-3 — Three admin tabs call non-existent endpoints

**Verified root cause:** the routers never had these endpoints, and the components use relative `fetch('/api/v1/...')` which resolves to the **Next.js origin** (which serves HTML for all paths — not proxied), so the client got HTML 404s. Proven: `GET /admin/users/with-brokers` on the API was 405 (shape collides with `PATCH /admin/users/{user_id}`), `GET /admin/ip-whitelist` → 404.

**Fix (backend):** added to `apps/api/routes/v1_admin.py` (all `require_super_admin`), reusing existing `AdminService` methods:
- `GET /admin/users/with-brokers` → `list_users_with_brokers()`
- `GET /admin/ip-whitelist`, `POST /admin/ip-whitelist` (`AddWhitelistIPRequest`), `DELETE /admin/ip-whitelist/{ip_id}` → existing service methods (cache `admin_ip_whitelist` invalidation + audit included).

**Fix (web):** converted the raw relative fetches to the typed `api` client (`API_BASE`):
- `apps/web/lib/api.ts`: added `admin.users.withBrokers()` + `admin.ipWhitelist.{list,add,remove}`; widened `executeTrade` result typing.
- `trade-router-tab.tsx`: `/admin/users/with-brokers`, `/market/option-chain`, `/marketdata/instruments`, `/admin/execute-trade` all via `api`.
- `ip-whitelist-tab.tsx`: list/add/delete via `api.admin.ipWhitelist`.
- `admin-content.tsx` TradesTab: option-chain, instruments, execute-trade via `api`; removed now-dead `getCSRF()` helpers (the client already handles CSRF in `request()`).

---

## 5. P2-1 — Login rate-limiting / lockout

**Root cause:** `signin` proxied straight to Supabase's token endpoint; no attempt limiter at the app layer within the window.

**Fix:** in `apps/api/routes/v1_auth.py` — `core.cache`-backed throttle keyed `loginfail:{email}:{ip}` (client IP from first `X-Forwarded-For` hop, matching the AdminIPWhitelist behavior). Per the security constraint "never degrade the success path": a correct credential check merely resets the counter; only failed attempts progress through a **progressive delay** (0.5s → …), capped at 5s, and rejection is `429 Too Many Requests` after 5 failures within a 5-minute window. Audit entries `auth_failed` / `login_locked`. Graceful when Redis is down (cache singleton returns defaults, throttle no-ops safe).

**Verification:** `apps/api/tests/test_auth_throttle.py` (4 tests — forwarded-IP extraction, socket fallback, success clears, progressive+lockout 429).

---

## 6. Verification gates

All seven validation gates run locally before deploy:
- Unit: 16 new tests (option-chain normalizing/mock, journal resilience, throttle).
- Integration/Regression: full `apps/api` suite — **979 passed, 1 xfailed** (baseline 963/1) + `test_admin_service.py` route-inventory updated for the 3 new routes.
- Browser build (web): `tsc --noEmit` 0 err; `next lint` 0 new (1 pre-existing warning in `deploy-wizard.tsx`); `next build` with `.env.production` swap clean (BUILD_ID `QiL_h7JpOgCdxeeLs4DV6`).
- Reports: this report + Files Changed + Regression + Security (see `reports/`).

Prod deploy + browser/mobile re-smoke pending after user approval gate.