#!/usr/bin/env bash
set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <backup_file>"
  echo "  Restores a .dump or .dump.gpg file"
  exit 1
fi

BACKUP_FILE="$1"
PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-54322}"
PG_USER="${PG_USER:-postgres}"
PG_DB="${PG_DB:-postgres}"

if [[ "$BACKUP_FILE" == *.gpg ]]; then
  if [ -z "$BACKUP_ENCRYPTION_KEY" ]; then
    echo "ERROR: BACKUP_ENCRYPTION_KEY required for encrypted backups"
    exit 1
  fi
  echo "[$(date)] Decrypting backup..."
  DECRYPTED="${BACKUP_FILE%.gpg}"
  gpg --batch --yes --passphrase "$BACKUP_ENCRYPTION_KEY" \
    -o "$DECRYPTED" -d "$BACKUP_FILE"
  BACKUP_FILE="$DECRYPTED"
fi

echo "[$(date)] Restoring PostgreSQL from $BACKUP_FILE..."
pg_restore \
  -h "$PG_HOST" \
  -p "$PG_PORT" \
  -U "$PG_USER" \
  -d "$PG_DB" \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  --verbose \
  "$BACKUP_FILE"

echo "[$(date)] Restore complete."
