# Upgrade Guide — TradeMetrix Terminal v1.0.0 (GA)

Covers moving between released versions. Upgrade path so far: v0.2.0-rc.x → v1.0.0 (GA). All GA migrations are additive and idempotent (`IF NOT EXISTS`).

## Standard upgrade (app + infra)

```bash
ssh root@187.127.185.56
cd /root/trademetrix-terminal
bash infra/production/deploy.sh
```

That is the whole procedure for code + infra: the script resets the repo to `origin/main`, rebuilds images, recreates containers and health-gates API + web. Env files are untracked and preserved.

Before deploying, review the diff for anything operational:

```bash
git fetch origin && git log --oneline HEAD..origin/main
git diff HEAD origin/main -- infra/ CHANGELOG.md RELEASE_NOTES.md
```

## Database migrations

Migrations live in `supabase/migrations/` (14 files, idempotent, filename-ordered). The GA database state is already applied remotely; new migrations must be applied in order:

```bash
# local dev
docker exec -it supabase_db_trademetrix-terminal psql -U postgres -d postgres \
  -f /dev/stdin < supabase/migrations/<new>.sql

# production (remote Supabase) — password in password manager
PGPASSWORD='<supabase-db-password>' psql \
  "postgresql://postgres@db.nwutlfuowiulfpbsrldn.supabase.co:5432/postgres?sslmode=require" \
  -f supabase/migrations/<new>.sql
```

Check what's pending first:

```bash
PGPASSWORD='<supabase-db-password>' psql "postgresql://postgres@db.nwutlfuowiulfpbsrldn.supabase.co:5432/postgres?sslmode=require" \
  -c "\dt" | grep -E 'builder|backtest|candles|oms'
```

All migrations to date are additive (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) — no destructive changes, no data rework.

## Version-specific notes

### v1.0.0-rc.x → v1.0.0 (GA) — this release
- No schema changes beyond those already applied during GA prep (6 tables: `builder_strategies`, `builder_strategy_versions`, `builder_strategy_logs`, `backtest_runs`, `candles`, `corporate_actions`) — verify they exist before/after upgrade
- Deps: reportlab now baked into the image — remove any manual `pip install` habit
- Deploy script is now the only supported path (old `infra/deploy.sh` / `infra/production/deploy.sh` interactive prompts are gone)
- New ops artifact: `infra/scripts/backup.sh` — add it to cron (see `BACKUP_RESTORE.md`)
- Prometheus compose flags changed (`--web.enable-lifecycle`, `--web.enable-admin-api`) — required for snapshot-based backups

### v0.x → v1.0.0-rc (historical, kept for audit)
- Circuit-breaker wrapper: broker instantiation must use `create_broker()` not raw adapters
- Strategy assignments FK changed `strategies(id)` → `user_strategies(id)`
- Broker credentials re-encryption when `ENCRYPTION_KEY` changes

## Rollback

```bash
cd /root/trademetrix-terminal
git log --oneline -10          # find last known-good sha
git checkout <known-good-sha>
bash infra/production/deploy.sh
```

Schema rollback: because migrations are additive, old code + new schema is safe (new columns are nullable/defaulted). Only roll back the DB itself via Supabase dashboard PITR if a release introduced bad data — never hand-DROP columns.

## Post-upgrade verification checklist

1. `curl -s https://api.ai.trademetrix.tech/health` → ok; `/health/ready` → db+cache ok
2. `curl -s -o /dev/null -w '%{http_code}\n' https://ai.trademetrix.tech/` → 200
3. Login → dashboard loads; strategy list shows persisted strategies
4. Run a quick backtest (NIFTY 15m, 10 days) → completes; open the run from history (persisted)
5. `bash /root/trademetrix-terminal/infra/scripts/backup.sh` → exit 0, all `[OK]`
6. `docker ps` — all containers healthy (autoheal active)
