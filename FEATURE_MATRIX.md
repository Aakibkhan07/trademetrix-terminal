# TradeMetrix Terminal — Feature Matrix

> Generated: 2026-07-04 | Automated audit + manual verification.
> Stack: Python FastAPI + Next.js 14 (App Router) + Supabase + Redis + Docker Compose / Caddy

---

## Frontend Route Inventory

| Route | Page Type | Status | Notes |
|-------|-----------|--------|-------|
| `/` | Home page | WORKING | Static hero + feature sections |
| `/auth` | Auth page | WORKING | Login/signup forms |
| `/portal` | Client portal | WORKING | OTP send & verify flow |
| `/onboarding` | Onboarding wizard | WORKING | Multi-step setup wizard |
| `/dashboard` | Main dashboard | WORKING | Portfolio summary, P&L, positions. Loading+error states added. SIMULATED badge when feed offline. |
| `/terminal` | Terminal view | WORKING | Quick order form. Sidebar fixed-widths relaxed for 380px. |
| `/trade` | Trade page | WORKING | Manual order placement with option chain |
| `/positions` | Positions view | WORKING | Current open positions |
| `/strategies` | Strategies list | WORKING | Skeleton loading + error state + retry added |
| `/strategies/catalog` | Strategy catalog | WORKING | Browse built-in strategies |
| `/marketdata` | Market data | WORKING | Watchlist, price chart, alerts |
| `/brokers` | Broker manager | WORKING | Full CRUD + OAuth |
| `/backtest` | Backtest runner | WORKING | Config + results table |
| `/ai` | AI Desk | WORKING | Gemini chat |
| `/copilot` | AI Copilot | WORKING | Separate AI chat |
| `/analytics` | Analytics | WORKING | Charts + metrics |
| `/risk` | Risk controls | WORKING | Kill switch, limits |
| `/alerts` | Price alerts | WORKING | CRUD on alerts |
| `/journal` | Trade journal | WORKING | Order notes + reflections |
| `/account` | Account settings | WORKING | Profile, password, preferences |
| `/settings` | App settings | WORKING | Theme, notifications |
| `/pricing` | Pricing page | WORKING | Subscription tiers |
| `/feedback` | Feedback form | WORKING | Calls feedback API |
| `/help` | Help center | STUB | Hardcoded placeholder |
| `/changelog` | Changelog | STUB | Hardcoded entries |
| `/transparency` | Reports | WORKING | Platform transparency stats |
| `/status` | System status | WORKING | Health dashboard |
| `/terminal/builder` | Strategy Builder | WORKING | 2-leg strategy create/edit, leg controls (SL/Target/Trailing SL/Re-entry), payoff preview, margin estimate, **activity feed** per strategy card |
| `/terminal/option-chain` | Option Chain Analyzer | WORKING | CE|STRIKE|PE chain, PCR zone, Max Pain, CE resistance/PE support, SIMULATED badge, 10s auto-poll, sticky STRIKE, OI change tracking |
| Legal pages (`/legal/*`) | Legal hub | WORKING | Static pages |
| `/admin` | Admin panel | WORKING | Dashboard, Users, Brokers, Trades, Audit, Risk tabs |
| `/admin/founder` | Founder dashboard | WORKING | 11-section metrics, auto-refresh |
| `/admin/broadcast` | Broadcast trades | WORKING | Send signals |
| `/admin/beta` | Beta management | STUB | Mock data, no backend |
| `/admin/admins` | Admin management | WORKING | CRUD admin users |

All 30+ routes return **HTTP 200** on production (`ai.trademetrix.tech`).

---

## Backend Endpoint Inventory

**Total: 130+ endpoints** across 20 route files.

### Key Endpoint Groups (all prefixed `/api/v1`)

| Group | Route File | Key Endpoints | Auth |
|-------|-----------|---------------|------|
| Health | `v1_health.py` | `/health`, `/health/live`, `/health/ready`, `/version` | None |
| Auth | `v1_auth.py` | `/auth/signup`, `/auth/signin`, `/auth/signout`, `/auth/me`, `/auth/csrf` | None (signup/signin), cookie (me) |
| OTP | `v1_otp.py` | `/auth/send-otp`, `/auth/verify-otp`, `/auth/register-with-otp` | None + CSRF |
| Brokers | `v1_brokers.py` | `/brokers/list`, `/brokers/activate`, `/brokers/fyers/callback` | Cookie (most), None (OAuth callback) |
| Engine | `v1_engine.py` | `/engine/trade`, `/engine/positions`, `/engine/orders`, `/engine/funds` | Cookie |
| Market | `v1_market.py` | `/market/option-chain` — returns chain + PCR + Max Pain + `is_simulated` | Cookie |
| Market Data | `v1_marketdata.py` | `/marketdata/ws` (WebSocket), `/marketdata/historical`, `/marketdata/symbols` | Cookie + WS cookie |
| Strategies | `v1_strategies.py` | `/strategies/` — CRUD built-in strategy assignments | Cookie |
| User Strategies | `v1_user_strategies.py` | `/user-strategies/` — CRUD user-created strategies; **`/{id}/activity`** — activity feed | Cookie |
| Backtest | `v1_backtest.py` | `/backtests/` — list/create/get backtest runs | Cookie (POST requires pro tier) |
| Risk | `v1_risk.py` | `/risk/settings`, `/risk/kill-switch` | Cookie |
| Margin Estimate | `v1_margin_estimate.py` | `/margin-estimate/` — SPAN + Exposure | Cookie |
| Admin | `v1_admin.py` | `/admin/users`, `/admin/orders`, `/admin/audit-log`, `/admin/risk` | Cookie + admin role |
| Events (SSE) | `v1_events.py` | `/events/stream` — Server-Sent Events | Cookie |

### Auth Requirements

| Auth Level | Count | Notes |
|------------|-------|-------|
| None (public) | 33 | Health, broker metadata, market status |
| `get_current_user` | 62 | Most endpoints |
| `require_admin` / `require_super_admin` | 17 | Admin APIs |
| HMAC + CSRF | 2 | TradingView webhook, mutating endpoints |

---

## Feature Matrix

| Feature | Status | Evidence | Notes |
|---------|--------|----------|-------|
| **Auth: Email/Password** | WORKING | Signin sets `tm_session` cookie | Supabase-backed, JWT 24h |
| **Auth: OTP Login** | WORKING | send-otp → verify-otp flow | Redis-backed, SHA256 hashed |
| **Auth: Session Cookie** | WORKING | `tm_session` HttpOnly Secure SameSite=None 7d | Core security |
| **Auth: CSRF Protection** | WORKING | 403 on mutating requests without CSRF | ~15 SAFE_PATHS exempted |
| **Broker Connect (10 brokers)** | WORKING | Fyers, Angel One, Upstox, Dhan, Zerodha, Kotak Neo | FlatTrade/AliceBlue/Finvasia/5Paisa have stub holdings |
| **PAPER/LIVE Gate** | WORKING | `order.is_paper` → broker "paper"; `risk_settings.is_live` → real broker | PAPER-only enforced at execute_order entry |
| **Quick Order / Manual Trade** | WORKING | `/engine/trade` → RiskGuard → broker | Paper default |
| **Positions** | WORKING | `/engine/positions` | Broker adapter dependent |
| **Order List & Cancel** | WORKING | `/engine/orders` GET + POST cancel | TOCTOU race known |
| **Strategy Builder** | WORKING | Visual block builder + **user strategy builder** with leg controls | Full CRUD + re-entry + trailing SL |
| **User Strategies (Builder)** | WORKING | `user_strategies` CRUD, deploy PAPER | Trailing SL, re-entry, activity feed |
| **Strategy Deploy** | WORKING | POST `/user-strategies/{id}/deploy` — PAPER only; LIVE returns 403 | `is_paper=True` forced |
| **Strategy Activity Feed** | WORKING | GET `/user-strategies/{id}/activity` — queries audit_log | New endpoint added |
| **Backtest Engine** | WORKING | V1 simple + V2 replay at `/backtests/` | Route prefix fixed to plural |
| **Backtest V1 Routes** | WORKING | `GET/POST /backtests/`, `GET /backtests/{run_id}` | Tier-gated (pro) |
| **Margin Estimate** | WORKING | POST `/margin-estimate/` — SPAN + Exposure | Broker-dependent |
| **Option Chain Analyzer** | WORKING | **Backend + Frontend** deployed at `/terminal/option-chain` | Full chain, PCR, Max Pain, SIMULATED badge, 10s poll |
| **WebSocket Market Data** | WORKING | `/marketdata/ws` real-time ticks | Must use `api.ai.trademetrix.tech` |
| **RiskGuard** | WORKING | Capital, position size, daily loss, drawdown limits | Tier-based |
| **Kill Switch** | WORKING | Emergency stop, visible in sidebar pulsing red | Full UI + API |
| **Daily Loss Caps** | WORKING | Free=2K, Starter=3K, Pro=5K, Enterprise=10K | Enforced in RiskGuard |
| **AI Desk (Gemini)** | WORKING | Chat with Gemini | Google GenAI SDK |
| **Portfolio Analytics** | WORKING | Charts + metrics at `/analytics` | Client-side tracking |
| **Admin Panel** | WORKING | Dashboard, Users, Brokers, Trades, Audit, Risk, Founder, Broadcast, Admins | Full CRUD |
| **Sub-Admin Roles** | WORKING | super_admin, admin, support, analyst | `role` column in profiles |
| **SIMULATED DATA Badges** | WORKING | Present on: Dashboard, Terminal, Trade, Option Chain, Payoff Preview | Added to Dashboard |
| **Loading States** | WORKING | All terminal pages: terminal, builder, trade, strategies, option-chain, dashboard | SkeletonCard/SkeletonTable/ErrorMessage |
| **Empty States** | WORKING | All pages show empty state when no data | EmptyState component or inline |
| **Error States** | WORKING | All pages with data fetching show error + retry | Fixed strategies + dashboard pages |
| **380px Mobile** | PARTIAL | Terminal pages OK (flexWrap, overflow-x:auto, min/max-width). Dashboard grids may squeeze. | Strategies sidebar flex fixed. Trade table scrolls. |

---

## Polish Issues (Resolved in this pass)

| Issue | File | Fix |
|-------|------|-----|
| `is_simulated` at wrong level | `routes/v1_market.py` | Added `is_simulated` at top level of option-chain response |
| Strategies page: no error state | `app/strategies/page.tsx` | Added ErrorMessage + retry; upgraded loading to SkeletonCard |
| Dashboard: no loading/error states | `app/dashboard/page.tsx` | Added SkeletonCard/SkeletonTable loading + ErrorMessage + SIMULATED badge |
| Strategies header: no flexWrap | `app/strategies/page.tsx` | Added `flexWrap: 'wrap', gap: 8` |
| Dashboard header: no flexWrap | `app/dashboard/page.tsx` | Added `flexWrap: 'wrap'` |
| Terminal page: fixed-width sidebars | `app/terminal/page.tsx` | Changed `flex: 0 0 280/200` to `flex: 1 1` with min/max-width |
| Option chain activity endpoint missing | `routes/v1_user_strategies.py` | Added GET `/{id}/activity` endpoint |
| Activity feed frontend missing | `app/terminal/builder/page.tsx` | Added expandable activity panel per strategy card |
| Activity API method missing | `web/lib/api.ts` | Added `userStrategies.activity(id)` |

---

## Test Suite

**176 tests — all passing** (up from 98 in previous audit).

### Breakdown

| Test File | Tests | Status |
|-----------|-------|--------|
| test_auth.py | 1 | ✅ |
| test_backtest.py | 3 | ✅ |
| test_backtest_routes.py | 6 | ✅ |
| test_broker_angelone.py | 6 | ✅ |
| test_broker_dhan.py | 5 | ✅ |
| test_broker_fyers.py | 7 | ✅ |
| test_broker_timeouts.py | 3 | ✅ |
| test_broker_upstox.py | 6 | ✅ |
| test_circuit_breaker_wiring.py | 5 | ✅ |
| test_engine.py | 14 | ✅ |
| test_gate.py | 10 | ✅ |
| test_leg_controls.py | 13 | ✅ |
| test_margin_estimate.py | 3 | ✅ |
| test_marketdata.py | 3 | ✅ |
| test_mirror_fanout.py | 2 | ✅ |
| test_oms_persistence.py | 10 | ✅ |
| test_risk.py | 4 | ✅ |
| test_risk_fail_closed.py | 8 | ✅ |
| test_sprint3.py | 8 | ✅ |
| test_strategies.py | 3 | ✅ |
| test_user_strategies.py | 20 | ✅ |
| test_user_strategy_runner.py | 35 | ✅ |

---

## Known Limitations

1. **Live broker execution** — Requires broker empanelment. PAPER-only for now.
2. **Historical data** — Simulated when NSE/BSE feeds are unavailable (market closed hours, weekends).
3. **Sub-admin `role` column** — Added ad-hoc via Supabase SQL Editor, not as a migration file.
4. **WebSocket on main domain** — Must use `api.ai.trademetrix.tech`; main domain nginx lacks WS upgrade headers.
5. **TOCTOU race in OMS cancel** — `cancel_order()` can send order between queue check and remove.
6. **OCO sibling cancellation** — Not implemented in OMS.
7. **Broker stubs** — FlatTrade, AliceBlue, Finvasia, 5Paisa have `get_holdings()`, `get_quotes()`, or `get_historical()` returning `[]`.
8. **Help/Changelog pages** — Hardcoded content, not dynamic/CMS-backed.
9. **Admin Beta page** — Mock data, no backend connected.
10. **Portfolio analytics** — Client-side only, not persisted server-side.
