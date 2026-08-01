# TradeMetrix Production Runbook

> v1.0.0 GA — 2026-08-01. Host `187.127.185.56`, repo `Aakibkhan07/trademetrix-terminal` (main).

## Architecture

```
                         ┌──────────────┐
                         │   Caddy (443) │
                         │  reverse_proxy│
                         └──────┬───────┘
                                │
              ┌─────────────────┼──────────────────┐
              │                 │                   │
     ┌────────▼────────┐ ┌─────▼──────┐  ┌─────────▼─────────┐
     │  api:8000        │ │ web:3000   │  │ grafana:3000      │
     │  FastAPI + Uvicorn│ │ Next.js    │  │ Dashboards + Alerts│
     └────────┬─────────┘ └────────────┘  └─────────┬──────────┘
              │                                     │
     ┌────────▼─────────┐                  ┌────────▼──────────┐
     │  redis:6379       │                  │ prometheus:9090   │
     │  Cache + Queue    │◄─────────────────│ Scrapes /metrics  │
     └───────────────────┘                  └───────────────────┘
                                                    │
                                        ┌───────────┼───────────┐
                                        │           │           │
                              ┌─────────▼──┐ ┌─────▼─────┐ ┌───▼────────┐
                              │ node-exporter│ │redis-     │ │caddy:2019  │
                              │ :9100       │ │exporter   │ │ /metrics   │
                              └─────────────┘ │:9121      │ └────────────┘
                                               └───────────┘
```

## Health Endpoints

| Endpoint | Description | Expected Response |
|----------|-------------|-------------------|
| `GET /health` | Basic health | `{"status":"ok", "uptime_seconds": N}` |
| `GET /health/live` | Liveness probe | `{"status":"alive"}` |
| `GET /health/ready` | Readiness (DB + Cache) | `{"status":"ok", "dependencies": {...}}` |
| `GET /health/metrics` | Process + request stats | JSON with system, requests, circuit_breakers |
| `GET /metrics` | Prometheus scrape endpoint | Prometheus text format |

## Monitoring Stack

- **Prometheus**: `http://prometheus:9090` (internal) — 30d retention
- **Grafana**: `https://monitor.ai.trademetrix.tech` — provisioned dashboards + datasources
- **Alert Rules**: `/etc/prometheus/alerts/trademetrix.yml`
- **Sentry**: DSN not configured — set `SENTRY_DSN` in `.env` to enable

## Key Metrics (Prometheus)

### API
- `http_requests_total{method, path, status}` — Request count by status
- `http_request_duration_seconds_bucket{method, path}` — Latency histogram
- `api_health_status` — 1 = healthy, 0 = unhealthy
- `active_connections` — WebSocket connections
- `process_memory_bytes{type}` — RSS / VMS memory
- `process_cpu_percent` — Process CPU %

### Database
- `db_query_duration_seconds_bucket{table, operation}` — Supabase query latency

### Broker
- `broker_request_duration_seconds_bucket{broker, operation}` — Broker API latency
- `broker_requests_success_total{broker, operation}` — Successful calls
- `broker_requests_failure_total{broker, operation}` — Failed calls
- `circuit_breaker_state{breaker}` — 0=closed, 1=half, 2=open
- `rate_limit_breaches_total{broker}` — Rate limit hits

### Orders
- `orders_failed_total{status}` — rejected, cancelled, expired, error

### System
- `exceptions_total{type}` — Unhandled exceptions by type
- `active_strategies` — Running strategy engines
- `active_broker_sessions` — Broker sessions active

### Market
- `market_ticks_total{broker}` — Tick count
- `market_ticks_errors_total{error_type}` — Tick errors
- `market_ticks_reconnects_total{broker}` — Reconnects

### Redis (via redis-exporter)
- `redis_memory_used_bytes`
- `redis_connected_clients`
- `redis_keyspace_hits_total` / `redis_keyspace_misses_total`

### Caddy (via admin API :2019/metrics)
- `caddy_http_requests_total`
- `caddy_http_request_duration_seconds`

## Alert Rules

| Alert | Severity | Condition | Action |
|-------|----------|-----------|--------|
| APIHighLatency | warning | Avg latency >2s for 5m | Check for slow DB queries or broker calls |
| APIP99Latency | warning | P99 >5s for 5m | Same as above, investigate slow endpoints |
| APIHighErrorRate | critical | 5xx rate >5% for 5m | Check logs, Sentry, recent deployment |
| APIUnhealthy | critical | health check fails for 1m | API process may be hung or OOM |
| InstanceDown | critical | `up == 0` for 1m | Container crashed — check docker logs |
| HighCPUUsage | warning | CPU >80% for 10m | Check for runaway loops, too many ticks |
| HighMemoryUsage | warning | Memory >85% for 10m | Check for memory leak, reduce cache TTL |
| DiskSpaceLow | critical | Disk <10% | Clean logs, increase volume size |
| RedisDown | critical | `redis_up == 0` for 1m | Redis process crashed — restart container |
| BrokerFailureRate | warning | >20% failures for 5m | Broker API down or rate-limited |
| CircuitBreakerOpen | critical | Breaker open for 1m | Broker API unavailable — check credentials |
| OrderFailureRate | warning | >0.1/s failed for 5m | Paper/live broker issue |
| HighExceptionRate | critical | >0.05/s for 5m | Unhandled exceptions — check logs |

## Runbooks

### 1. API Latency Spike

1. Check `/health/metrics` for slow endpoints
2. Check DB query latency (`db_query_duration_seconds`)
3. Check broker latency (`broker_request_duration_seconds`)
4. Check for event loop blocking (`event_loop_blocked_seconds`)
5. Check log: `docker logs trademetrix_api --tail 100`
6. If sustained, restart API: `docker restart trademetrix_api`

### 2. Circuit Breaker Open

1. Identify which broker: Prometheus `circuit_breaker_state`
2. Check broker credentials: `GET /api/v1/brokers/credentials`
3. Check broker status page / API health
4. If credentials expired, re-authenticate via `/api/v1/brokers/{broker}/re-auth`
5. If broker API down, wait for recovery (automatic backoff)
6. To force reset: `docker exec trademetrix_api python3 -c "from core.resilience import force_reset; force_reset('broker_fyers')"`

### 3. High Memory Usage

1. Check `process_memory_bytes{type="rss"}` vs container limit (768m)
2. Check number of WebSocket connections (`active_connections`)
3. Check Redis memory (`redis_memory_used_bytes`)
4. If API OOM: `docker logs trademetrix_api --tail 50 | grep -i "killed\|oom\|memory"`
5. Restart API: `docker restart trademetrix_api`
6. If trend continues, increase `mem_limit` in docker-compose

### 4. Redis Down

1. Check Redis health: `docker exec trademetrix_redis redis-cli ping`
2. Check logs: `docker logs trademetrix_redis --tail 50`
3. Restart: `docker restart trademetrix_redis`
4. Verify API recovers (auto-reconnect with 30s cooldown)

### 5. Disk Space Full

1. Check usage: `df -h` and biggest dirs: `du -sh /root/trademetrix-backups /var/lib/docker 2>/dev/null`
2. Clean unused images/build cache (keeps volumes): `docker system prune -af`  (never `--volumes`)
3. Prune old backups (retention is 14 days, runs are manual): `bash /root/trademetrix-terminal/infra/scripts/backup.sh` prunes automatically; manually delete `/root/trademetrix-backups/<old>` if urgent
4. Docker logs are rotated by daemon config (json-file, 10 MB × 3); do NOT `rm -rf /prometheus/*` while running — use the TSDB retention (30d) or `docker compose up -d --force-recreate prometheus`

### 6. Deploy New Code (STANDARD — one command)

```bash
cd /root/trademetrix-terminal
bash infra/production/deploy.sh
```

Rebuilds images from `origin/main`, recreates containers, health-gates API + web, prints `Deployment Complete — v1.0 GA` or exits 1 with log tips. See `DEPLOYMENT.md`.

### 6b. Emergency hot-patch (bypasses image rebuild — single file fix)

```bash
# from a local working copy
tar czf - -C apps/api <path> | ssh root@187.127.185.56 \
  "mkdir -p /tmp/hot && tar xzf - -C /tmp/hot && docker cp /tmp/hot/<path> trademetrix_api:/app/<path> \
   && docker restart trademetrix_api && sleep 12 && \
   curl -s -o /dev/null -w 'health: %{http_code}\n' https://api.ai.trademetrix.tech/health"
```

Always commit the change to git afterwards so `deploy.sh` stays authoritative.

### 7. Deploy Infra / Compose Changes

```bash
cd /root/trademetrix-terminal
git pull origin main                          # pick up infra/production changes
docker compose -f infra/production/docker-compose.yml up -d --remove-orphans
docker compose -f infra/production/docker-compose.yml restart prometheus grafana  # if configs changed
```

### 8. Force Prometheus Config Reload

```bash
docker exec trademetrix_prometheus kill -HUP 1
```

## Logs

- API logs: `docker logs trademetrix_api --tail 100`
- All containers: `docker compose -f /root/trademetrix-terminal/infra/production/docker-compose.yml logs --tail=50 -f`
- Log rotation: json-file driver, max 10MB per file, 3 files max

## Deployment

- **Standard deploy**: `cd /root/trademetrix-terminal && bash infra/production/deploy.sh` (build → up → health gates)
- API hot-patch (emergency only): `tar | docker cp` + `docker restart trademetrix_api` (see §6b) — commit to git afterwards
- Infra changes via `docker compose -f infra/production/docker-compose.yml up -d`
- Caddy reload: `docker exec trademetrix_caddy caddy reload --config /etc/caddy/Caddyfile`
- Backup: `bash /root/trademetrix-terminal/infra/scripts/backup.sh` → `/root/trademetrix-backups/` (14-day retention)

## Credentials

| Service | URL | Auth |
|---------|-----|------|
| Grafana | https://monitor.ai.trademetrix.tech | `GRAFANA_PASSWORD` in `infra/production/.env.production` |
| Prometheus | internal only (127.0.0.1:9090) | None (localhost bind) |
| Caddy | on host (127.0.0.1:2019) | Localhost bind |
| SSH (host) | root@187.127.185.56 | password in password manager |
| Supabase | https://nwutlfuowiulfpbsrldn.supabase.co | Service-role key + DB password in `apps/api/.env` (untracked) + password manager |
| Sentry | N/A | Set `SENTRY_DSN` in `apps/api/.env` to enable |

## Container Resource Limits

| Container | Memory | CPU | 
|-----------|--------|-----|
| api | 768m | 2.0 |
| web | 512m | 0.5 |
| caddy | 128m | 0.5 |
| redis | 256m | 0.5 |
| redis-exporter | 64m | 0.1 |
| prometheus | 512m | 0.5 |
| grafana | 256m | 0.5 |
| node-exporter | 128m | 0.2 |
| market-agent | 256m | 0.5 |
| n8n | 1g | 1.0 |
| autoheal | 32m | 0.1 |

Total allocated: ~2.9GB / 7.8GB available