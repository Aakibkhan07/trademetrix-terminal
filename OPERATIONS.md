# Operations Guide — TradeMetrix Terminal v1.0.0-rc

## Service Architecture

| Service | Port | Health Endpoint | Dependencies |
|---------|------|-----------------|--------------|
| API (FastAPI) | 8000 | `/health` | PostgreSQL, Redis |
| Web (Next.js) | 3000 | N/A | API |
| PostgreSQL (Supabase) | 5432 | Supabase internal | — |
| Redis | 6379 | `PING` | — |
| Nginx | 443 | N/A | API, Web |

## Monitoring

### Prometheus Metrics (available at `/metrics`)

**Key Metrics to Watch:**

| Metric | Type | Alert Threshold | Description |
|--------|------|-----------------|-------------|
| `http_request_duration_seconds` | Histogram | p99 > 2s | API response times |
| `broker_request_duration_seconds` | Histogram | p99 > 10s | Broker API latency |
| `circuit_breaker_state` | Gauge | 2 (open) | Broker circuit breaker state (0=closed, 1=half, 2=open) |
| `process_memory_bytes` | Gauge | > 512MB RSS | Process memory usage |
| `process_cpu_percent` | Gauge | > 80% | CPU utilization |
| `active_connections` | Gauge | > 1000 | Concurrent WebSocket connections |
| `rate_limit_breaches_total` | Counter | > 10/min | Broker rate limit violations |
| `broker_requests_failure_total` | Counter | > 5/min | All broker failures |

### Grafana Dashboards

1. **System Overview** — CPU, memory, disk, network
2. **API Performance** — Request duration, error rates, endpoints
3. **Broker Health** — Latency per broker, failure rates, circuit breaker states
4. **Market Data** — Tick rates, WebSocket connections, reconnection events

## Logging

Logs are structured JSON, written to stdout for container environments.

### Log Levels

- `ERROR`: System failures, broker connection losses, order failures
- `WARNING`: Rate limit approaching, token expiry, slow operations (>1s)
- `INFO`: Order placements, user logins, strategy starts
- `DEBUG`: Detailed broker request/response (do NOT enable in production)

### Log Shipping

Configure `fluentd` or `logstash` to forward logs from Docker to your SIEM:

```bash
docker plugin install grafana/loki-docker-driver:latest --alias loki
docker compose -f infra/docker-compose.yml --log-driver=loki up -d
```

## Backup

### PostgreSQL (Supabase)

```bash
# Full backup
supabase db dump -f backups/full_$(date +%Y%m%d).sql

# Scheduled (cron)
0 3 * * * supabase db dump -f backups/full_$(date +\%Y\%m\%d).sql
```

### Redis

```bash
# Save RDB snapshot
redis-cli SAVE

# Copy from container
docker cp trademetrix-redis:/data/dump.rdb backups/redis_$(date +%Y%m%d).rdb
```

### Retention Policy

- Daily backups: 14 days
- Weekly backups: 3 months
- Monthly backups: 1 year

## Routine Maintenance

### Daily

1. Check `/health` returns 200
2. Verify WebSocket connections count
3. Monitor broker token refresh logs
4. Review error rate in Grafana

### Weekly

1. Review circuit breaker stats
2. Check Redis memory usage
3. Verify backup completeness
4. Rotate broker tokens if needed

### Monthly

1. OS security patches
2. Docker image updates
3. Dependency audit (`npm audit`, `pip audit`)
4. Performance review

## Incident Response

See `RUNBOOK.md` for detailed incident procedures.

---

## Broker Setup: Fyers OAuth

### Environment Configuration

#### Local Development (`apps/api/.env`)

```ini
# Fyers App credentials (from https://myapi.fyers.in)
FYERS_APP_ID=<your_app_id>            # e.g. XXXXXXXXXX-XXX
FYERS_APP_SECRET=<your_app_secret>    # 16-char alphanumeric

# Fyers redirect URI — must match EXACTLY one of the URIs registered in the Fyers dashboard
fyers_redirect_uri=http://localhost:8000/api/v1/brokers/fyers/callback

# Frontend URL — where the OAuth callback redirects the browser after success
# Must match the frontend dev server port
frontend_url=http://localhost:3000

# Broker API timeouts
broker_request_timeout=10
broker_connect_timeout=8
```

#### Staging (`infra/staging/.env` or CI secrets)

```ini
fyers_redirect_uri=https://staging-api.trademetrix.tech/api/v1/brokers/fyers/callback
frontend_url=https://staging.trademetrix.tech
broker_request_timeout=8
broker_connect_timeout=5
```

#### Production (`infra/production/.env` or deployment secrets)

```ini
fyers_redirect_uri=https://api.ai.trademetrix.tech/api/v1/brokers/fyers/callback
frontend_url=https://ai.trademetrix.tech
broker_request_timeout=8
broker_connect_timeout=5
```

### Fyers App Dashboard Guide

#### 1. Create or Edit a Fyers App

1. Go to [https://myapi.fyers.in](https://myapi.fyers.in)
2. Log in with your Fyers trading credentials
3. Click **My Apps** in the left sidebar
4. Click **Create App** (or click your existing app to edit)
5. Fill in:
   - **App Name**: `TradeMetrix`
   - **App Type**: `WEB` (required for OAuth redirect flow)
   - **Description**: `Automated trading terminal`

#### 2. Configure Redirect URI

1. Under **Redirect URL**, enter the EXACT callback URL for your environment:

   | Environment | Redirect URL |
   |-------------|-------------|
   | Production | `https://api.ai.trademetrix.tech/api/v1/brokers/fyers/callback` |
   | Staging | `https://staging-api.trademetrix.tech/api/v1/brokers/fyers/callback` |
   | Local Dev | `http://localhost:8000/api/v1/brokers/fyers/callback` |

2. **Important**: Fyers allows only ONE redirect URI per app. If you need multiple environments, either:
   - Create separate Fyers apps per environment (recommended), OR
   - Use a single app with a production callback, and test locally by copying the `auth_code` from the redirected URL manually.

#### 3. Configure API Permissions

Enable the following permissions (the adapter calls these endpoints):

| Permission | Endpoint | Required For |
|-----------|----------|-------------|
| ✅ **Orders** | `POST /api/v3/orders`, `GET /api/v2/orders` | Place, modify, cancel, list orders |
| ✅ **Positions** | `GET /api/v2/positions` | View current positions |
| ✅ **Holdings** | `GET /api/v2/holdings` | View delivery holdings |
| ✅ **Funds** | `GET /api/v2/funds` | View margin and available funds |
| ✅ **Order History** | `GET /api/v2/orders` | Trade journal and P&L calculation |
| ✅ **Quotes** | `POST /data/quotes` | Live market quotes |
| ✅ **Historical Data** | `POST /data/history` | Charts and backtesting |
| ✅ **WebSocket** | `fyers_apiv3` SDK | Real-time tick stream |
| ✅ **Margin** | `POST /api/v3/span_margin` | Pre-order margin estimation |

#### 4. Save and Get Credentials

1. Click **Save**
2. Copy:
   - **App ID**: Looks like `XXXXXXXXXX-XXX` (e.g. `PKL4EMD8ML-200`)
   - **App Secret**: 16-character alphanumeric string (e.g. `luJcw8FFkWMRJebK`)
3. Store these securely — the Secret is shown once

#### 5. Create Supabase Storage Table (if missing)

The `broker_credentials` table must exist in Supabase:

```sql
CREATE TABLE IF NOT EXISTS broker_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    broker TEXT NOT NULL,
    encrypted_api_key TEXT NOT NULL,
    encrypted_secret_key TEXT NOT NULL,
    encrypted_access_token TEXT DEFAULT '',
    encrypted_refresh_token TEXT DEFAULT '',
    token_expires_at TIMESTAMPTZ,
    token_status TEXT DEFAULT 'pending',
    last_token_refresh_at TIMESTAMPTZ,
    additional_params JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_broker_credentials_user ON broker_credentials(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_broker_credentials_user_broker ON broker_credentials(user_id, broker);
```

### OAuth Flow Verification Checklist

After configuration, run through every step:

```
Step 1:  ✓ Login page opens at Fyers (https://api-t1.fyers.in/api/v3/generate-authcode?...)
Step 2:  ✓ User authenticates on Fyers login page
Step 3:  ✓ Fyers redirects browser to callback URL with auth_code and state
Step 4:  ✓ Backend receives POST to /api/v1/brokers/fyers/callback
Step 5:  ✓ State parameter validated against Redis cache
Step 6:  ✓ auth_code exchanged for access_token at Fyers API
Step 7:  ✓ access_token encrypted and stored in broker_credentials table
Step 8:  ✓ is_active set to TRUE
Step 9:  ✓ Browser redirected to frontend with ?auth_success=1
Step 10: ✓ Broker status shows "Active" on Brokers page
```

**Programmatic verification** (run after a successful OAuth):

```bash
# 1. Check credentials are stored (authenticated API call)
curl -s -H "Authorization: Bearer $(YOUR_JWT)" \
  http://localhost:8000/api/v1/brokers/credentials

# Expected: fyers entry shows is_active=true

# 2. Test broker session
curl -s -H "Authorization: Bearer $(YOUR_JWT)" \
  http://localhost:8000/api/v1/engine/token-status

# Expected: {"status":"valid","broker":"fyers"}

# 3. Fetch funds
curl -s -H "Authorization: Bearer $(YOUR_JWT)" \
  http://localhost:8000/api/v1/funds?broker=fyers

# Expected: {"funds":{...}} with real margin data (not zeros)

# 4. Fetch positions
curl -s -H "Authorization: Bearer $(YOUR_JWT)" \
  http://localhost:8000/api/v1/positions?broker=fyers

# Expected: {"positions":[...],"broker":"fyers"}

# 5. Run PAT suite (98 tests)
cd apps/api && python3 pat_test.py
# Expected: Passed: 98/98 (100.0%)
```

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "redirect_uri mismatch" at Fyers login | Auth URL redirect_uri doesn't match Fyers app dashboard | Check `fyers_redirect_uri` env var matches exactly what's registered at https://myapi.fyers.in |
| Callback returns "Invalid or expired state parameter" | Redis state TTL expired (600s) or Redis is down | Complete OAuth within 10 minutes; check `redis-cli PING` |
| Callback returns "No Fyers credentials found" | User hasn't saved App ID/Secret first | Save credentials via Brokers page before re-auth |
| Token exchange returns "invalid auth code" | auth_code already used or expired (5min TTL) | Generate new auth URL and retry immediately |
| `get_funds()` returns empty after success | Token valid but no trading data (market closed, no positions) | Expected — verify during market hours or with active positions |
| `engine/token-status` shows "expired" | Fyers JWT token expired (24h lifetime) | Click "Re-auth" on Brokers page to generate new token |
| PAT test suite fails after config change | Port/URL mismatch | Verify `API_BASE` in `pat_test.py` matches server port: `http://localhost:8000/api/v1` |
| WebSocket won't connect | Token expired, or unsupported symbol | Verify token valid, check symbol is in Fyers supported list |
