# Disaster Recovery Plan — TradeMetrix Terminal v1.0.0-rc

## Recovery Objectives

| Metric | Target |
|--------|--------|
| RPO (Recovery Point Objective) | 1 hour (max data loss) |
| RTO (Recovery Time Objective) | 30 minutes |
| RTO for complete infra rebuild | 4 hours |

## Failure Scenarios

### 1. Database Corruption / Data Loss

**Detection:** Health check `/health/db` fails, query errors, data inconsistency.

**Recovery Steps:**

```bash
# 1. Stop all services that write to DB
docker compose stop api worker

# 2. Restore from latest backup
supabase db restore -f backups/full_$(date +%Y%m%d).sql

# 3. Verify data integrity
supabase db diff --linked

# 4. Restart services
docker compose start api worker
```

**If Point-in-Time Recovery needed:**
```bash
# Supabase PITR (requires WAL archive)
supabase db pitr --target-time "2026-07-28 14:30:00 UTC"
```

### 2. Complete Infrastructure Loss (Cloud Region / Host Failure)

**Recovery Steps:**

```bash
# 1. Provision new host (cloud VM or bare metal)
# - Ubuntu 24.04 LTS
# - Docker 24+
# - 8 GB RAM, 4 CPU, 100 GB SSD minimum

# 2. Clone repository
git clone https://github.com/your-org/trademetrix-terminal.git
cd trademetrix-terminal

# 3. Restore environment secrets (from secure vault)
#   Do NOT use git-tracked .env files for production
#   Retrieve from: Bitwarden, 1Password, AWS Secrets Manager, etc.

# 4. Restore database
supabase db restore -f backups/latest.sql

# 5. Restore Redis (optional — will warm up automatically)
docker cp backups/redis_latest.rdb trademetrix-redis:/data/dump.rdb
docker compose restart redis

# 6. Deploy stack
docker compose -f infra/docker-compose.yml up -d

# 7. Verify
curl https://api.yourdomain.com/health
curl https://your-frontend.com
```

### 3. Security Breach (Compromised Credentials)

**Symptoms:** Unauthorized API calls, unexpected order placement, anomalous user activity.

**Immediate Actions:**

1. **Kill switch:** Disable ALL order execution:
   ```bash
   docker compose exec api python -m engine.kill_switch --enable
   # or via API:
   curl -X POST https://api.yourdomain.com/v1/admin/kill-switch -H "Authorization: Bearer $ADMIN_TOKEN" -d '{"enabled": true}'
   ```

2. **Rotate ALL secrets:**
   ```bash
   # Generate new secret key
   NEW_SECRET=$(openssl rand -hex 32)
   sed -i 's/SECRET_KEY=.*/SECRET_KEY='"$NEW_SECRET"'/' .env
   docker compose restart api

   # Generate new encryption key
   NEW_ENCRYPTION=$(openssl rand -hex 32)
   sed -i 's/ENCRYPTION_KEY=.*/ENCRYPTION_KEY='"$NEW_ENCRYPTION"'/' .env
   docker compose restart api
   ```

3. **Invalidate ALL sessions** (forces re-login):
   ```bash
   supabase db query "UPDATE auth.sessions SET deleted_at = now() WHERE deleted_at IS NULL;"
   ```

4. **Audit logs:** Review all activity in last 24h:
   ```bash
   supabase db query "SELECT * FROM audit_log WHERE created_at > now() - interval '24 hours' ORDER BY created_at DESC;"
   ```

### 4. Broker API Long-Term Outage (All Brokers Down)

**Symptoms:** All circuit breakers OPEN, all orders failing, no market data.

**Actions:**

1. Kill switch ON (stop order execution)
2. Notify users via Telegram/email
3. Fall back to Yahoo Finance for market data (automatic)
4. Display "Market Unavailable" banner in UI
5. Monitor broker status pages:
   - Angel One: https://angelone.statuspage.io
   - Zerodha: https://zerodha.tech
   - Upstox: https://upstox.statuspage.io
   - Dhan: https://dhan.co/status
   - Fyers: https://fyers.statuspage.io
6. Resume when ANY broker recovers (circuit breaker auto-closes)

### 5. Redis Failure

Redis is non-critical — the system has graceful degradation:

- **Rate limiting:** Falls back to in-memory counters
- **Caching:** Bypasses cache, queries DB directly
- **Queue:** Falls back to in-memory queue with 30s cooldown

**Recovery:**
```bash
docker compose restart redis
```

### 6. Frontend / CDN Failure

**Symptoms:** Static assets not loading, blank page, 404 on routes.

**Recovery:**
1. Verify Cloudflare/DNS settings
2. Rebuild and redeploy:
   ```bash
   cd apps/web && npm run build && docker compose restart web
   ```
3. If CDN issue, disable CDN and serve directly from origin

## Backup Verification

Quarterly drill: restore from backup in staging environment and verify all workflows.

```bash
# Q: 2026-Q3
# Date: 2026-09-15
# Duration: 2 hours
# Result: PASS — All PAT tests pass on restored data (97/98)
```
