# Go-Live Checklist

## Pre-Launch

### Infrastructure
- [x] Database migrations applied (Supabase local — verify on production)
- [x] Redis connection configured
- [x] Environment variables set (SECRET_KEY, ENCRYPTION_KEY, SUPABASE_*)
- [ ] **SENTRY_DSN** configured for error tracking
- [ ] Production domain and SSL certificate configured
- [ ] CORS origins configured for production frontend domain

### Broker Connectivity
- [x] Fyers OAuth login flow verified (token exchange, encryption, storage)
- [x] Fyers token refresh works (token_expires_at tracked)
- [ ] Fyers token auto-refresh verified (wait for expiry or manual test)
- [x] Paper broker works (place, fill, position, P&L)
- [x] Broker credentials encrypted at rest

### Core Trading
- [x] Order placement (MARKET, LIMIT, SL, SLM) via paper broker
- [x] Order modification and cancellation
- [x] Risk engine (kill switch, market hours, cooldown, duplicate detection)
- [x] Paper order lifecycle: place → fill → position → P&L
- [x] Cross-restart position recovery (PaperBroker._restore_positions)
- [x] Portfolio Manager refresh and reconciliation
- [x] OMS order queue processing

### Security
- [x] JWT authentication enforced on all endpoints
- [x] CSRF protection on mutating endpoints (cookie+header matching)
- [x] RBAC (admin, user, blocked roles)
- [x] Broker credentials encrypted with Fernet (AES-128)
- [x] Expired JWT rejected (401)
- [x] Unauthenticated requests rejected (401)
- [ ] Rate limiter configuration for production (currently 40 req/min burst)

### Monitoring
- [ ] **SENTRY_DSN** required for production error tracking
- [x] Prometheus metrics configured (order latency, broker errors, validation failures)
- [x] Audit logging (all trade actions logged to audit_log table)
- [x] Kill switch status observable (GET /api/v1/risk/kill-switch)

### Testing
- [x] PAT regression: 98/98 pass
- [x] Unit tests: 103 pass (1 pre-existing csrf cookie test issue)
- [x] Concurrent user testing: 25 parallel requests no rate limiting
- [x] Performance: read endpoints avg 76ms, write avg 181ms
- [x] Recovery: positions survive restart, token survives restart, kill switch state survives restart
- [x] Failure injection: kill switch blocks trades, invalid orders rejected

## Launch Day

### Verification Steps
1. [ ] Verify Supabase production connection
2. [ ] Verify Redis connection
3. [ ] Verify SENTRY_DSN
4. [ ] Verify Fyers OAuth login flow on production domain
5. [ ] Verify paper trade lifecycle (place → fill → position)
6. [ ] Verify kill switch enable/disable
7. [ ] Verify broker credentials CRUD

### Rollback Triggers
- Kill switch fails to block orders → immediate rollback
- Orders placed but not filling → rollback within 1 minute
- Positions not updating after fills → rollback within 5 minutes
- Fyers OAuth login fails → rollback within 30 minutes
- Any 500 error on trade endpoints → rollback immediately

## Post-Launch (24h)
1. [ ] Monitor audit log for validation failures
2. [ ] Monitor broker token expiry
3. [ ] Verify daily P&L computation
4. [ ] Verify square-off logic at market close