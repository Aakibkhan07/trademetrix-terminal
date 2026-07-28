# Runbook — TradeMetrix Terminal v1.0.0-rc

## Incident Severity Levels

| Level | Definition | Response Time |
|-------|------------|---------------|
| SEV1 | Complete service outage | 15 min |
| SEV2 | Feature degradation | 1 hour |
| SEV3 | Minor issue, no user impact | Next business day |

## Incident Response Procedures

### SEV1: Complete Service Outage

**Symptoms:** `/health` returns 5xx, all users affected.

**Diagnosis:**
```bash
# 1. Check service status
docker compose -f infra/docker-compose.yml ps

# 2. Check logs
docker compose -f infra/docker-compose.yml logs --tail=100 api
docker compose -f infra/docker-compose.yml logs --tail=100 web

# 3. Check database
curl https://api.yourdomain.com/health/db

# 4. Check Redis
redis-cli -u $REDIS_URL PING

# 5. Check resource usage
docker stats --no-stream
```

**Resolution:**
1. If API container is down: `docker compose restart api`
2. If DB is down: restore from backup (see DISASTER_RECOVERY.md)
3. If Redis is down: API falls back to in-memory cache automatically
4. If DNS/Domain: check Cloudflare/DNS provider status

---

### SEV2: Broker Connection Failure

**Symptoms:** Orders failing, circuit breaker OPEN, broker errors.

**Diagnosis:**
```bash
# 1. Check circuit breaker stats
curl https://api.yourdomain.com/v1/admin/circuit-breakers

# 2. Check broker metrics in Prometheus
# Look for broker_requests_failure_total and circuit_breaker_state

# 3. Check broker auth tokens
curl https://api.yourdomain.com/v1/admin/token-status
```

**Resolution:**
1. **Broker API outage (upstream):** Wait for broker recovery. Circuit breaker auto-recovers with exponential backoff (30s base, 5min max).
2. **Token expired:** Trigger manual token refresh via admin panel.
3. **Rate limited:** Check rate_limit_breaches_total. Reduce order rate. The rate limiter auto-recovers within 60s.
4. **Credentials invalid:** Notify user to re-authenticate with broker.

---

### SEV2: Order Execution Failure

**Symptoms:** Orders stuck in PENDING/PARTIALLY_FILLED, reconciliation alerts.

**Diagnosis:**
```bash
# 1. Check pending orders
curl https://api.yourdomain.com/v1/admin/pending-orders

# 2. Check reconciliation status
curl https://api.yourdomain.com/v1/admin/reconciliation
```

**Resolution:**
1. Run manual order reconciliation:
   ```
   docker exec trademetrix-api python -m execution.recovery
   ```
2. If specific orders stuck, cancel via broker API directly (backup admin).
3. Verify broker is reachable and returning order status.

---

### SEV2: High Latency

**Symptoms:** p99 response time > 2s, users report slowness.

**Diagnosis:**
```bash
# 1. Check API latency in Prometheus
# http_request_duration_seconds{p50,p95,p99}

# 2. Check broker latency
# broker_request_duration_seconds

# 3. Check DB query performance
# db_query_duration_seconds

# 4. Check for slow queries
docker compose exec api python -m core.slow_query_log
```

**Resolution:**
1. If DB slow: Check connection pool, add indexes, scale DB.
2. If broker slow: Circuit breaker opens automatically, reducing load.
3. If general: Scale API horizontally (add more containers behind load balancer).

---

### SEV2: WebSocket / Market Data Feed Failure

**Symptoms:** No real-time ticks, stale prices.

**Diagnosis:**
```bash
# 1. Check WebSocket client count
# active_connections metric

# 2. Check market data feed logs
docker compose logs --tail=50 api | grep "market"

# 3. Check broker feed status
curl https://api.yourdomain.com/v1/admin/feed-status
```

**Resolution:**
1. Auto-reconnect triggers automatically (up to 10 retries with exponential backoff).
2. If all retries exhausted, manual restart:
   ```
   docker compose restart api
   ```
3. Yahoo Finance fallback activates if broker feed unavailable.

---

### SEV3: Slow Strategy Execution

**Symptoms:** Strategy signals delayed, backtest taking longer.

**Diagnosis:**
Check scheduler logs, queue depth, executor availability.

**Resolution:**
1. Restart strategy runners:
   ```
   docker compose exec api python -m engine.user_strategy_runner restart
   ```
2. Check Redis queue depth in Grafana.

---

## Post-Mortem Template

```markdown
## Incident Post-Mortem

**Date:** YYYY-MM-DD
**Severity:** SEV1/SEV2/SEV3
**Duration:** Xh YZm

### Summary
One paragraph describing what happened.

### Timeline
- HH:MM — Detection
- HH:MM — Diagnosis
- HH:MM — Mitigation
- HH:MM — Resolution

### Root Cause
What caused the incident.

### Action Items
- [ ] Fix identified in the code/configuration
- [ ] Add monitoring/alert for this scenario
- [ ] Update runbook
- [ ] Schedule blameless post-mortem meeting
```
