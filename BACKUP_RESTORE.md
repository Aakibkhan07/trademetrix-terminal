# Backup & Restore Guide — TradeMetrix Terminal v1.0.0 (GA)

## What is backed up (and by whom)

| Data | Owner | How |
|------|-------|-----|
| Postgres (Supabase) | **Supabase platform** | Dashboard → Project Settings → Backups. Scheduled backups + PITR (add-on). NOT covered by `backup.sh`. |
| Redis (cache/queue) | `backup.sh` | `redis-cli SAVE` (atomic RDB) |
| Prometheus (metrics, 30d) | `backup.sh` | TSDB snapshot via admin API (`--web.enable-admin-api`), no downtime |
| Grafana (dashboards/config) | `backup.sh` | brief `docker stop` + volume tar |
| n8n (workflows) | `backup.sh` | brief `docker stop` + volume tar |
| Caddy (TLS certs + config) | `backup.sh` | brief `docker stop` + volume tar |
| Env files (all `.env*`) | `backup.sh` | plain copy |
| Application code | git | `git push origin main` (single source of truth) |

## Taking a backup

```bash
ssh root@187.127.185.56
bash /root/trademetrix-terminal/infra/scripts/backup.sh
```

- Output: `/root/trademetrix-backups/<YYYYMMDD_HHMMSS>/`
- Every archive is integrity-checked (`tar tzf`); any failed check → the script exits non-zero (`FAILED=1`)
- Retention: last 14 days, older backups pruned automatically
- Exit 0 + `[DONE] Backup complete and verified: <dir>` = every component OK

Expected output:

```
[OK] redis                (SAVE to RDB)
[OK] prometheus-data      (28M)
[OK] grafana-data         (21M)
[OK] n8n-data             (444K)
[OK] caddy-data           (12K)
[OK] caddy-config         (4.0K)
[OK] env files
[OK] retention (last 14 days)

[DONE] Backup complete and verified: /root/trademetrix-backups/20260801_135225 (49M)
```

## Scheduling

No cron is installed by default. To run nightly at 01:30 UTC:

```bash
crontab -e
30 1 * * * bash /root/trademetrix-terminal/infra/scripts/backup.sh >> /var/log/trademetrix-backup.log 2>&1
```

The runbook alert (Grafana/Prometheus `DiskSpaceLow`) covers the backup dir growth.

## Restoring

### Env files

```bash
cd /root/trademetrix-terminal && mkdir -p apps/api apps/web
cp /root/trademetrix-backups/<ts>/env/apps_api.env   apps/api/.env
cp /root/trademetrix-backups/<ts>/env/apps_web.env   apps/web/.env
# ...match paths in the backup's env/ tree exactly
bash infra/production/deploy.sh
```

### Redis

```bash
docker run --rm -v production_redis-data:/data -v /root/trademetrix-backups/<ts>:/b \
  alpine sh -c "cp /b/redis/appendonlydir/dump.rdb /data/dump.rdb 2>/dev/null || cp /b/redis/dump.rdb /data/dump.rdb"
docker restart trademetrix_redis
```

Redis is non-critical: rate limiting, cache and queue all degrade gracefully (in-memory fallbacks). If in doubt, skip the restore — it warms back up.

### Prometheus

```bash
docker run --rm -v production_prometheus-data:/v -v /root/trademetrix-backups/<ts>:/b \
  alpine sh -c "rm -rf /v/snapshots && tar xzf /b/prometheus-data.tar.gz -C /v"
docker restart trademetrix_prometheus
```

### Grafana / n8n / Caddy

```bash
# example: grafana-data
docker stop trademetrix_grafana
docker run --rm -v production_grafana-data:/v -v /root/trademetrix-backups/<ts>:/b \
  alpine sh -c "tar xzf /b/grafana-data.tar.gz -C /v"
docker start trademetrix_grafana
```

Same pattern for `n8n-data` (container `trademetrix-n8n`), `caddy-data` + `caddy-config` (container `trademetrix_caddy`).

### Database (Supabase)

Use the dashboard: Project Settings → Backups → choose restore point (PITR or scheduled snapshot). The app needs no downtime for reads; writes during restore are lost back to the restore point (RPO governed by platform schedule).

## Off-site copy (recommended)

`backup.sh` writes only to the VPS disk — copy `/root/trademetrix-backups/` off-host (e.g. `rsync`/`rclone` to object storage) or the host failure scenario is covered only by Supabase. See `DISASTER_RECOVERY.md`.
