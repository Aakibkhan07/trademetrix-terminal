#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
err()   { echo -e "${RED}[ERR]${NC}   $1"; }

INSTALL_DIR="${INSTALL_DIR:-$HOME/trademetrix-terminal}"
COMPOSE_FILE="${COMPOSE_FILE:-infra/docker-compose.yml}"
BACKUP_DIR="${BACKUP_DIR:-./rollback-snapshots}"
VERSION_FILE="${VERSION_FILE:-./.deployed-version}"
BRANCH="${BRANCH:-main}"

cd "$INSTALL_DIR"

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════╗"
echo "║      TradeMetrix Terminal — Rollback         ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# Determine rollback target
TARGET="${1:-}"
if [ -z "$TARGET" ]; then
  if [ -f "$VERSION_FILE" ]; then
    PREV=$(tail -2 "$VERSION_FILE" | head -1 | cut -d' ' -f1 || true)
    if [ -n "$PREV" ]; then
      TARGET="$PREV"
      info "Auto-detected previous version: $TARGET"
    fi
  fi
fi

if [ -z "$TARGET" ]; then
  info "Usage: $0 [<git-ref>]"
  info "  Git ref can be a tag (v1.0.0-beta), commit hash, or branch name"
  echo ""
  info "Available tags:"
  git tag --sort=-creatordate | head -10
  echo ""
  info "Recent commits:"
  git log --oneline -10
  exit 1
fi

info "Rolling back to: $TARGET"

# Backup current images
SNAPSHOT_DIR="$BACKUP_DIR/$(date +%Y%m%d_%H%M%S)_pre_rollback"
mkdir -p "$SNAPSHOT_DIR"
info "Snapshotting current .env files to $SNAPSHOT_DIR..."
cp -r apps/api/.env "$SNAPSHOT_DIR/api.env" 2>/dev/null || warn "No apps/api/.env to backup"
cp -r apps/web/.env "$SNAPSHOT_DIR/web.env" 2>/dev/null || warn "No apps/web/.env to backup"
ok "Env snapshotted"

# Record current containers
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" > "$SNAPSHOT_DIR/containers.txt" 2>/dev/null || true

# Stop current stack
info "Stopping current services..."
docker compose -f "$COMPOSE_FILE" down --timeout 30 || true
ok "Services stopped"

# Stash any local changes
info "Stashing local changes..."
git stash --include-untracked || true

# Checkout target
info "Checking out $TARGET..."
if ! git checkout "$TARGET" 2>/dev/null; then
  err "Failed to checkout $TARGET"
  warn "Restoring services from previous state..."
  docker compose -f "$COMPOSE_FILE" up -d
  exit 1
fi
ok "Checked out $TARGET"

# Restore .env files (they were stashed)
info "Restoring environment files..."
if [ -f "$SNAPSHOT_DIR/api.env" ]; then
  cp "$SNAPSHOT_DIR/api.env" apps/api/.env
  ok "apps/api/.env restored"
fi
if [ -f "$SNAPSHOT_DIR/web.env" ]; then
  cp "$SNAPSHOT_DIR/web.env" apps/web/.env
  ok "apps/web/.env restored"
fi

# Rebuild and restart
info "Building and starting services..."
docker compose -f "$COMPOSE_FILE" build --parallel api web
docker compose -f "$COMPOSE_FILE" up -d
ok "Services restarted"

# Healthcheck
info "Waiting for healthcheck..."
sleep 10
for i in {1..12}; do
  STATUS=$(curl -so /dev/null -w "%{http_code}" http://localhost:8000/health/live 2>/dev/null || echo "000")
  if [ "$STATUS" = "200" ]; then
    ok "API is healthy (HTTP $STATUS)"
    break
  fi
  if [ "$i" -eq 12 ]; then
    warn "API healthcheck did not pass within 2 minutes"
    warn "Check: docker compose -f $COMPOSE_FILE logs api"
  fi
  sleep 10
done

# Record rollback
echo "$TARGET $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$VERSION_FILE"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           Rollback Complete!                 ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo "  Rolled back to: $TARGET"
echo "  Snapshot:        $SNAPSHOT_DIR"
echo ""
echo "  To restore the snapshot's env files:"
echo "    cp $SNAPSHOT_DIR/api.env apps/api/.env"
echo "    cp $SNAPSHOT_DIR/web.env apps/web/.env"
