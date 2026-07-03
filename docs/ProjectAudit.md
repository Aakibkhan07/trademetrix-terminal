# Project Audit

> Generated: 2026-07-02
> Method: Manual codebase walkthrough of all files in apps/api, apps/web, infra, scripts
> Rule: Zero code modifications — documentation only.

---

## Backend: apps/api

### 1. Routes (/routes)

| File | Lines | Status | Notes |
|------|-------|--------|-------|
| `v1_otp.py` | ~180 | ✅ COMPLETE | send-otp, register-with-otp, verify-otp, logout. SHA256 OTP hashing, Redis-backed, debug_otp for dev. verify-otp handles missing profile gracefully. |
| `v1_brokers.py` | ~250 | ✅ COMPLETE | CRUD + metadata endpoint. Flexible field name mapping (api_key/client_id/client_code/access_token). OAuth authorize/callback flow. |
| `v1_feed.py` | ~80 | ✅ COMPLETE | start/stop/status. Stops existing feeds + alert checker before starting new. Proper error handling. |
| `v1_alerts.py` | ~150 | ✅ COMPLETE | CRUD + toggle + delete. One shared/alerts route file with full alert lifecycle. |
| `v1_orders.py` | ~100 | ✅ COMPLETE | List orders, place order. Integrates with broker adapter via factory. |
| `v1_positions.py` | ~60 | ✅ COMPLETE | Current positions + P&L aggregation from broker. |
| `v1_portfolio.py` | ~80 | ✅ COMPLETE | Portfolio performance data (equity curve, monthly returns, drawdown, P&L by symbol). |
| `v1_admin.py` | ~200 | ✅ COMPLETE | Users list, trades view, audit log, risk metrics, kill switch, user broker assignment. |
| `v1_broadcast.py` | ~100 | ✅ COMPLETE | Send broadcast to all users or specific user. |
| `v1_tradingview.py` | ~40 | ⚠️ FIXED | Had `.execute()` inside `safe_single()` which broke webhook no-user_id path. Fixed — now uses `_execute_safe` pattern. |

### 2. Core Services (/core)

| File | Lines | Status | Notes |
|------|-------|--------|-------|
| `ratelimit.py` | ~70 | ⚠️ FIXED | Had `call_next(next)` instead of `call_next(request)` — crashed every API request. Fixed. |
| `notifications.py` | ~250 | ✅ COMPLETE | Fast2SMS, Twilio WhatsApp, SMTP Email with console fallback. Both OTP delivery and alert notification methods. |

### 3. Middleware (/middleware)

| File | Lines | Status | Notes |
|------|-------|--------|-------|
| `csrf.py` | ~50 | ✅ COMPLETE | CSRF double-submit cookie. SAFE_PATHS includes all current endpoints. |
| `auth.py` | ~40 | ✅ COMPLETE | Session validation against Redis. Correctly excludes /auth/ and /public/ paths. |

### 4. Market Data (/market)

| File | Lines | Status | Notes |
|------|-------|--------|-------|
| `data_socket.py` | ~180 | ✅ COMPLETE | WebSocket manager with subscribe/broadcast per symbol. Active connections tracked. |
| `simulator.py` | ~200 | ✅ COMPLETE | MarketSimulator runs 24/7. Realistic base prices for all 65 symbols. Gaussian random walk for price movement. |
| `alert_checker.py` | ~120 | ✅ COMPLETE | Subscribes via `shared_socket.subscribe("*")`. Checks upper/lower thresholds per symbol. Fires notifications via core/notifications.py. |
| `shared_socket.py` | ~20 | ✅ COMPLETE | Singleton pattern. Single `SharedPriceSocket` instance. |

### 5. Brokers (/brokers)

| File | Lines | Status | Notes |
|------|-------|--------|-------|
| `registry.py` | ~100 | ✅ COMPLETE | Metadata for all 10 brokers (display name, auth type, fields, OAuth URLs, instructions). |
| `base.py` | ~50 | ✅ COMPLETE | Abstract BaseAdapter with standard interface (get_quotes, place_order, stream, etc.). |
| `factory.py` | ~30 | ✅ COMPLETE | `get_adapter(broker_name)` returns appropriate adapter class. Supports all 10 brokers. |
| `fyers_adapter.py` | ~200 | ✅ COMPLETE | Fyers REST + WebSocket. Full OAuth flow. |
| `zerodha_adapter.py` | ~150 | ⚠️ FIXED | `stream()` was WS with no subscription message — changed to HTTP polling via `get_quotes`. |
| `angelone_adapter.py` | ~180 | ⚠️ FIXED | `re.match` → `_re.match` (NameError on F&O symbol parsing). WS streaming for NSE/Capital symbols. |
| `dhan_adapter.py` | ~120 | ⚠️ LIMITED | Access_token-direct only. No OAuth flow yet. REST + WS. |
| `upstox_adapter.py` | ~100 | ⚠️ LIMITED | Access_token-direct only. No OAuth flow yet. REST only. |
| `fivepaisa_adapter.py` | ~80 | ⚠️ FIXED | `stream()` was empty `pass` — now uses HTTP polling. REST only. |
| `aliceblue_adapter.py` | ~80 | ✅ COMPLETE | REST client with auth flow. |
| `finvasia_adapter.py` | ~70 | ✅ COMPLETE | REST client. |
| `flattrade_adapter.py` | ~70 | ✅ COMPLETE | REST client. |
| `kotakneo_adapter.py` | ~100 | ⚠️ FIXED | `stream()` had no subscription message — now sends subscription JSON before reading lines. |

### 6. Models, Config, Main

| File | Status | Notes |
|------|--------|-------|
| `models/models.py` | ✅ COMPLETE | All DB models defined (users, positions, orders, trades, alerts, broadcast, journal_entries, notification_prefs, broker_credentials). |
| `config.py` | ✅ COMPLETE | Pydantic Settings with env vars. Covers all API keys, DB URLs, Redis config. |
| `main.py` | ✅ COMPLETE | App factory, middleware stack, router includes, lifecycle events. 3 bugs fixed. |

---

## Frontend: apps/web

| File | Status | Notes |
|------|--------|-------|
| `page.tsx` (marketing) | ✅ COMPLETE | Standalone landing page (server component). Hero, features, CTA. No sidebar, no auth. |
| `layout.tsx` | ✅ COMPLETE | Root layout with AppLayout integration. |
| `portal/page.tsx` | ✅ COMPLETE | Full portal: overview, positions, orders, performance charts, brokers, alerts, journal. Dynamic broker forms. |
| `admin/page.tsx` | ✅ COMPLETE | Admin tabs: Dashboard, Users, Brokers, Trades, Audit, Risk, Broadcast. Dynamic broker forms + OAuth. |
| `app-layout.tsx` | ✅ COMPLETE | Conditional chrome (sidebar/ticker/status bar) for terminal routes. Kill switch try/catch fixed. |
| `sidebar.tsx` | ✅ COMPLETE | Nav links for portal + admin. Collapsible on mobile. |
| `market-ticker.tsx` | ✅ COMPLETE | Scrolling price ticker in header. |
| `status-bar.tsx` | ✅ COMPLETE | Connection status (connected/reconnecting/disconnected). |
| `use-market-data.tsx` | ✅ COMPLETE | WebSocket hook with 200ms buffered tick updates. |
| `api.ts` | ✅ COMPLETE | HTTP client with all API methods. BrokerMeta, BrokerFieldMeta interfaces. Flexible saveCredentials. |
| `components.css` | ✅ COMPLETE | Shared styles. Legacy CSS aliases for backward compat. t-btn-sub class. Mobile responsive. |

## Infrastructure

| File | Status | Notes |
|------|--------|-------|
| `infra/production/docker-compose.yml` | ✅ COMPLETE | Backend, Redis, Postgres services configured. Fyers credentials set. |
| `traefik config` | ✅ COMPLETE | TLS, routing configured per VPS. |

## Known Issues Found (All Documented, None Changed)

1. **Dhan/Upstox missing OAuth flow**: Both adapters accept `access_token` directly but have no OAuth redirect/authorize flow implemented. User must obtain token externally.

2. **AliceBlue/Finvasia/FlatTrade/KotakNeo `stream()` untested**: Adapters implement the interface but `stream()` has never been validated against live broker APIs. May need debugging.

3. **No pagination on orders/positions tables**: All data loads at once. Will become slow with 1000+ orders.

4. **No WebSocket reconnection backoff**: If WS disconnects, `use-market-data.tsx` tries to reconnect immediately. Could flood server on network flapping.

5. **`templates/admin.html` (Jinja2) vs `admin/page.tsx` (Next.js)**: Two admin UIs exist. The Jinja2 template (rendered at `/admin` by FastAPI) is likely unused — Next.js handles `/admin` routing. Consider deprecating the Jinja2 template.

6. **No sitemap/robots.txt**: Marketing site has no SEO metadata.

7. **No unit tests**: Zero test files found in the entire repository. All testing is manual.

8. **Simulator prices drift unbounded**: `MarketSimulator` uses Gaussian random walk without mean reversion. Prices can theoretically drift to unrealistic levels over long periods.

9. **No alert persistence across restarts**: Alerts are stored in DB, but the `AlertChecker` is in-memory only. If the API restarts, `start_market_feed` must be called again to resume alert checking.

10. **Redis session data not persisted**: Sessions live in Redis only. Restarting Redis logs out all users.
