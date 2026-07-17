#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# TradeMetrix Terminal — VPS Deployment Script
#
# Usage:
#   bash infra/deploy.sh                 # Deploy latest main
#   bash infra/deploy.sh <branch/tag>    # Deploy specific ref
#
# Prerequisites:
#   infra/.env.production  must exist on the VPS
#   (copy from infra/.env.production.example and fill in values)
# ============================================================

REPO_URL="https://github.com/Aakibkhan07/trademetrix-terminal.git"
BRANCH="${1:-main}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/trademetrix-terminal}"
COMPOSE_FILE="infra/docker-compose.yml"
VERSION_FILE="${INSTALL_DIR}/.deployed-version"

DOMAIN="${DOMAIN:-ai.trademetrix.tech}"
API_DOMAIN="${API_DOMAIN:-api.ai.trademetrix.tech}"
MONITOR_DOMAIN="${MONITOR_DOMAIN:-monitor.ai.trademetrix.tech}"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info() { echo -e "${CYAN}[INFO]${NC}  $1"; }
ok()  { echo -e "${GREEN}[OK]${NC}    $1"; }
err() { echo -e "${RED}[ERR]${NC}   $1"; }

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════╗"
echo "║      TradeMetrix Terminal — VPS Deploy       ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo "  Branch/ref:  $BRANCH"
echo "  Install dir: $INSTALL_DIR"
echo ""

# ── Prompt for Gemini key ──
if [ -z "${GEMINI_API_KEY:-}" ]; then
  read -rp "Enter Gemini API key (or press Enter to skip AI): " GEMINI_KEY
  GEMINI_API_KEY="${GEMINI_KEY:-}"
fi
export GEMINI_API_KEY

# ── Install Docker if missing ──
info "Checking prerequisites..."
if ! command -v docker &>/dev/null; then
  info "Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"
  ok "Docker installed"
else
  ok "Docker $(docker --version | cut -d' ' -f3 | tr -d ',')"
fi
if ! docker compose version &>/dev/null 2>&1; then
  sudo apt-get install -y docker-compose-plugin
fi
ok "Docker Compose ready"

# ── Clone or pull repo ──
if [ -d "$INSTALL_DIR" ]; then
  info "Updating existing installation..."
  cd "$INSTALL_DIR"
  git fetch origin
  git stash --include-untracked || true
  git checkout "$BRANCH"
  git reset --hard "origin/$BRANCH"
  ok "Repo updated to $BRANCH"
else
  info "Cloning repository..."
  git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
  cd "$INSTALL_DIR"
  ok "Repo cloned (branch: $BRANCH)"
fi

# ── Verify .env file ──
if [ ! -f infra/.env.production ]; then
  err "infra/.env.production not found!"
  err "Create from template and fill in values:"
  err "  cp infra/.env.production.example infra/.env.production"
  err "  nano infra/.env.production"
  exit 1
fi

# Inject Gemini key into .env.production if provided
if [ -n "$GEMINI_API_KEY" ]; then
  if grep -q "GEMINI_API_KEY=" infra/.env.production; then
    sed -i "s/^GEMINI_API_KEY=.*/GEMINI_API_KEY=$GEMINI_API_KEY/" infra/.env.production
  else
    echo "GEMINI_API_KEY=$GEMINI_API_KEY" >> infra/.env.production
  fi
  ok "Gemini API key configured"
fi

ok "Environment file ready"

# ── Check DNS ──
info "Checking DNS..."
VPS_IP=$(curl -s ifconfig.me || curl -s icanhazip.com || echo "")
if [ -z "$VPS_IP" ]; then
  warn "Could not determine VPS IP — skipping DNS check"
else
  for sub in "$DOMAIN" "$API_DOMAIN" "$MONITOR_DOMAIN"; do
    RESOLVED=$(dig +short "$sub" 2>/dev/null || host "$sub" 2>/dev/null | grep "has address" | awk '{print $NF}' || echo "")
    if [ "$RESOLVED" = "$VPS_IP" ]; then
      ok "$sub → $RESOLVED"
    else
      err "$sub does not point to $VPS_IP (got: ${RESOLVED:-not resolved})"
      err "Update DNS before Caddy can issue TLS certs"
    fi
  done
fi

# ── Build and start ──
info "Building and starting services..."
cd "$INSTALL_DIR"
docker compose -f "$COMPOSE_FILE" pull redis prometheus node-exporter
docker compose -f "$COMPOSE_FILE" build --parallel api web market-agent
docker compose -f "$COMPOSE_FILE" up -d

# Reload nginx to pick up new container IPs (avoid 502 errors)
docker compose -f "$COMPOSE_FILE" exec -T nginx nginx -s reload 2>/dev/null || true

# Record deployed version
echo "$BRANCH $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$VERSION_FILE"

# ── Post-deploy healthcheck ──
echo ""
info "Waiting for services to be healthy..."
sleep 15
for i in {1..12}; do
  STATUS=$(curl -so /dev/null -w "%{http_code}" http://localhost:8000/health/live 2>/dev/null || echo "000")
  if [ "$STATUS" = "200" ]; then
    ok "API is healthy (HTTP $STATUS)"
    break
  fi
  if [ "$i" -eq 12 ]; then
    err "API healthcheck failed after 2 minutes"
    err "Check: docker compose -f $COMPOSE_FILE logs api"
  fi
  sleep 10
done

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           Deployment Complete!              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo "  Frontend:  https://$DOMAIN"
echo "  API docs:  https://$API_DOMAIN/health"
echo "  Monitor:   https://$MONITOR_DOMAIN"
echo ""
echo "  Logs:      docker compose -f $COMPOSE_FILE logs -f"
echo "  Restart:   docker compose -f $COMPOSE_FILE restart"
echo "  Stop:      docker compose -f $COMPOSE_FILE down"
echo "  Rollback:  bash infra/rollback.sh"
