# Release Notes — TradeMetrix Terminal v1.0.0-rc

## Release Candidate 1 — July 28, 2026

**STATUS:** ⚠️ RELEASE CANDIDATE — Not yet production-ready (see Known Limitations)

---

## Features

### Broker Integration
- Support for 11 brokers: Angel One, Dhan, Fyers, Upstox, Zerodha, Alice Blue, 5Paisa, Finvasia, Flattrade, Kotak Neo, Groww
- Unified order interface: place, modify, cancel orders across all brokers
- Broker authentication with OAuth (Fyers, Dhan, Upstox, Zerodha) and credentials + TOTP
- Automatic token refresh with retry and exponential backoff
- Real-time WebSocket market data streaming (Fyers, Angel One, Dhan, Upstox)
- Yahoo Finance fallback when broker data unavailable

### Order Execution
- Order validation and risk checks before submission
- Rate limiting per broker (configurable RPM)
- Pending order reconciliation on startup
- Webhook retry worker with 3 retries and backoff
- Square-off scheduler for end-of-day position closure
- Kill switch for emergency order suspension

### Circuit Breaker (NEW in RC)
- All broker operations protected by circuit breaker with OPEN / HALF_OPEN / CLOSED states
- Exponential backoff on recovery (base 30s, max 5min, backoff factor 2x)
- Fallback values for read operations (orderbook, positions, holdings, funds)
- Prometheus metrics for circuit breaker state per broker
- Auto-recovery when broker becomes available again

### Strategy Engine
- User-defined trading strategies with multi-leg support
- Strategy catalog with pre-built strategies (MACD crossover, etc.)
- Compile, deploy, and run strategies
- Backtesting engine
- Strategy assignment and scheduling

### Market Data
- Real-time ticks via WebSocket
- Historical data retrieval (daily, weekly, monthly)
- Option chain data
- Broadcast system for strategy signals

### User Management
- JWT-based authentication with Supabase GoTrue
- Role-based access control (user, admin, super_admin)
- Subscription management (Starter, Pro, Enterprise)
- Broker credential management with encryption at rest

### Monitoring & Observability
- Prometheus metrics for API, broker, DB, circuit breakers, rate limits
- Structured JSON logging
- Sentry error tracking (requires DSN configuration)
- Telegram alerting for system events

### Frontend
- Next.js 14 App Router
- 30+ routes covering all features
- Real-time market data display
- Strategy builder UI
- Admin dashboard

## Bug Fixes

- CSRF double-submit cookie race condition resolved — token stored on `request.state` and shared between route handler and middleware
- Subscription table column mismatch (`plan` vs `tier`) — code now reads `plan` with `tier` fallback
- Strategy service `days_of_week` parsing — string to `list[int]` conversion with null `option_type` handling
- Broker `_get_http_client` — check for closed client before reuse
- Database disconnect race condition — `getattr` guard prevents `'NoneType' not awaitable`
- Redis connection retry — 30s cooldown in queue subscriber prevents tight reconnect loops
- Token refresh timeout handling — configurable timeout with max retries
- Rate limiter — in-memory fallback when Redis unavailable
- Broker service — supported broker validation on credential save
- Multiple edge cases in order normalization and response parsing

## Breaking Changes

- **Circuit breaker integration**: All broker adapter instantiation must use `create_broker()` instead of `get_broker()()` directly. The broker `__init__.py` exports `create_broker()` returning a `CircuitBreakerBroker` wrapper. Direct adapter instantiation bypasses circuit breaker protection.
- **Strategy assignments FK**: Changed from `strategies(id)` to `user_strategies(id)`. Existing strategy assignment data must be migrated.
- **Rate limit environment variable**: If `RATE_LIMIT_RPM` was previously set manually, it is now configured via broker adapter constants (default 600 RPM). Custom env var support to be added.

## Known Limitations

### Production Blockers (Must resolve before production)

1. **Live broker authentication untested**: All broker adapters have unit tests but no live credential testing has been completed. Required for: Angel One, Dhan, Fyers, Upstox, Zerodha.

2. **Sentry not configured**: `SENTRY_DSN` is empty in `.env`. Production errors would be invisible. Set to a valid Sentry DSN before deployment.

3. **No circuit breaker circuit breaker**: The circuit breaker protects against broker failures but there is no parent-level breaker to protect against cascading failures across brokers.

### Minor Limitations

4. **CSRF bootstrap endpoint fails in test**: `GET /csrf-bootstrap` returns a cookie but the ASGI test client doesn't forward it correctly. Not a production concern — works in browser.

5. **Option chain endpoint returns 503 in dev**: `GET /marketdata/option-chain` requires a live broker connection. Expected behavior in development environment.

6. **Rate limiter 60s cooldown**: After ~40 rapid requests, rate limiter enters 60s cooldown. Works as designed but may surprise new testers in demo environments.

7. **Auth RLS policies**: Some tables have permissive RLS policies (allowing all authenticated users). Should be tightened before production launch.

8. **`.env` in git**: The environment file is tracked in git. For production, use a secret manager and `.env.example` pattern.

9. **No end-to-end browser tests**: The frontend build succeeds but no Playwright/Cypress tests exist for user flows.

10. **No CDN configuration**: Static assets are served directly from the Next.js server. For production, configure Cloudflare or similar CDN.

## Test Results

| Suite | Pass Rate | Notes |
|-------|-----------|-------|
| PAT (Product Acceptance) | 97/98 (99%) | 1 known issue (CSRF bootstrap) |
| Broker — Angel One | 10/10 | 100% |
| Broker — Dhan | 10/10 | 100% |
| Broker — Fyers | 10/10 | 100% |
| Broker — Upstox | 10/10 | 100% |
| Broker — Timeouts | 6/7 | 1 pre-existing assertion mismatch |
| Broker — Service | 19/19 | 100% |
| Circuit Breaker | 13/13 | 100% |
| Other Unit Tests | ~35 | Varied |
| Frontend Build | ✅ | 30+ routes compiled |

## Upgrade Notes

### From v0.x to v1.0.0-rc

1. **Regenerate encryption key** — All broker credentials must be re-encrypted with the new key
2. **Run database migrations** — `supabase migration up`
3. **Update broker instantiation** — Replace `get_broker(name)()` with `create_broker(name)` in any custom broker code
4. **Add circuit breaker config** — Default settings are sane, but review `failure_threshold`, `recovery_timeout`, and `backoff_factor`
5. **Configure monitoring** — Set `SENTRY_DSN`, Prometheus, and Grafana

## Assets

- `docker pull trademetrix/api:rc-1.0.0`
- `docker pull trademetrix/web:rc-1.0.0`
- GitHub tag: `v1.0.0-rc`
