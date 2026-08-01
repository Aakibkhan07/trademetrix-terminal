#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# TradeMetrix Terminal — Backup (run on the VPS)
#
#   bash infra/scripts/backup.sh [target_dir]
#
# Backs up everything that is NOT managed by Supabase:
#   - Redis data (RDB snapshot of redis-data volume)
#   - Caddy TLS certificates / config
#   - Grafana + Prometheus volumes (thin: just copies the dirs)
#   - .env files (api/web) — secrets live here, do NOT lose them
#   - n8n data
#
# Supabase (Postgres + storage) has platform-managed backups:
#   dashboard -> Project Settings -> Backups (daily + PITR).
# The DB password must be stored separately (password manager).
#
# Restore: see docs/ProductionRunbook.md / DISASTER_RECOVERY.md
# ============================================================

DEST="${1:-/root/trademetrix-backups}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$DEST/$STAMP"
RETENTION_DAYS=14

mkdir -p "$OUT"
echo "[INFO] Backing up to $OUT"

# 1. Redis RDB (point-in-time snapshot)
if docker exec trademetrix_redis redis-cli SAVE >/dev/null 2>&1; then
  mkdir -p "$OUT/redis"
  VOL=$(docker volume ls -q -f name=trademetrix | grep redis || true)
  if [ -n "$VOL" ]; then
    docker run --rm -v "$VOL":/data -v "$OUT/redis":/backup alpine sh -c 'cp /data/dump.rdb /backup/ 2>/dev/null || true'
  fi
  echo "[OK] Redis snapshot"
fi

# 2. Caddy (TLS + config)
for V in caddy-data caddy-config; do
  VOL=$(docker volume ls -q -f name=trademetrix | grep "$V" || true)
  if [ -n "$VOL" ]; then
    docker run --rm -v "$VOL":/v -v "$OUT":/backup alpine sh -c "tar czf /backup/$V.tar.gz -C / v ."
    echo "[OK] $V"
  fi
done

# 3. Prometheus + Grafana volumes
for V in prometheus-data grafana-data; do
  VOL=$(docker volume ls -q -f name=trademetrix | grep "$V" || true)
  if [ -n "$VOL" ]; then
    docker run --rm -v "$VOL":/v -v "$OUT":/backup alpine sh -c "tar czf /backup/$V.tar.gz -C / v ."
    echo "[OK] $V"
  fi
done

# 4. n8n data
for V in $(docker volume ls -q -f name=trademetrix-n8n); do
  docker run --rm -v "$V":/v -v "$OUT":/backup alpine sh -c "tar czf /backup/n8n.tar.gz -C / v ."
  echo "[OK] n8n"
done

# 5. Env files (secrets)
mkdir -p "$OUT/env"
cp /root/trademetrix-terminal/apps/api/.env "$OUT/env/api.env" 2>/dev/null || true
cp /root/trademetrix-terminal/apps/web/.env "$OUT/env/web.env" 2>/dev/null || true
echo "[OK] env files"

# 6. Retention
find "$DEST" -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" -exec rm -rf {} + 2>/dev/null || true
echo "[OK] Retention: keeping last $RETENTION_DAYS days"

echo ""
echo "[DONE] Backup at $OUT"
du -sh "$OUT"
echo ""
echo "[NOTE] Supabase Postgres: managed backups live in the Supabase dashboard."
echo "       Store the DB password + .env secrets in a password manager."
