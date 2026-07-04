# Trade Metrix Terminal — Deployment Guide

## Prerequisites

- Docker 24+ and Docker Compose v2
- Python 3.12+ (for local dev)
- Node.js 20+ (for frontend builds)
- `aws` CLI + `gpg` (for backup/restore scripts)

## Quick Start (Dev)

```bash
# 1. Start Supabase local
npx supabase start

# 2. Set up API
cd apps/api
cp .env.example .env   # fill in Supabase keys
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# 3. Run migrations
alembic upgrade head

# 4. Start API
uvicorn main:app --reload --port 8000

# 5. Start frontend
cd apps/web
cp .env.example .env
npm install
npm run dev
```

## Staging Deployment

```bash
cd infra/staging

# Set required env vars
export SENTRY_DSN="https://..."
export GRAFANA_PASSWORD="secure_password"

# Start all services
docker compose -f docker-compose.yml up -d --build

# Verify health
curl http://localhost:8000/health/ready
curl http://localhost:3000/

# Access monitoring
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3001 (admin / $GRAFANA_PASSWORD)
```

## Production Deployment

### 1. Database (Supabase/PostgreSQL)

- Use managed PostgreSQL (Supabase, RDS, Cloud SQL)
- Enable point-in-time recovery
- Set up read replicas for heavy query loads
- Connection pooling via PgBouncer (included with Supabase)

### 2. API (Docker / ECS / K8s)

```bash
# Build production image
docker build -t trademetrix-api:latest apps/api

# Run with env vars
docker run -d \
  --name trademetrix-api \
  -p 8000:8000 \
  -e SUPABASE_URL="..." \
  -e SUPABASE_SERVICE_KEY="..." \
  -e SECRET_KEY="..." \
  -e DOTENV_KEY="..." \
  -e SENTRY_DSN="..." \
  -e REDIS_URL="redis://..." \
  trademetrix-api:latest
```

Environment variables required:
| Variable | Description |
|---|---|
| `SUPABASE_URL` | PostgreSQL/API endpoint |
| `SUPABASE_SERVICE_KEY` | Service role key |
| `SECRET_KEY` | JWT signing key (32+ chars) |
| `DOTENV_KEY` | Vault decryption key |
| `SENTRY_DSN` | Sentry project DSN |

### 3. Web (Vercel / Docker)

```bash
# Build
docker build -t trademetrix-web:latest apps/web

# Run
docker run -d --name trademetrix-web -p 3000:3000 \
  -e NEXT_PUBLIC_API_URL="https://api.ai.trademetrix.tech" \
  trademetrix-web:latest
```

### 4. Redis

- Use ElastiCache / Memorystore / Upstash
- Enable encryption in transit + at rest
- Multi-AZ for high availability

### 5. Load Balancer

- Terminate TLS at LB
- Forward `/api/*` → API target group
- Forward `/*` → Web target group
- Health check path: `/health/live`

## Backup & Disaster Recovery

### Automated Backups

```bash
# Run backup (via cron: every 6h)
PG_HOST=localhost PG_PORT=54322 \
  S3_BUCKET=trademetrix-backups \
  BACKUP_ENCRYPTION_KEY="..." \
  bash apps/api/scripts/backup.sh
```

### Restore

```bash
bash apps/api/scripts/restore.sh backups/trademetrix_20241201_120000.dump
```

### DR Plan

1. **DB failure**: Restore latest backup to new Supabase project, update `SUPABASE_URL` env var, restart API
2. **API failure**: Auto-restart via Docker restart policy / K8s liveness probe; if permanent, shift traffic to standby replica
3. **Region failure**: Have DR stack in secondary region with replicated DB; swap DNS to DR load balancer
4. **Data corruption**: Restore pre-corruption backup, replay audit logs to rebuild state

## Monitoring & Alerting

- **Sentry**: Alert on `p95 > 1s`, error rate > 1%, 5xx spikes
- **Prometheus**: Track `http_requests_total`, `circuit_breaker_state`, `process_memory_bytes`
- **Grafana**: Dashboards for request latency, error rates, market data throughput, system resources
- **Health endpoints**:
  - `GET /health/live` — liveness (always 200)
  - `GET /health/ready` — readiness (checks DB + Redis)

## Scaling

| Component | Vertical | Horizontal |
|---|---|---|
| API | 4 vCPU / 8GB RAM min | 3+ replicas behind LB |
| Web | 2 vCPU / 4GB RAM | Stateless — scale freely |
| PostgreSQL | 8 vCPU / 32GB RAM | Read replicas for analytics |
| Redis | 4GB RAM | Cluster mode for larger cache |

## Multi-Region HA

- Deploy stacks in 2+ regions
- PostgreSQL: cross-region replication (Supabase project clones)
- Redis: Global Datastore (Upstash) or active-passive
- DNS: Route53 latency-based routing with health checks
- Trade-off: Cross-region DB replication latency (~50-200ms) may stale quotes/orders momentarily
