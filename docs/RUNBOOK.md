# TradeMetrix Terminal — Production Runbook

## Service Topology

```
Caddy (TLS termination) → API (FastAPI :8000) → Redis (:6379)
                        → Web (Next.js :3000)
                        → Postgres (Supabase)
                        → Market Agent (publishes ticks → Redis)
```

Monitoring: Prometheus (:9090) ← Grafana (:3000) | Sentry (errors)

## Health Checks

| Endpoint | What it checks |
|----------|---------------|
| `GET /health` | App alive, returns version + uptime |
| `GET /health/ready` | DB + Redis connectivity |
| `GET /health/live` | Simple liveness (always 200) |
| `GET /metrics` | Prometheus metrics |

Docker auto-heals via `willfarrell/autoheal` — containers with `autoheal=true` label restart on healthcheck failure.

## Deployment

```bash
# staging
docker compose -f infra/staging/docker-compose.yml up -d --build

# production
docker compose -f infra/production/docker-compose.yml up -d --build
```

Secrets come from `.env` files (vault-encrypted). Run migrations:

```bash
cd apps/api && alembic upgrade head
```

## Common Failure Modes

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| API healthcheck failing | DB/Redis unreachable | Check `docker logs trademetrix_api`; verify Supabase status |
| Web shows "API unavailable" | API not healthy; Caddy misconfig | `docker compose ps`; check Caddy logs |
| No market data | Market agent down; Redis full | `docker logs trademetrix_market_agent`; `redis-cli ping` |
| Orders not executing | Broker token expired | Trigger token refresh: `POST /api/v1/auth/me/brokers/<broker>/refresh` |
| OAuth callback fails | Redirect URI mismatch | Verify broker dev console redirect URI matches `settings.*_redirect_uri` |
| Strategy not running | Scheduler not started; heartbeat stale | Check `strategy_health` table; restart runtime_manager |
| OOM / memory spike | LRU cache eviction misconfig | Check market_cache size; verify sweep loop running |

## Logs

```bash
docker logs trademetrix_api -f --tail 100
docker logs trademetrix_market_agent -f
docker logs trademetrix_caddy -f
```

Log level controlled by `LOG_LEVEL` env var (default: `INFO`, set `DEBUG` for troubleshooting).

## Backups

Automatic daily: `docker exec trademetrix_api bash scripts/backup.sh`
Restore: `docker exec trademetrix_api bash scripts/restore.sh <backup_file>`

## Monitoring

- **Grafana**: `https://monitor.ai.trademetrix.tech` — dashboards for API latency, error rates, active strategies, market data throughput
- **Prometheus**: Port 9090 (localhost only) — raw metrics
- **Sentry**: Error tracking — alerts on 5xx spikes
- **Alert rules**: Defined in `infra/prometheus/alerts/` — CpuHigh, MemoryHigh, HealthCheckFailing, HighErrorRate

## Capacity Planning

| Service | Memory | CPU | Storage |
|---------|--------|-----|---------|
| API | 768 MB | 2.0 | — |
| Web | 512 MB | 1.0 | — |
| Redis | 256 MB | 0.5 | 1 GB (data) |
| Market Agent | 256 MB | 0.5 | — |
| Prometheus | 512 MB | 0.5 | 10 GB |
| Grafana | 256 MB | 0.5 | — |
| Caddy | 128 MB | 0.5 | — |

Scale API horizontally behind Caddy if p95 latency exceeds 500ms at peak.

## Recovery

1. **Container crash**: Autoheal restarts within 30s
2. **Full outage**: `docker compose -f infra/production/docker-compose.yml up -d --force-recreate`
3. **Data loss**: Restore from latest backup
4. **Broker outage**: Market agent auto-detects and falls back to cached data; alerts on disconnection
5. **Token expiry**: Automatic refresh on 401; manual trigger via refresh endpoint
