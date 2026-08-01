# Disaster Recovery Plan — TradeMetrix Terminal v1.0.0 (GA)

## Recovery Objectives

| Metric | Target |
|--------|--------|
| RPO (data loss) | 1 h (Supabase PITR/backup schedule) + 14 d VPS backups |
| RTO — single container crash | ~1 min (autoheal restarts unhealthy containers) |
| RTO — app redeploy / corruption | ~15–30 min |
| RTO — complete host loss | ~2–4 h (fresh VPS + `deploy.sh` + backups + Supabase restore) |

The platform has **two independent durability domains**:

1. **Supabase (PaaS)** — Postgres, auth, storage; managed HA + backups. Recovering it is always done in the Supabase dashboard, never from the VPS.
2. **VPS state** — Redis, Prometheus, Grafana, n8n, Caddy certs, env files. Recovered from `/root/trademetrix-backups/` (14-day retention; copy off-host if the host is the failure domain).

## Scenario 1 — Container crash / unhealthy

`trademetrix_autoheal` restarts unhealthy containers automatically (default ~30 s).

```bash
docker ps                                   # check states
docker logs trademetrix_<name> --tail 100   # root cause
docker restart trademetrix_<name>           # manual restart if needed
```

## Scenario 2 — API container broken (bad deploy, code issue)

```bash
cd /root/trademetrix-terminal
git log --oneline -5                        # find last known-good sha
git checkout <sha>
bash infra/production/deploy.sh             # rebuild + health gates, exit 1 on failure
```

The deploy script's health gates (API `/health` + web 200) decide success. Env files survive checkout/reset (untracked).

## Scenario 3 — Redis loss / corruption

Redis is non-critical (graceful degradation everywhere). Restore from backup if available (see `BACKUP_RESTORE.md`), otherwise:

```bash
docker rm -f trademetrix_redis
docker volume rm production_redis-data       # only if corrupted
docker compose -f infra/production/docker-compose.yml up -d redis
```

## Scenario 4 — Database (Supabase) incident

**Detection**: `/health/ready` fails (DB dep), API errors on writes, dashboard down.

1. Supabase dashboard → check project status / incidents
2. Restore: Project Settings → Backups → scheduled or PITR restore point
3. After restore, verify: login works, strategies + backtest runs present (`builder_strategies`, `backtest_runs`), a smoke order round-trips
4. No app changes needed — schema is restored with the data

If the whole project is lost, recreate: create new Supabase project → apply all `supabase/migrations/*.sql` in order (all idempotent) → update `SUPABASE_URL`/keys in `apps/api/.env` + `apps/web/.env` → `deploy.sh`. Env file backup (`backup.sh` → `env/`) contains the current keys.

## Scenario 5 — Complete host loss

**RPO impact**: VPS-side state up to last backup (Redis/ Prometheus/ Grafana — recoverable or expendable). **Data**: safe on Supabase + GitHub.

1. Provision a new VPS (Ubuntu 24.04, 4 vCPU / 8 GB / 100 GB SSD minimum)
2. Point DNS at the new IP (TTL permitting)
3. Copy env files + latest backup dir from off-host copy:
   ```bash
   mkdir -p /root/trademetrix-terminal && cd /root/trademetrix-terminal
   git clone https://github.com/Aakibkhan07/trademetrix-terminal.git .
   # restore apps/api/.env, apps/web/.env, apps/web/.env.production, infra/production/.env.production
   ```
4. `bash infra/production/deploy.sh` — installs Docker, builds, deploys, health-gates
5. Restore state from backup (see `BACKUP_RESTORE.md`): redis, prometheus, grafana, n8n, caddy
6. Verify: API health, web 200, login, a paper order round-trip, `/backtest` loads a persisted run

## Scenario 6 — Security breach / compromised credentials

1. **Kill switch** — suspend order execution first (API kill switch / block broker creds in dashboard; see RUNBOOK)
2. Rotate secrets: Supabase DB password (dashboard → Database → reset password) + update `apps/api/.env`, rotate Supabase service/anon keys, SSH key
3. Invalidate sessions: Supabase dashboard → Authentication → delete sessions/users as needed
4. Audit: API logs (`docker logs trademetrix_api`), auth events in dashboard, recent git pushes, review orders tables
5. If git secrets were ever committed: the repo is public — rotate the secret AND remove it from history (history is public)

## Scenario 7 — Broker outage (Fyers etc.)

- Circuit breakers open automatically; reads (positions/funds) get fallbacks; market data falls back to Yahoo for index symbols
- Token expiry (Fyers ~30 days): watchdog alerts T-60min; re-auth via UI `/v1/brokers/fyers/re-auth`; while expired, backtests still run via Yahoo fallback, live trading is blocked until re-consent
- Broker recovery is automatic (half-open probe); no DR action needed

## Verification drills

- **Quarterly**: restore latest backup into a scratch dir (`tar tzf` + spot-extract), verify a fresh container boots from restored volumes
- **Every release**: one full `deploy.sh` run from `git reset --hard origin/main` (tested 2026-08-01 for v1.0 GA)
- **After Supabase changes**: verify a persisted strategy/backtest survives an API restart (GA checklist item — PASS)
