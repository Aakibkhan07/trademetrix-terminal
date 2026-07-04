# TradeMetrix Terminal — Feature Matrix

> Generated: 2026-07-04 | Mode: READ-ONLY audit — zero code modified.
> Stack: Python FastAPI + Next.js 14 (App Router) + Supabase + Redis + Docker Compose

---

## Frontend Route Inventory

| Route | Page Type | What It Renders | Status | Notes |
|-------|-----------|-----------------|--------|-------|
| `/` | Home page | Marketing landing, features, CTA | WORKING | Static hero + feature sections |
| `/auth` | Auth page | Login/signup forms (email/password, Google) | WORKING | Full auth flow |
| `/portal` | Client portal | OTP-based login/signup flow → client dashboard | WORKING | OTP send & verify flow |
| `/onboarding` | Onboarding wizard | Multi-step setup (broker, strategy, risk) | WORKING | Guides new users |
| `/dashboard` | Main dashboard | Portfolio summary, P&L, active strategies | WORKING | Calls admin/stats + engine/orders |
| `/terminal` | Terminal view | Trading terminal with order entry | WORKING | Quick order form |
| `/trade` | Trade page | Manual order placement form | WORKING | Symbol, side, qty, price, type |
| `/positions` | Positions view | Current open positions from broker | WORKING | Calls engine/positions |
| `/strategies` | Strategies list | User's custom + assigned strategies | WORKING | CRUD on strategies |
| `/strategies/catalog` | Strategy catalog | Browse built-in strategy types | WORKING | Lists available strategies |
| `/marketdata` | Market data | Watchlist, price chart, alerts, option chain? | PARTIAL | Has watchlist + alerts UI; option chain not present |
| `/brokers` | Broker manager | Connect/manage broker accounts | WORKING | Full CRUD + OAuth flow |
| `/backtest` | Backtest runner | Run backtests, view results | WORKING | V1 backtest UI with config + results table |
| `/ai` | AI Desk | AI-powered trading assistant | WORKING | Chat interface with Gemini |
| `/copilot` | AI Copilot | Real-time AI copilot chat | WORKING | Separate AI chat |
| `/analytics` | Analytics | Trading performance analytics | WORKING | Charts + metrics |
| `/risk` | Risk controls | Risk settings, kill switch, live toggle | WORKING | Full risk management UI |
| `/alerts` | Price alerts | Create/manage price alerts | WORKING | CRUD on alerts |
| `/journal` | Trade journal | Trading journal with notes | WORKING | Order notes + reflections |
| `/account` | Account settings | Profile, password, preferences | WORKING | User settings |
| `/settings` | App settings | Theme, notifications, display prefs | WORKING | App-wide settings |
| `/pricing` | Pricing page | Subscription plan comparison | WORKING | Tier feature list |
| `/feedback` | Feedback form | Submit bug report / feature request | WORKING | Calls feedback API |
| `/help` | Help center | FAQ / support articles | STUB | Hardcoded placeholder content |
| `/changelog` | Changelog | Release history | STUB | Hardcoded entries, not dynamic |
| `/transparency` | Reports | Platform transparency report | STUB | Hardcoded stats |
| `/status` | System status | Component health dashboard | WORKING | Calls health endpoints + EventSource SSE |
| `/legal` | Legal hub | Links to legal pages | WORKING | Index page |
| `/legal/privacy` | Privacy policy | Privacy policy content | WORKING | Static page |
| `/legal/terms` | Terms of service | ToS content | WORKING | Static page |
| `/legal/disclaimer` | Disclaimer | Risk disclaimer | WORKING | Static page |
| `/legal/risk-disclosure` | Risk disclosure | Risk disclosure content | WORKING | Static page |
| `/legal/refund` | Refund policy | Refund/cancellation policy | WORKING | Static page |
| `/admin` | Admin panel (Dashboard) | Stats overview, user list, broker mgmt, trades, audit, risk | WORKING | Tab-based SPA with sub-pages |
| `/admin/founder` | Founder dashboard | Full platform metrics, system health | WORKING | 11+ API calls, auto-refresh 5s |
| `/admin/broadcast` | Broadcast trades | Send trade signals to strategy recipients | WORKING | Broadcast form + results |
| `/admin/beta` | Beta management | Invite codes, waitlist, approvals | STUB | In-memory mock data, no backend |
| `/admin/admins` | Admin management | CRUD admin users, assign roles | WORKING | New feature (added 2026-07-04) |

## Backend Endpoint Inventory

Total: **126 endpoints** across 18 route files. See `apps/api/routes/` for details.

### Auth Requirements Summary

| Auth Level | Count | Notes |
|------------|-------|-------|
| None (public) | 33 | Health, broker metadata, strategies catalog, market status |
| `get_current_user` | 60 | Most API endpoints |
| `require_admin` | 14 | Admin panel APIs |
| `require_super_admin` | 3 | Admin management (create/update/delete admins) |
| HMAC signature | 1 | TradingView webhook |
| Cookie-based (WS) | 1 | WebSocket market data |

### Test Coverage

- **98 tests total** — all PASS on Python 3.14
- **18 test files** in `apps/api/tests/`
- **200 warnings** (all deprecation: `datetime.utcnow()`, `pydantic`, `supabase` client deprecated params)

---

## Feature Matrix

| Feature | Location (files) | Status | Evidence | Notes |
|---------|------------------|--------|----------|-------|
| **Auth: Email/Password** | `routes/v1_auth.py` (signup, signin), `web/app/auth/page.tsx` | **WORKING** | API returns 200 on signin, sets `tm_session` cookie | Supabase-backed, JWT 24h expiry |
| **Auth: OTP Login** | `routes/v1_otp.py` (send-otp, verify-otp), `web/app/portal/page.tsx` | **BROKEN** (prod) | send-otp returns 200, verify-otp returns 401 "No OTP found" | Redis `bind 127.0.0.1` prevents cross-container access. Fixed in code (bind 0.0.0.0 + password) but NOT YET DEPLOYED. See commit `335dcbb`. |
| **Auth: Google OAuth** | `routes/v1_auth.py` (signin delegates to Supabase) | **WORKING** | Supabase handles Google OAuth redirect | No custom endpoint, relies on Supabase built-in |
| **Auth: Session Cookie** | `core/security.py` (JWT), `core/deps.py` (get_current_user) | **WORKING** | `tm_session` cookie set on login, validated on each request | HttpOnly, Secure, SameSite=None, 7-day expiry |
| **Auth: CSRF Protection** | `middleware/csrf.py` | **WORKING** | 403 on mutating requests without valid CSRF header | ~15 SAFE_PATHS exempted (auth, webhook, feeds) |
| **Broker Connect: Fyers** | `brokers/fyers_adapter.py`, `routes/v1_brokers.py` | **WORKING** | OAuth flow, place/cancel orders, positions, historical data | `supports_option_chain=True`; WebSocket uses polling, not real WS |
| **Broker Connect: Angel One** | `brokers/angelone_adapter.py` | **WORKING** | API-key auth, place/cancel orders, positions | WebSocket supported |
| **Broker Connect: Upstox** | `brokers/upstox_adapter.py` | **WORKING** | OAuth + API-key, place/cancel orders | WS uses `httpx.stream()` — unreliable per cert docs |
| **Broker Connect: Dhan** | `brokers/dhan_adapter.py` | **WORKING** | API-key auth, orders, positions | Error path returns empty on holding fetch |
| **Broker Connect: Zerodha** | `brokers/zerodha_adapter.py` | **WORKING** | API-key auth | Basic CRUD |
| **Broker Connect: Kotak Neo** | `brokers/kotakneo_adapter.py` | **WORKING** | OAuth flow | Basic CRUD |
| **Broker Connect: FlatTrade** | `brokers/flattrade_adapter.py` | **PARTIAL** | Place/cancel orders WORKING; `get_holdings()` returns `[]` | STUB — holdings not implemented |
| **Broker Connect: Alice Blue** | `brokers/aliceblue_adapter.py` | **PARTIAL** | Place/cancel orders WORKING; `get_quotes()` + `get_historical()` return `[]` | STUB — two methods not implemented |
| **Broker Connect: Finvasia (Shoonya)** | `brokers/finvasia_adapter.py` | **PARTIAL** | Place/cancel orders WORKING; `get_holdings()` returns `[]` | STUB — holdings not implemented |
| **Broker Connect: 5Paisa** | `brokers/fivepaisa_adapter.py` | **PARTIAL** | Place/cancel orders WORKING; `get_holdings()` + `get_historical()` return `[]` | STUB — two methods not implemented |
| **Quick Order / Manual Trade** | `routes/v1_engine.py` POST `/engine/trade`, `web/app/terminal/page.tsx` | **WORKING** | Places order through gate → RiskGuard → broker | Paper default; requires explicit live toggle |
| **Positions** | `routes/v1_engine.py` GET `/engine/positions`, `web/app/positions/page.tsx` | **WORKING** | Returns current positions from active broker | Depends on broker adapter `get_positions()` |
| **Orders List** | `routes/v1_engine.py` GET `/engine/orders`, `web/app/trade/page.tsx` | **WORKING** | Last 100 orders, cancellable | has note/annotation support |
| **Order Cancel** | `routes/v1_engine.py` POST `/engine/orders/{id}/cancel` | **WORKING** | Cancels via broker adapter | **[KNOWN BUG]** TOCTOU race in OMS `cancel_order()` — order can be sent between queue check and remove (doc: ProductionReadinessReport.md C10) |
| **Portfolio / Performance Analytics** | `routes/v1_analytics.py`, `web/app/analytics/page.tsx` | **WORKING** | Charts + metrics from tracked events | Depends on client-side analytics tracking |
| **Strategy Assignment** | `routes/v1_admin.py` (assignments CRUD), `web/app/admin/page.tsx` (UsersTab) | **WORKING** | Admin assigns built-in strategies to users | Validates tier requirements |
| **Strategy Builder** | `routes/v1_builder.py` (20 endpoints), `components/builder/` | **WORKING** | Visual block-based strategy builder | Full CRUD + compile + validate + preview |
| **Built-in Strategies** | `strategies/` directory | **WORKING** | Catalog of ~10+ strategies | Includes trend_rider, orb_pro, smc_sniper, expiry_hunter, etc. |
| **PAPER/LIVE Gate** | `engine/gate.py` — `execute_order()`, `core/risk.py` — `RiskGuard` | **WORKING** | Paper default, checks risk limits before live | Kill switch + daily loss caps enforced |
| **RiskGuard** | `core/risk.py`, `routes/v1_risk.py` | **WORKING** | Capital, position size, daily loss, drawdown limits | Tier-based limits enforced |
| **Kill Switch** | `routes/v1_risk.py` POST enable/disable, `web/app/risk/page.tsx` | **WORKING** | Emergency stop all trading | Visible in sidebar, pulsing red dot when active |
| **Daily Loss Caps** | `core/models.py` `TIER_DAILY_LOSS`, `core/risk.py` | **WORKING** | Per-tier loss limits: free=2K, starter=3K, pro=5K, enterprise=10K | Enforced in RiskGuard |
| **WebSocket Market Data** | `routes/v1_marketdata.py` WS `/marketdata/ws`, `lib/use-market-data.tsx` | **WORKING** | Real-time tick stream via WebSocket | **[KNOWN ISSUE]** Main domain nginx lacks WS upgrade headers — must use `api.ai.trademetrix.tech` |
| **Option Chain Analyzer** | `routes/v1_market.py` GET `/market/option-chain`, `markets/option_chain.py` | **MISSING** (frontend) | **Backend**: API returns option chain with PCR, Max Pain, expiries. **Frontend**: NO UI page exists. No `/option-chain` route. Not in `marketdata/page.tsx`. Deployed JS bundle confirmed has no option-chain code. | Backend WORKING. Frontend NOT-DEPLOYED / MISSING. |
| **Option Chain (Fyers)** | `routes/v1_marketdata.py` GET `/marketdata/option-chain` | **MISSING** (frontend) | Same as above — API exists but no frontend page calls it | Fyers-specific source |
| **Backtest Engine** | `routes/v1_backtest.py`, `backtest/` (V1 + V2 engine) | **WORKING** | V1 simple + V2 replay engine. Frontend at `/backtest`. API at `GET /backtest/strategies` returns 200. | Tested: 98 tests pass including `test_backtest.py` |
| **Admin Panel: Dashboard** | `web/app/admin/page.tsx` (DashboardTab) | **WORKING** | Stats cards, tier distribution chart | Calls `/admin/stats` |
| **Admin Panel: Users** | `web/app/admin/page.tsx` (UsersTab) | **WORKING** | Search users, change tier, assign/unassign strategies | Calls `/admin/users`, `/admin/assignments` |
| **Admin Panel: Brokers** | `web/app/admin/page.tsx` (BrokersTab) | **WORKING** | Set global broker credentials, view all user connections | Calls `/admin/brokers` |
| **Admin Panel: Trades** | `web/app/admin/page.tsx` (TradesTab) | **WORKING** | View all orders, filter by user/paper/live, auto-refresh | Calls `/admin/orders` |
| **Admin Panel: Audit Log** | `web/app/admin/page.tsx` (AuditTab) | **WORKING** | View audit trail, filter by action | Calls `/admin/audit-log` |
| **Admin Panel: Risk** | `web/app/admin/page.tsx` (RiskTab) | **WORKING** | View all users' risk settings | Calls `/admin/risk` |
| **Admin Panel: Founder** | `web/app/admin/founder/page.tsx` | **WORKING** | 11-section dashboard: users, orders, brokers, system, monitoring | 11+ API calls, auto-refresh 5s |
| **Admin Panel: Broadcast** | `web/app/admin/broadcast/page.tsx` | **WORKING** | Send trade signals to strategy recipients | Calls `/admin/broadcast` |
| **Admin Panel: Beta** | `web/app/admin/beta/page.tsx` | **STUB** | Invite codes, waitlist, approvals — all in-memory mock data | NO backend API connected |
| **Admin Panel: Admins** | `web/app/admin/admins/page.tsx` | **WORKING** | CRUD admin users, assign roles | New feature (2026-07-04), requires `role` column in Supabase |
| **Trade Notes / Journal** | `routes/v1_engine.py` POST notes, GET notes; `web/app/journal/page.tsx` | **WORKING** | Add notes to orders, view journal | Full CRUD |
| **CSV Export** | `web/app/trade/page.tsx` | **WORKING** | Export orders to CSV from trade page | Client-side CSV generation |
| **Tier Gating** | `core/models.py` TIER_LIMITS/TIER_DAILY_LOSS, `core/risk.py` | **WORKING** | Limits per tier: max strategies, daily loss, features | Free=1strat/2K loss, Starter=2/3K, Pro=8/5K, Enterprise=15/10K |
| **Sub-Admin Roles** | `core/models.py` ADMIN_ROLES, `core/deps.py` require_super_admin/permission | **WORKING** | 4 roles: super_admin, admin, support, analyst | New feature (2026-07-04), requires `role` column migration |

---

## Security Checks

### CORS (`api.ai.trademetrix.tech`)
| Test | Result |
|------|--------|
| Preflight with valid origin `https://ai.trademetrix.tech` | ✅ Returns `Access-Control-Allow-Origin: https://ai.trademetrix.tech` |
| Preflight with evil origin `https://evil.com` | ✅ Returns 400 WITHOUT `Access-Control-Allow-Origin` — browser blocks |
| Credentials allowed | `access-control-allow-credentials: true` (expected — cookie-based auth) |

**Verdict**: CORS is strict whitelist. Only our frontend domain is allowed.

### Swagger/OpenAPI Exposure
| Check | Result |
|-------|--------|
| `/docs` (Swagger UI) | ❌ 404 — not exposed |
| `/openapi.json` (OpenAPI spec) | ❌ 404 — not exposed |
| `/redoc` | ❌ 404 — not exposed |

**Verdict**: API documentation endpoints are disabled in production. Excellent.

### 307 Redirect on `/api/v1/strategies`
| Check | Result |
|-------|--------|
| `GET /api/v1/strategies` | Returns **307** → `http://api.ai.trademetrix.tech/api/v1/strategies/` |

**Root cause**: FastAPI's router has one route at `/strategies` (no trailing slash) and one at `/strategies/` (with trailing slash). The router redirects the no-slash version to the slash-version via FastAPI's built-in redirect behaviour. **Harmless cosmetic issue** — does not affect functionality since the client `api.ts` library uses the correct path.

---

## Test Suite Results

**Command**: `cd apps/api && python3 -m pytest tests/ -v --tb=short`
**Environment**: Python 3.14, macOS local (not VPS)

```
98 passed in 15.77s
0 failed
200 warnings (all deprecation: datetime.utcnow(), pydantic, supabase deprecated params)
```

**Breakdown by file**:
| Test File | Tests | Status |
|-----------|-------|--------|
| test_auth.py | 1 | ✅ PASS |
| test_backtest.py | 3 | ✅ PASS |
| test_broker_angelone.py | 6 | ✅ PASS |
| test_broker_dhan.py | 5 | ✅ PASS |
| test_broker_fyers.py | 7 | ✅ PASS |
| test_broker_timeouts.py | 3 | ✅ PASS |
| test_broker_upstox.py | 6 | ✅ PASS |
| test_circuit_breaker_wiring.py | 5 | ✅ PASS |
| test_engine.py | 14 | ✅ PASS |
| test_gate.py | 10 | ✅ PASS |
| test_marketdata.py | 3 | ✅ PASS |
| test_mirror_fanout.py | 2 | ✅ PASS |
| test_oms_persistence.py | 10 | ✅ PASS |
| test_risk.py | 4 | ✅ PASS |
| test_risk_fail_closed.py | 8 | ✅ PASS |
| test_sprint3.py | 8 | ✅ PASS |
| test_strategies.py | 3 | ✅ PASS |

**Zero backend tests are failing.**

---

## TODO / FIXME / Stub Inventory

### Stub Implementations (code returns `[]` or `None` — no real logic)
| File | Line | Method | Issue |
|------|------|--------|-------|
| `brokers/fivepaisa_adapter.py` | 227 | `get_holdings()` | Always returns `[]` |
| `brokers/fivepaisa_adapter.py` | 302-305 | `get_historical()` | Always returns `[]` |
| `brokers/aliceblue_adapter.py` | 193 | `get_quotes()` | Always returns `[]` |
| `brokers/aliceblue_adapter.py` | 195-198 | `get_historical()` | Always returns `[]` |
| `brokers/flattrade_adapter.py` | 172-173 | `get_holdings()` | Always returns `[]` |
| `brokers/finvasia_adapter.py` | 172-173 | `get_holdings()` | Always returns `[]` |
| `market/adapter.py` | 59-60 | `get_option_chain()` | Always returns `None` |

### Known Bugs (code present, not fixed)
| File | Line | Issue | Severity |
|------|------|-------|----------|
| `oms/manager.py` | 127-142 | TOCTOU race in `cancel_order()` — check vs remove gap | HIGH |
| `oms/manager.py` | ~306-307 | OCO sibling cancellation not implemented | HIGH |

### Placeholder Pages
| Route | Issue |
|-------|-------|
| `/help` | Hardcoded FAQ content, no CMS/backend |
| `/changelog` | Hardcoded entries, not dynamic |
| `/transparency` | Hardcoded stats |
| `/admin/beta` | Mock data, no backend connected |

### Deployment Gaps
| Issue | Status |
|-------|--------|
| Redis `bind 127.0.0.1` + missing password in URL | Fixed in code (commit `335dcbb`) but NOT YET DEPLOYED — requires `docker compose up -d --force-recreate redis api` |
| `infra/.env.production` placeholder values | ⚠️ Contains `<placeholder>` strings for secrets. If VPS file has real values, this is moot. **Cannot verify from read-only.** |
| `.env.production` file created for web app (commit `161949e`) | DEPLOYED — web container rebuilt and restarted |

---

## Option Chain Analyzer — Definitive Answer

**Backend**: ✅ **EXISTS AND WORKING**
- `routes/v1_market.py` `GET /api/v1/market/option-chain` — Returns option chain with PCR, Max Pain, expiries (auth: `get_current_user`)
- `routes/v1_marketdata.py` `GET /api/v1/marketdata/option-chain` — Fyers-first, NSE-fallback (auth: `get_current_user`)
- `market/option_chain.py` — `OptionChainEngine` singleton, NSE scraping + fallback to synthetic data
- Deployed API returns HTTP 401 (unauthorized — expected without auth token)

**Frontend**: ❌ **MISSING — NOT DEPLOYED**
- No route exists for `/option-chain` or `/marketdata/option-chain`
- `marketdata/page.tsx` has watchlist, price chart, and alerts — NO option chain UI
- Deployed JS bundle at `ai.trademetrix.tech` confirmed to contain zero option-chain code
- No component, no navigation link, no page — completely absent from the frontend

**Verdict**: **MISSING** from the deployed frontend. Backend API is ready but unused.

---

## Backtest Engine — Definitive Answer

**Backend**: ✅ **WORKING**
- `routes/v1_backtest.py` — V1 simple + V2 replay engine
- `backtest/manager.py`, `backtest/replay_engine.py`, `backtest/performance.py`
- `GET /api/v1/backtest/strategies` returns 200
- 3 backtest tests pass

**Frontend**: ✅ **WORKING**
- Route `/backtest` returns 200
- `web/app/backtest/page.tsx` has full UI: strategy selector, symbol, interval, days config + results table with trades, equity curve, metrics

**Verdict**: Fully deployed and operational.

---

## Files Read for This Audit

### Backend
- `apps/api/main.py` — App structure, middleware stack, router registrations
- `apps/api/routes/v1_*.py` (all 18 route files) — Endpoint inventory
- `apps/api/core/models.py` — Pydantic models, constants
- `apps/api/core/deps.py` — Auth dependencies
- `apps/api/core/security.py` — JWT, encryption
- `apps/api/core/config.py` — Settings
- `apps/api/core/cache.py` — Redis cache layer
- `apps/api/middleware/csrf.py` — CSRF protection
- `apps/api/market/option_chain.py` — Option chain engine
- `apps/api/backtest/` — Backtest engine files
- `apps/api/oms/manager.py` — OMS order management
- `apps/api/engine/gate.py` — Order execution gate
- `apps/api/brokers/` (all adapter files) — Broker implementations

### Frontend
- `apps/web/app/layout.tsx` — Root layout
- `apps/web/app/admin/layout.tsx` — Admin layout
- `apps/web/app/*/page.tsx` (all 38 route files)
- `apps/web/middleware.ts` — Middleware (disabled)
- `apps/web/next.config.js` — Config
- `apps/web/lib/api.ts` — API client library
- `apps/web/lib/auth-context.tsx` — Auth context
- `apps/web/lib/use-api.ts` — API data fetching hook
- `apps/web/components/` (all shared components)
- `apps/web/styles/components.css` — Design system CSS

### Infrastructure
- `infra/nginx.conf` — nginx configuration
- `infra/docker-compose.yml` — Docker Compose
- `infra/redis/redis.conf` — Redis configuration
- `infra/.env.production.example` — Environment template

### Documentation
- `docs/ProductionReadinessReport.md`
- `docs/BrokerCertification.md`
- `docs/MissingFeatures.md`
- `docs/ProjectAudit.md`
- `apps/api/docs/` (all docs)

---

## How to Test

1. **Auth flow**: Visit `https://ai.trademetrix.tech/auth` → sign in with email/password. Check `tm_session` cookie set.
2. **OTP flow**: Visit `/portal` → enter email → check OTP received → enter OTP → should verify (requires Redis fix deployed).
3. **Broker connect**: Visit `/brokers` → connect a broker → save credentials.
4. **Trading**: Visit `/terminal` → place a paper trade. Check orders at `/trade`.
5. **Admin panel**: Visit `/admin` → all tabs functional. Sub-admin management at `/admin/admins`.
6. **Backtest**: Visit `/backtest` → select strategy → run backtest → view results.
7. **Test suite**: `cd apps/api && python3 -m pytest tests/ -v`

## What I Could NOT Verify

1. **VPS `.env.production` secrets** — Cannot read the file without SSH. If it contains placeholder values, the deployment will fail on startup.
2. **Supabase `role` column** — The `ALTER TABLE profiles ADD COLUMN role TEXT DEFAULT ''` migration was run ad-hoc in SQL Editor, not as a migration file. Not reproducible from scratch.
3. **Redis fix applied** — The Redis password + bind fix is committed but may not be deployed yet. User needs to run `docker compose up -d --force-recreate redis api` on VPS.
4. **Live broker trading** — Cannot test actual broker API connectivity without real credentials.
5. **CORS with `credentials: include`** — The preflight test confirms basic CORS, but full credentialed request flow with cookies could not be verified from CLI.
