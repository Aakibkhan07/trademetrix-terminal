# Deployment Guide — TradeMetrix Terminal v1.0.0-rc

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Next.js    │────▶│  FastAPI     │────▶│  Supabase    │
│   (web)      │     │  (api)       │     │  (Postgres)  │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
                    ┌───────┴────────┐
                    │   Redis        │
                    │   (cache/ql)   │
                    └────────────────┘
```

## Prerequisites

- Docker 24+ and Docker Compose v2
- Colima or Docker Desktop (macOS)
- Supabase CLI (local dev only)
- Python 3.12+
- Node.js 20+
- Domain with DNS pointing to deployment host

## Environment Configuration

### Required Environment Variables

```bash
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
SUPABASE_ANON_KEY=eyJ...

# Security (generate unique values)
SECRET_KEY=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(openssl rand -hex 32)
CORS_ORIGINS=https://your-frontend.com

# Redis
REDIS_URL=redis://redis:6379/0

# Monitoring
SENTRY_DSN=https://key@oXXXX.ingest.sentry.io/PROJECT
SENTRY_ENV=production

# Broker OAuth Callbacks
FYERS_REDIRECT_URI=https://api.yourdomain.com/v1/broker/fyers/callback
DHAN_REDIRECT_URI=https://api.yourdomain.com/v1/broker/dhan/callback
UPSTOX_REDIRECT_URI=https://api.yourdomain.com/v1/broker/upstox/callback

# Notifications
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## Deployment Steps

### 1. Database Migrations

```bash
# Apply all Supabase migrations
supabase migration up

# Verify schema
supabase db diff --linked
```

### 2. Build & Push Docker Images

```bash
# Build API
docker build -t trademetrix/api:rc-1.0.0 -f infra/api.Dockerfile .
docker push trademetrix/api:rc-1.0.0

# Build Web
docker build -t trademetrix/web:rc-1.0.0 -f infra/web.Dockerfile .
docker push trademetrix/web:rc-1.0.0
```

### 3. Deploy with Docker Compose

```bash
# Set up environment
cp infra/.env.production .env
# Edit .env with production values

# Deploy stack
docker compose -f infra/docker-compose.yml up -d

# Verify all services
docker compose -f infra/docker-compose.yml ps
```

### 4. Health Check

```bash
# API health
curl https://api.yourdomain.com/health

# Database connectivity check
curl https://api.yourdomain.com/health/db

# Full system status
curl https://api.yourdomain.com/v1/admin/system-status
```

### 5. Verify Frontend

```bash
# Check frontend is serving
curl -I https://your-frontend.com

# Verify API proxy works
curl https://your-frontend.com/api/health
```

## Rollback

```bash
# Rollback to previous Docker image tag
docker compose -f infra/docker-compose.yml down
docker compose -f infra/docker-compose.yml up -d

# Database rollback (if migration caused issues)
supabase migration repair --status reverted <offending-migration>
supabase migration up  # Re-apply up to last known good
```

## Blue-Green Deployment

1. Deploy new version to `green` stack
2. Run health checks against green
3. Switch load balancer from blue to green
4. Keep blue running for 15 min observation period
5. Tear down blue after confirmation
