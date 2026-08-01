# Deployment Guide — TradeMetrix Terminal v1.0.0 (GA)

## Architecture

```
                    ┌─────────────────────┐
   Internet ───────▶│  Caddy (443, TLS)   │  https://ai.trademetrix.tech
                    └──────┬───────┬──────┘  https://api.ai.trademetrix.tech
                           │       │
                  ┌────────▼───┐ ┌─▼───────────┐
                  │  web:3000  │ │  api:8000   │  FastAPI + Uvicorn (1 worker)
                  │  Next.js   │ │  (FastAPI)  │
                  └────────────┘ └──┬─────┬────┘
                                    │     │
                     ┌──────────────▼──┐ ┌▼──────────────┐
                     │  Supabase (PaaS)│ │  redis:6379   │
                     │  Postgres 17.6  │ │  cache/queue  │
                     │  (remote, RLS)  │ └───────────────┘
                     └─────────────────┘
   Observability: trademetrix_prometheus (127.0.0.1:9090, 30d retention),
   trademetrix_grafana (https://monitor.ai.trademetrix.tech),
   node-exporter, redis-exporter, trademetrix_autoheal
   Side stack on same host: trademetrix-n8n, analyzer-frontend-1, analyzer-backend-1
```

- **Host**: single VPS `187.127.185.56` (Ubuntu, Docker 24+, 8 GB RAM class)
- **Repo**: `https://github.com/Aakibkhan07/trademetrix-terminal` (public, branch `main`) — the ONLY source of truth for deployment
- **Images**: built on the VPS from the repo (`docker compose build`). No image registry.
- **Database**: managed Supabase (`db.nwutlfuowiulfpbsrldn.supabase.co:5432`, PostgreSQL 17.6). RLS on; the API uses the service-role key (`get_supabase()`).

## Prerequisites (fresh host)

Nothing to install manually — `deploy.sh` installs Docker + Compose if missing. You only need:

1. SSH access to the host (`root@187.127.185.56`; credentials in password manager)
2. The untracked env files, which are NEVER in git (see below)
3. DNS records: `ai.trademetrix.tech`, `api.ai.trademetrix.tech`, `monitor.ai.trademetrix.tech` → host IP (Caddy auto-provisions TLS)

## Environment files (not in git)

These files exist ONLY on the VPS (`.gitignore`d) and are required:

```
apps/api/.env                    # Supabase URL + service key, SECRET_KEY, FYERS creds, ...
apps/web/.env                    # NEXT_PUBLIC_* (API base URL)
apps/web/.env.production         # used for prod builds
infra/production/.env.production # compose interpolations (GRAFANA_PASSWORD, ...)
```

Backup of all env files is included in `backup.sh` (`env/` in each backup dir).

## Deploy (single command)

```bash
ssh root@187.127.185.56
cd /root/trademetrix-terminal
bash infra/production/deploy.sh
```

What `deploy.sh` does (non-interactive, safe to re-run):

1. Installs Docker/Compose if missing
2. `git fetch origin && git reset --hard origin/main` (env files are untracked → survive)
3. Fails fast if required env files are missing
4. Injects `OPENROUTER_API_KEY` into `apps/api/.env` ONLY if the env var is set AND the key is absent (never prompts)
5. Advisory DNS check (compares resolver IP vs `ifconfig.me`)
6. `docker compose -f infra/production/docker-compose.yml build --parallel api web`
7. `docker compose ... up -d`
8. Health gates — waits up to 18 × 10 s for BOTH:
   - `https://api.ai.trademetrix.tech/health` → 200
   - `https://ai.trademetrix.tech/` → 200
9. Prints `Deployment Complete — v1.0 GA` or a FAIL message with `docker compose logs api web` tips (exit 1)

Expected output tail:

```
[OK] health gate: api    https://api.ai.trademetrix.tech/health -> 200
[OK] health gate: web    https://ai.trademetrix.tech/ -> 200
Deployment Complete — v1.0 GA
```

## Manual verification after deploy

```bash
curl -s https://api.ai.trademetrix.tech/health                      # {"status":"ok",...}
curl -s https://api.ai.trademetrix.tech/health/ready               # DB + cache deps
curl -s -o /dev/null -w '%{http_code}\n' https://ai.trademetrix.tech/backtest   # 200
docker ps --format 'table {{.Names}}\t{{.Status}}'                 # all healthy
```

## Database migrations

Migrations live in `supabase/migrations/` (14 files, all idempotent `IF NOT EXISTS`). Two paths:

- **Local dev**: `docker exec -it supabase_db_trademetrix-terminal psql -U postgres -d postgres -f /dev/stdin < supabase/migrations/<file>.sql` (or the Supabase CLI)
- **Production (remote)**: apply via any Postgres client:

```bash
PGPASSWORD='<supabase-db-password>' psql "postgresql://postgres@db.nwutlfuowiulfpbsrldn.supabase.co:5432/postgres?sslmode=require" -f supabase/migrations/<file>.sql
```

Order matters — apply in filename order. All GA migrations are already applied to prod (verified 2026-08-01). New tables come with RLS enabled; the API uses the service-role key and is unaffected.

## Rollback

```bash
# App code — previous commit, same single command
cd /root/trademetrix-terminal
git log --oneline -5                       # pick the last known-good sha
git checkout <sha> && bash infra/production/deploy.sh
```

Database rollback: Supabase dashboard → Database → Backups (PITR or scheduled restore). Migrations since GA have been additive-only, so rolling back code to a commit whose schema is a subset of prod is safe.

## Operations handover

- Backup: `bash /root/trademetrix-terminal/infra/scripts/backup.sh` → `/root/trademetrix-backups/` (see `BACKUP_RESTORE.md`)
- Restore/disaster recovery: see `DISASTER_RECOVERY.md`
- Day-to-day: see `RUNBOOK.md`
- Known gaps: see `KNOWN_ISSUES.md`
