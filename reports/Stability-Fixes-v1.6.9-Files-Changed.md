# Files Changed — v1.6.9 Stability Sprint

**Date:** 07 Aug 2026 · **Base:** `d0367ca` (v1.6.8)

Legend: **+/-** = additive / modified · **D** = deleted · **N** = new file

---

## Backend (API)

| File | Change | Defect |
|------|--------|--------|
| `apps/api/market/option_chain.py` | **+** module-level `SUPPORTED_INDICES`, `_INDEX_ALIASES`, `normalize_index_symbol()`; **+** `_generate_simulated_chain()` (deterministic per-index mock chain: base prices, strikes, next-Thursday+4w expiry, approx greeks, CE/PE ltp/bid/ask/volume/oi/iv, `mock: true`); **+** `normalize_index_symbol` + simulated-fallback wiring in `get_option_chain()` / `get_expiries()`; **FIX** dead-code Fyers parsing block (was nested under the error condition — dedented to success path so real chains parse) | P1-1 |
| `apps/api/routes/v1_marketdata.py` | **+** `normalize_index_symbol` before the `fyers_map` lookup; **D** dead `_generate_mock_option_chain` (buggy loop/indent) — delegated to the engine's shared simulator; engine `option_chain_engine._generate_simulated_chain()` fallback instead | P1-1 |
| `supabase/migrations/20260807_01900_trades_schema_align.sql` | **N** idempotent `ALTER TABLE trades ADD COLUMN IF NOT EXISTS` (order_id, strategy_id, broker, exchange, side, price, value, trade_time, is_paper, created_at) + `idx_trades_user_created` | P1-2 |
| `apps/api/ai/journal.py` | **+** orders-first `_get_recent_trades` (FILLED orders with full schema, normalized row shape) with `trades`-table fallback; both queries try/except → `[]` (journal never 500s on schema drift) | P1-2 |
| `apps/api/routes/v1_ai.py` | **+** graceful `get_journal` (try/except → `{"analysis": "AI journal is temporarily unavailable.", "stats": {}}`) | P1-2 |
| `apps/api/main.py` | **+** `_cors_headers_for(request)` (mirrors CORSMiddleware origin echo + `Vary: Origin` + credentials); **+** global `@app.exception_handler(Exception)` now passes CORS headers (ServerErrorMiddleware is outside CORSMiddleware — the root cause of CORS-less 500s) | P1-2 |
| `apps/api/core/response.py` | **+** `headers:` param on `api_response()` / `error_response()` | P1-2 |
| `apps/api/routes/v1_admin.py` | **+** `GET /admin/users/with-brokers`, `GET|POST /admin/ip-whitelist`, `DELETE /admin/ip-whitelist/{ip_id}` (all `require_super_admin`; reuse existing `AdminService` methods incl. cache invalidation + audit) | P1-3 |
| `apps/api/routes/v1_auth.py` | **+** `_client_ip`, `_throttle_login`, `_record_login_failure`, `_clear_login_failures`; **+** signin wiring: failed → progressive delay + lockout (429 after 5 fails / 5 min), success → counter reset; `auth_failed` / `login_locked` audit entries | P2-1 |

## Backend (tests)

| File | Change | Defect |
|------|--------|--------|
| `apps/api/tests/test_option_chain_normalize.py` | **N** 7 tests: normalization, aliases, passthrough, simulated-chain shape for all 4 index symbols, unsupported → `None`, ATM strike window, PCR/max-pain | P1-1 |
| `apps/api/tests/test_journal_resilience.py` | **N** 5 tests: orders-first, trades fallback, orders-error→trades, schema-drift → `[]`, graceful analysis | P1-2 |
| `apps/api/tests/test_auth_throttle.py` | **N** 4 tests: forwarded-IP extraction, socket fallback, success clears counter, progressive delay → 429 lockout | P2-1 |
| `apps/api/tests/test_admin_service.py` | **+** route-inventory test updated for the 3 new admin routes | P1-3 |

## Frontend (web)

| File | Change | Defect |
|------|--------|--------|
| `apps/web/lib/api.ts` | **+** `admin.users.withBrokers()`; **+** `admin.ipWhitelist.{list,add,remove}`; **+** `executeTrade` result typing widened (`success`/`message` optional) | P1-3 |
| `apps/web/app/dashboard/trade-router-tab.tsx` | **+** import `api` client; **R** relative fetches → `api.admin.users.withBrokers()`, `api.get('/market/option-chain…')`, `api.get('/marketdata/instruments…')`, `api.admin.executeTrade()`; **D** dead `getCSRF()` | P1-3 |
| `apps/web/app/dashboard/ip-whitelist-tab.tsx` | **+** import `api` client; **R** relative fetches → `api.admin.ipWhitelist.{list,add,remove}` | P1-3 |
| `apps/web/app/dashboard/admin-content.tsx` | **+** TradesTab option-chain/instruments/execute-trade → `api` client; **D** dead `getCSRF()` | P1-3 |

**No files deleted from the codebase** (dead helper functions removed within edited files only).