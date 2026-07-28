# TradeMetrix Terminal — AGENTS.md

## Project
Automated trading terminal. FastAPI backend + Next.js frontend. Multi-broker support. Supabase DB, Redis cache/rate-limiter, Prometheus metrics, Telegram alerts.

## Architecture
- `apps/api/` — FastAPI backend (Python 3.12)
- `apps/web/` — Next.js frontend
- `infra/` — Docker Compose deployment configs
- `supabase/` — DB migrations

## Session: 2026-07-27 — Product Acceptance Testing (PAT)

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
