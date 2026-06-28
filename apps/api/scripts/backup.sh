#!/usr/bin/env bash
set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_DIR:-./backups}"
DB_URL="${SUPABASE_URL:-http://localhost:54321}"
PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-54322}"
PG_USER="${PG_USER:-postgres}"
PG_DB="${PG_DB:-postgres}"
S3_BUCKET="${S3_BUCKET:-}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting PostgreSQL backup..."

pg_dump \
  -h "$PG_HOST" \
  -p "$PG_PORT" \
  -U "$PG_USER" \
  -d "$PG_DB" \
  -F c \
  -f "${BACKUP_DIR}/trademetrix_${TIMESTAMP}.dump" \
  -Z 9 \
  --no-owner \
  --no-acl

echo "[$(date)] Backup written: ${BACKUP_DIR}/trademetrix_${TIMESTAMP}.dump"

# Encrypt backup
if [ -n "$BACKUP_ENCRYPTION_KEY" ]; then
  echo "[$(date)] Encrypting backup..."
  gpg --batch --yes --passphrase "$BACKUP_ENCRYPTION_KEY" \
    -c "${BACKUP_DIR}/trademetrix_${TIMESTAMP}.dump"
  rm "${BACKUP_DIR}/trademetrix_${TIMESTAMP}.dump"
  echo "[$(date)] Encrypted: ${BACKUP_DIR}/trademetrix_${TIMESTAMP}.dump.gpg"
fi

# Sync to S3
if [ -n "$S3_BUCKET" ]; then
  echo "[$(date)] Syncing to S3..."
  aws s3 sync "$BACKUP_DIR" "s3://${S3_BUCKET}/backups/" --exclude "*" --include "*.dump*"
  echo "[$(date)] S3 sync complete"
fi

# Clean old backups
find "$BACKUP_DIR" -name "trademetrix_*.dump*" -mtime +$RETENTION_DAYS -delete
echo "[$(date)] Retention: removed backups older than ${RETENTION_DAYS} days"

echo "[$(date)] Backup complete."
