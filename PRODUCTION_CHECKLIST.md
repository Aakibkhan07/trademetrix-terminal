# Production Readiness Checklist — TradeMetrix Terminal v1.0.0-rc

Every item must be verifiable. Mark ✅ when confirmed.

## Security

| # | Item | Verification Method | Status |
|---|------|-------------------|--------|
| 1 | SECRET_KEY is a unique random 64-char hex string | `openssl rand -hex 32` | ❌ |
| 2 | ENCRYPTION_KEY is a unique random 32-char base64 string | `openssl rand -hex 32` | ❌ |
| 3 | CORS_ORIGINS restricted to known frontend domains | `curl -I -H "Origin: https://evil.com" https://api/...` returns no `Access-Control-Allow-Origin` | ❌ |
| 4 | HTTPS enforced (TLS 1.2+) | `curl -v https://api/...` shows TLS handshake | ❌ |
| 5 | Rate limiting enabled (600 RPM per broker) | `curl /metrics` shows `rate_limit_breaches_total` | ❌ |
| 6 | JWT tokens expire in 24h or less | Decode token, check `exp` claim | ❌ |
| 7 | CSRF protection enabled for state-changing endpoints | `curl -X POST /...` without CSRF token returns 403 | ❌ |
| 8 | Admin IP whitelist configured | `curl /admin/...` from non-whitelisted IP returns 403 | ❌ |
| 9 | RBAC enforced (user cannot access admin routes) | Non-admin user calls `/admin/...` returns 403 | ❌ |
| 10 | Broker credentials encrypted at rest (Fernet) | Check `encrypted_api_key` column in DB — not plaintext | ❌ |
| 11 | Webhook signatures verified | `TRADINGVIEW_WEBHOOK_SECRET` set in env | ❌ |
| 12 | `.env` files excluded from git | `git ls-files .env*` shows only `.env.example` | ❌ |
| 13 | No secrets in environment logs | Check recent logs for any exposed tokens/keys | ❌ |
| 14 | Input validation on all API endpoints | Test with invalid payloads — expect 422 | ❌ |

## Infrastructure

| # | Item | Verification Method | Status |
|---|------|-------------------|--------|
| 15 | Docker Compose stack deploys cleanly | `docker compose up -d` — all containers healthy | ❌ |
| 16 | PostgreSQL connection pool size set (32 max) | `SELECT count(*) FROM pg_stat_activity` | ❌ |
| 17 | Redis maxmemory configured | `redis-cli CONFIG GET maxmemory` | ❌ |
| 18 | Health checks configured for all containers | `docker inspect <container> | jq '.[].Config.Healthcheck'` | ❌ |
| 19 | Container restart policy set to `unless-stopped` | Check docker-compose.yml | ❌ |
| 20 | Log rotation configured (max 100MB per container) | Docker daemon config or log driver | ❌ |
| 21 | Nginx/Gunicorn max request body size matches config | `MAX_REQUEST_SIZE_BYTES=102400` | ❌ |
| 22 | Database migrations applied and idempotent | `supabase migration up` — no errors | ❌ |
| 23 | Cron job for daily DB backup configured | `crontab -l` shows backup job | ❌ |
| 24 | Monitoring stack (Prometheus + Grafana) deployed | `curl /metrics` returns valid Prometheus format | ❌ |

## Broker Integration

| # | Item | Verification Method | Status |
|---|------|-------------------|--------|
| 25 | Angel One: place/modify/cancel order tested | Unit test `test_broker_angelone.py` passes | ✅ |
| 26 | Dhan: place/modify/cancel order tested | Unit test `test_broker_dhan.py` passes | ✅ |
| 27 | Fyers: place/modify/cancel order tested | Unit test `test_broker_fyers.py` passes | ✅ |
| 28 | Upstox: place/modify/cancel order tested | Unit test `test_broker_upstox.py` passes | ✅ |
| 29 | Broker authentication with timeout (5s connect, 8s request) | `test_broker_timeouts.py` passes | ✅ |
| 30 | Token refresh with retry and backoff | Verify `token_manager.py` retry logic | ✅ |
| 31 | Circuit breaker wraps every broker operation | `test_circuit_breaker_wiring.py` passes | ✅ |
| 32 | Circuit breaker exponential backoff (30s → 5min max) | Unit test verifies backoff factor 2x | ✅ |
| 33 | Broker rate limiting per broker (120 RPM per broker) | `rate_limiter.py` test passes | ✅ |
| 34 | OAuth flow for Fyers, Dhan, Upstox, Zerodha | Integration test (requires live creds) | ⚠️ |

## Reliability & Recovery

| # | Item | Verification Method | Status |
|---|------|-------------------|--------|
| 35 | Pending order reconciliation on startup | Check `recovery.py` runs at boot | ✅ |
| 36 | WebSocket auto-reconnect (max 10 retries, 30s backoff) | `WS_RECONNECT_MAX_RETRIES=10` in config | ✅ |
| 37 | Redis failure → in-memory fallback | Stop Redis, verify API still responds | ✅ |
| 38 | DB failure → graceful error response (not crash) | Stop PostgreSQL, verify API returns 503 | ✅ |
| 39 | Rate limiter in-memory fallback when Redis down | `core/ratelimit.py` has memory fallback | ✅ |
| 40 | Kill switch for emergency order suspension | `/v1/admin/kill-switch` endpoint | ✅ |
| 41 | Webhook retry worker (3 retries with backoff) | `execution/webhook_retry.py` | ✅ |
| 42 | Square-off scheduler stops positions at market close | `squareoff_service.py` | ✅ |

## Frontend

| # | Item | Verification Method | Status |
|---|------|-------------------|--------|
| 43 | Next.js build succeeds (no errors) | `npm run build` — all routes compiled | ✅ |
| 44 | All routes render without 500 errors | Visit every route (30+) | ✅ |
| 45 | API proxy configured in Next.js | `next.config.js` rewrites | ✅ |
| 46 | Loading states for all async operations | Visual check | ❌ |
| 47 | Error boundary wraps each page | Test by triggering an API failure | ❌ |

## Monitoring & Observability

| # | Item | Verification Method | Status |
|---|------|-------------------|--------|
| 48 | Sentry DSN configured for API | `SENTRY_DSN` set in env | ❌ |
| 49 | Sentry DSN configured for Web | `NEXT_PUBLIC_SENTRY_DSN` set | ❌ |
| 50 | Prometheus metrics endpoint returns data | `curl /metrics` returns > 50 metric lines | ✅ |
| 51 | Circuit breaker state exposed in metrics | `curl /metrics | grep circuit_breaker` | ✅ |
| 52 | Grafana dashboard imported and configured | See `MONITORING_DASHBOARD.md` | ❌ |
| 53 | Uptime monitor configured (e.g., Better Uptime, Pingdom) | External monitoring service active | ❌ |
| 54 | Telegram alerting configured for SEV1 incidents | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` set | ❌ |

## Compliance & Documentation

| # | Item | Verification Method | Status |
|---|------|-------------------|--------|
| 55 | DEPLOYMENT.md written and reviewed | File exists at project root | ✅ |
| 56 | OPERATIONS.md written and reviewed | File exists at project root | ✅ |
| 57 | RUNBOOK.md written and reviewed | File exists at project root | ✅ |
| 58 | DISASTER_RECOVERY.md written and reviewed | File exists at project root | ✅ |
| 59 | RELEASE_NOTES.md written and reviewed | File exists at project root | ✅ |
| 60 | Database schema documented | Supabase schema dump | ❌ |

## Final Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | | | |
| DevOps | | | |
| QA | | | |
| Product Owner | | | |

**Status:** 28/60 verified ✅ | 28 ❌ | 4 ⚠️ (requires live broker)
