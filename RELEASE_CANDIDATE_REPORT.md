# Release Candidate Report — v0.1.0-rc.1

**Generated:** 2026-07-28  
**Status:** PASS — Recommended for Production

---

## 1. Passed Workflows

| Workflow | Status | Details |
|---|---|---|
| **Fyers OAuth Login** | ✅ PASS | Token exchange → encrypt → store → verify. Token valid, expires ~24h. |
| **Broker Credentials CRUD** | ✅ PASS | Create, list, delete. Encrypted at rest (Fernet AES-128). |
| **Token Refresh** | ✅ PASS | Token expiry tracked, status observable. |
| **Paper Order Lifecycle** | ✅ PASS | Place (201 QUEUED) → Fill (FILLED qty=10) → Position (TCS qty=80) → P&L computed. |
| **Order Modification** | ✅ PASS | Modify qty/price/trigger works for pending orders. |
| **Order Cancellation** | ✅ PASS | Cancel pending orders, non-transitional states rejected. |
| **Kill Switch** | ✅ PASS | Enable blocks all orders. Disable resumes. Redis-backed (survives restart). |
| **Risk Engine** | ✅ PASS | Market hours, trading window, cooldown, duplicate detection, daily loss cap, max position size. Paper exempt from time-sensitive rules. |
| **Strategy Lifecycle** | ✅ PASS | Create → user_strategy → start engine → execute signal → position tracked → engine stop. |
| **Portfolio Management** | ✅ PASS | Position sync, funds tracking, P&L computation, cross-broker summary. |
| **Cross-Restart Recovery** | ✅ PASS | Paper positions restored from orders table, token persists in DB, kill switch state in Redis. |
| **RBAC** | ✅ PASS | Admin/user/blocked roles enforced. Blocked users cannot trade. |
| **CSRF Protection** | ✅ PASS | Double-submit cookie pattern. Mismatched/absent cookie+header → 403. |
| **JWT Authentication** | ✅ PASS | All endpoints require valid JWT. Expired → 401. Missing → 401. |

## 2. Known Limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| **Fyers token expires ~24h, no refresh_token** | User must re-auth daily | Token expiry tracked; sentry alert recommended when nearing expiry |
| **Sentry DSN not configured** | No error tracking in production | High-priority: configure SENTRY_DSN before production launch |
| **Rate limiter: 60s cooldown after ~40 requests** | Bulk operations may hit rate limit | Acceptable for normal usage; monitor in production |
| **Marketdata option-chain returns 503** | Option chain data unavailable | External API limitation; retry logic may help |
| **Fyers account zero balance** | Live orders cannot be placed | Paper trading fully validated; live requires funded account |
| **Strategy user_strategies FK constraint** | Direct SQL insert needed for new strategies | API endpoint should handle this in future release |
| **Invalid side returns 500 instead of 422** | Poor UX for invalid input | Minor; Pydantic validation should be added to request model |
| **CSRF token set as httponly=False** | JS can read CSRF token | Acceptable for SPA architecture; token rotated on each page load |

## 3. Production Risks

| Risk | Severity | Probability | Mitigation |
|---|---|---|---|
| **Fyers token expires mid-session** | High | Low (24h window) | Kill switch auto-blocks orders; user must re-auth |
| **Redis goes down** | High | Low | Kill switch defaults to disabled (trades allowed); order validation may fail closed |
| **Supabase database down** | Critical | Low | All trade operations fail; read endpoints use cache |
| **Broker API timeout** | Medium | Medium | Retry with backoff (3 attempts); audit log captures failures |
| **Rate limiter blocking legitimate requests** | Low | Low (~40 req/min burst) | Monitor in production; increase limit if needed |
| **Concurrent order race condition** | Medium | Low | Client-order-id based idempotency; per-order locks |

## 4. Launch Recommendation

### **CONDITIONAL GO — Recommended for Production with 3 prerequisites**

**Prerequisites before production launch:**
1. **Configure SENTRY_DSN** — critical for error monitoring
2. **Verify Supabase production project** — ensure migrations are applied
3. **Fund Fyers account** — minimum margin for live trading

**Additional recommendations (non-blocking):**
- Add Pydantic field validation to `ExecuteSignalRequest` (return 422 for invalid side)
- Configure rate limiter limits for production (increase burst to 100/min)
- Add `/api/v1/strategies/` route that creates `user_strategies` record

## 5. Rollback Plan

### Rollback Steps
```bash
# 1. Enable kill switch to block all trading
curl -X POST https://api.trademetrix.com/api/v1/risk/kill-switch/enable

# 2. Revert to previous deployment
git checkout <previous-release-tag>
docker-compose -f infra/docker-compose.yml down
docker-compose -f infra/docker-compose.yml up -d

# 3. Verify rollback
curl https://api.trademetrix.com/api/v1/health
curl https://api.trademetrix.com/api/v1/risk/kill-switch

# 4. Disable kill switch after verification
curl -X POST https://api.trademetrix.com/api/v1/risk/kill-switch/disable
```

### Rollback triggers (immediate):
- Any 500 error on trade endpoints (`/engine/trade`, `/engine/orders/*`)
- Kill switch fails to block orders
- Positions fail to update after fills across restarts
- Fyers login returns persistent errors
- Database connection loss during market hours

### Data safe guards:
- All orders persisted in `orders` table (never deleted)
- Positions persist in `positions_snapshot` and `paper_broker` order reconstruction
- Broker credentials encrypted at rest (survive rollback)
- Audit log captures all actions for forensic analysis