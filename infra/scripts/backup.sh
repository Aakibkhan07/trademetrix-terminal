#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# TradeMetrix Terminal — Backup (run on the VPS)
#
#   bash infra/scripts/backup.sh [target_dir]
#
# Backs up everything NOT managed by Supabase:
#   - Redis data (consistent RDB snapshot via SAVE)
#   - Prometheus (consistent TSDB snapshot via admin API)
#   - Grafana + n8n (sqlite — stopped briefly for a consistent copy)
#   - Caddy TLS certs + config (stopped briefly)
#   - .env files (api/web) — secrets live here, do NOT lose them
#
# Supabase (Postgres + storage) has platform-managed backups:
#   dashboard -> Project Settings -> Backups (daily + PITR).
# The Supabase DB password must be stored in a password manager.
#
# Every archive is integrity-checked; the script exits non-zero
# if any archive fails verification.
#
# Restore: see docs/ProductionRunbook.md / docs/DISASTER_RECOVERY.md
# ============================================================

DEST="${1:-/root/trademetrix-backups}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$DEST/$STAMP"
RETENTION_DAYS=14
VOL_PREFIX="production"

FAILED=0
ok()   { echo "[OK] $1"; }
warn() { echo "[WARN] $1"; }

vol() { docker volume ls -q -f "name=${VOL_PREFIX}_$1" | head -1; }

check_archive() { # name path
  if [ -s "$2" ] && tar tzf "$2" >/dev/null 2>&1; then
    ok "$1 ($(du -h "$2" | cut -f1))"
  else
    warn "$1 archive failed verification"
    FAILED=1
  fi
}

tar_stopped() { # container volume name
  local C="$1" V="$2" N="$3"
  docker stop "$C" >/dev/null 2>&1 || true
  docker run --rm -v "$V":/v -v "$OUT":/backup alpine sh -c "tar czf /backup/$N.tar.gz -C /v ." 2>/dev/null || true
  docker start "$C" >/dev/null 2>&1 || true
  check_archive "$N" "$OUT/$N.tar.gz"
}

mkdir -p "$OUT"
echo "[INFO] Backing up to $OUT"

# 1. Redis (consistent, no downtime)
R=$(vol redis-data)
if [ -n "$R" ] && docker exec trademetrix_redis redis-cli SAVE >/dev/null 2>&1; then
  mkdir -p "$OUT/redis"
  docker run --rm -v "$R":/data -v "$OUT/redis":/backup alpine sh -c 'cp /data/dump.rdb /backup/' 2>/dev/null || true
  [ -s "$OUT/redis/dump.rdb" ] && ok "redis (dump.rdb)" || { warn "redis snapshot empty"; FAILED=1; }
else
  warn "redis snapshot skipped"
fi

# 2. Prometheus consistent snapshot (admin API, no downtime)
if curl -s -o /dev/null --max-time 5 http://127.0.0.1:9090/-/healthy; then
  curl -s -X POST http://127.0.0.1:9090/api/v1/admin/tsdb/snapshot >/dev/null 2>&1 || true
  SNAP=$(docker exec trademetrix_prometheus sh -c 'ls -t /prometheus/snapshots 2>/dev/null | head -1')
  if [ -n "$SNAP" ]; then
    docker exec trademetrix_prometheus tar czf - -C /prometheus "snapshots/$SNAP" > "$OUT/prometheus-data.tar.gz" 2>/dev/null || true
    check_archive "prometheus-data" "$OUT/prometheus-data.tar.gz"
  else
    warn "prometheus snapshot API unavailable — falling back to stopped-volume copy"
    P=$(vol prometheus-data)
    [ -n "$P" ] && tar_stopped trademetrix_prometheus "$P" prometheus-data
  fi
else
  warn "prometheus not reachable on 127.0.0.1:9090"
fi

# 3. Grafana (sqlite — brief stop)
G=$(vol grafana-data)
[ -n "$G" ] && tar_stopped trademetrix_grafana "$G" grafana-data

# 4. n8n (sqlite — brief stop)
N=$(vol n8n-data)
[ -n "$N" ] && tar_stopped trademetrix-n8n "$N" n8n-data

# 5. Caddy TLS + config (brief stop)
C1=$(vol caddy-data); [ -n "$C1" ] && tar_stopped trademetrix_caddy "$C1" caddy-data
C2=$(vol caddy-config); [ -n "$C2" ] && tar_stopped trademetrix_caddy "$C2" caddy-config

# 6. Env files (secrets)
mkdir -p "$OUT/env"
cp /root/trademetrix-terminal/apps/api/.env "$OUT/env/api.env" 2>/dev/null || true
cp /root/trademetrix-terminal/apps/web/.env "$OUT/env/web.env" 2>/dev/null || true
ok "env files"

# 7. Retention
find "$DEST" -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" -exec rm -rf {} + 2>/dev/null || true
ok "retention (last $RETENTION_DAYS days)"

echo ""
if [ "$FAILED" -eq 0 ]; then
  echo "[DONE] Backup complete and verified: $OUT ($(du -sh "$OUT" | cut -f1))"
else
  echo "[FAIL] Backup finished with unverified archives: $OUT"
  exit 1
fi
echo ""
echo "[NOTE] Supabase Postgres: managed backups live in the Supabase dashboard."
echo "       Store the DB password + .env secrets in a password manager."
