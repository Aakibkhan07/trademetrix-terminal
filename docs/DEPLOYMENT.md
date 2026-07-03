# TradeMetrix Terminal — Production Deployment Guide

## Server Requirements

### Minimum (single VPS, $30-50/mo)
| Resource | Value |
|----------|-------|
| vCPU | 2 cores @ 2.5GHz |
| RAM | 4 GB |
| Disk | 40 GB SSD |
| Bandwidth | 2 TB/mo |
| OS | Ubuntu 22.04 / Debian 12 |

### Recommended (single VPS, $80-120/mo)
| Resource | Value |
|----------|-------|
| vCPU | 4 cores @ 3.0GHz |
| RAM | 8 GB |
| Disk | 80 GB NVMe |
| Bandwidth | 4 TB/mo |
| OS | Ubuntu 24.04 / Debian 12 |

### High-availability (multi-node, $200+/mo)
| Node | Spec | Runs |
|------|------|------|
| Backend (×2) | 4 vCPU, 8 GB RAM | API, Redis |
| Frontend (×2) | 2 vCPU, 4 GB RAM | Next.js, Nginx |
| Monitoring | 2 vCPU, 4 GB RAM | Prometheus, Grafana, Node Exporter |
| Database | Managed (Supabase) | PostgreSQL |

---

## Ports Used

| Port | Service | Protocol | Public | Notes |
|------|---------|----------|--------|-------|
| 80 | Nginx | HTTP | Yes | Redirects to HTTPS |
| 443 | Nginx | HTTPS | Yes | SSL termination |
| 8000 | FastAPI | HTTP | No (internal) | Backend workers |
| 3000 | Next.js | HTTP | No (internal) | Frontend SSR |
| 6379 | Redis | TCP | No | Cache, rate-limit storage |
| 9090 | Prometheus | HTTP | No | Metrics DB, bound to 127.0.0.1 |
| 9100 | Node Exporter | HTTP | No | OS metrics, bound to 127.0.0.1 |
| 3001 | Grafana | HTTP | No | Dashboards (proxied via nginx to 443) |

---

## Environment Variables

See `infra/.env.production.example` for the complete reference.

### Required (no app startup without these)
```
SUPABASE_URL
SUPABASE_SERVICE_KEY
SUPABASE_ANON_KEY
SECRET_KEY
ENCRYPTION_KEY
```

### Strongly recommended
```
GEMINI_API_KEY        — AI signals, chat
REDIS_URL             — Caching (default: redis://redis:6379/0)
SENTRY_DSN            — Error tracking
TRADINGVIEW_WEBHOOK_SECRET  — Webhook signature verification
```

### Generation commands
```bash
SECRET_KEY=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(openssl rand -base64 32)
echo "SECRET_KEY=$SECRET_KEY"
echo "ENCRYPTION_KEY=$ENCRYPTION_KEY"
```

---

## Estimated RAM

| Service | Idle | Under Load | Peak |
|---------|------|------------|------|
| FastAPI (2 workers) | 120 MB | 200 MB | 400 MB |
| Next.js | 80 MB | 150 MB | 300 MB |
| Redis | 5 MB | 50 MB | 200 MB (maxmemory) |
| Nginx | 10 MB | 30 MB | 80 MB |
| Prometheus | 100 MB | 200 MB | 500 MB |
| Grafana | 80 MB | 120 MB | 200 MB |
| Node Exporter | 10 MB | 15 MB | 20 MB |
| **Total** | **~400 MB** | **~800 MB** | **~1.7 GB** |

---

## Estimated CPU

| Service | Idle | Under Load |
|---------|------|------------|
| FastAPI (2 workers) | 2% | 60-80% (per core) |
| Next.js | 1% | 40-60% |
| Redis | 0.5% | 10% |
| Nginx | 0.5% | 20% |
| Prometheus | 3% | 10% |
| Grafana | 1% | 5% |
| **Total** | **~8%** | **~150%** (1.5 cores) |

---

## Architecture

```
                         ┌─────────────┐
                         │   Cloudflare │  (optional CDN + DDoS)
                         └──────┬──────┘
                                │ :443
                         ┌──────▼──────┐
                         │   Nginx      │  SSL termination, rate limiting,
                         │   (reverse   │  gzip, security headers
                         │    proxy)    │
                         └──┬──────┬───┘
                            │      │
                   :3000    │      │  :8000
              ┌─────────────▼┐  ┌──▼──────────────┐
              │  Next.js     │  │  FastAPI         │
              │  (SSR)       │  │  (2+ workers)    │
              └──────────────┘  └──┬───────────────┘
                                   │
                            ┌──────▼──────┐
                            │   Redis     │  Session, rate-limit, cache
                            │   (7-alpine) │
                            └─────────────┘
                                   │
                            ┌──────▼──────┐
                            │  Supabase   │  PostgreSQL, Auth, Realtime
                            │  (external) │
                            └─────────────┘

  Monitoring:
  ┌──────────┐  ┌──────────┐  ┌──────────────┐
  │Prometheus│  │ Grafana  │  │ Node Exporter│
  │ :9090    │  │ :3001    │  │ :9100        │
  └──────────┘  └──────────┘  └──────────────┘
```

---

## Deployment

### Prerequisites
```bash
# VPS (Ubuntu 24.04)
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-v2 git curl ufw

# Firewall
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# Clone repo
git clone https://github.com/Aakibkhan07/trademetrix-terminal.git /opt/trademetrix
cd /opt/trademetrix
```

### Environment setup
```bash
# Create .env files from examples
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env

# Generate secrets
SECRET_KEY=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(openssl rand -base64 32)
sed -i "s/SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" apps/api/.env
sed -i "s/ENCRYPTION_KEY=.*/ENCRYPTION_KEY=$ENCRYPTION_KEY/" apps/api/.env

# Edit with your Supabase credentials
nano apps/api/.env
nano apps/web/.env
```

### Deploy
```bash
# One-command deploy
bash infra/production/deploy.sh

# Or manually:
docker compose -f infra/docker-compose.yml pull redis
docker compose -f infra/docker-compose.yml build --parallel api web
docker compose -f infra/docker-compose.yml up -d
```

### Verify
```bash
curl -f https://api.ai.trademetrix.tech/health
curl -f https://api.ai.trademetrix.tech/health/ready
curl -f https://ai.trademetrix.tech
```

### First-time SSL (certbot)
```bash
docker compose -f infra/docker-compose.yml run --rm certbot certonly --webroot \
  -w /var/www/certbot \
  -d ai.trademetrix.tech \
  -d api.ai.trademetrix.tech \
  -d monitor.ai.trademetrix.tech
```

---

## Rollback

```bash
# Rollback to previous version
bash infra/rollback.sh

# Rollback to specific tag
bash infra/rollback.sh v1.0.0-beta
```

---

## Backup & Restore

### Backup
```bash
# Manual
bash apps/api/scripts/backup.sh

# Automated (cron)
0 2 * * * /opt/trademetrix/apps/api/scripts/backup.sh >> /var/log/trademetrix-backup.log 2>&1
```

### Restore
```bash
bash apps/api/scripts/restore.sh /path/to/backup.dump
```

---

## Monitoring

### Metrics endpoints
| Endpoint | Description |
|----------|-------------|
| `GET /health` | Basic health (status, version, uptime) |
| `GET /health/live` | Liveness probe |
| `GET /health/ready` | Readiness probe (checks DB + Redis) |
| `GET /health/metrics` | Application metrics (request count, latency, errors) |
| `GET /metrics` | Prometheus metrics |

### Prometheus alert rules
Alerts defined in `infra/prometheus/alerts/trademetrix.yml`:
- APIHighLatency — p50 latency > 2s for 5 min
- APIHighErrorRate — 5xx rate > 5%
- InstanceDown — any target unreachable
- HighCPUUsage — CPU > 80% for 10 min
- HighMemoryUsage — memory > 85% for 10 min
- DiskSpaceLow — disk < 10%

### Grafana dashboards
- Pre-provisioned at `/grafana/dashboards/`
- Auto-imported on container start
- Default: `monitor.ai.trademetrix.tech` (user: admin, password from `GRAFANA_PASSWORD` env)

---

## Scaling Guide

### Vertical (single larger VPS)
| Tier | Users | Spec |
|------|-------|------|
| Starter | 1-10 | 2 vCPU, 4 GB RAM |
| Growth | 10-50 | 4 vCPU, 8 GB RAM |
| Scale | 50-200 | 8 vCPU, 16 GB RAM |

### Horizontal (multi-node)

**When to scale horizontally:**
- API consistently > 60% CPU
- p99 latency > 1s
- Redis eviction rate > 0

**Add API replicas:**
```yaml
# docker-compose.yml
api:
  deploy:
    replicas: 3
  environment:
    WORKER_COUNT: 4
```

**Add Nginx + frontend replicas:**
- Deploy separate frontend nodes behind a load balancer
- Use Cloudflare or AWS ALB for multi-region

**Database:**
- Supabase manages scaling automatically
- For self-hosted Postgres: add read replicas, enable PgBouncer for connection pooling

### Stateless design
All services are stateless:
- Sessions in Redis
- Files on S3-compatible storage
- No `localStorage` or sticky sessions needed
- Horizontal scale by adding containers behind a load balancer

---

## Security Checklist

- [ ] HTTPS enforced (SSL redirect on nginx)
- [ ] HSTS enabled (max-age=63072000)
- [ ] X-Content-Type-Options: nosniff
- [ ] X-Frame-Options: DENY
- [ ] Permissions-Policy restricts camera/mic/geolocation
- [ ] Rate limiting on all API endpoints (30 req/s, 3 req/m on login)
- [ ] CSRF protection via double-submit cookie pattern
- [ ] Webhook secret validates TradingView payloads
- [ ] Sentry error tracking (no PII in logs)
- [ ] Containers run as non-root users (UID 1001)
- [ ] no-new-privileges security flag on containers
- [ ] read_only root filesystem on API containers
- [ ] PrivateTmp for systemd services
- [ ] Firewall restricts all ports except 22, 80, 443
- [ ] Prometheus/Grafana bound to 127.0.0.1 (not publicly exposed)
- [ ] Log rotation (30-day retention, 100 MB max per file)

---

## Maintenance

### Update application
```bash
cd /opt/trademetrix
git pull origin main
docker compose -f infra/docker-compose.yml build --parallel api web
docker compose -f infra/docker-compose.yml up -d
```

### View logs
```bash
# All services
docker compose -f infra/docker-compose.yml logs -f

# Single service
docker compose -f infra/docker-compose.yml logs -f api
docker compose -f infra/docker-compose.yml logs -f web
docker compose -f infra/docker-compose.yml logs -f nginx
```

### Restart service
```bash
docker compose -f infra/docker-compose.yml restart api
```

### Full stop
```bash
docker compose -f infra/docker-compose.yml down
docker compose -f infra/docker-compose.yml down -v  # ⚠️ destroys volumes
```
