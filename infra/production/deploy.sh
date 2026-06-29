#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# TradeMetrix Terminal — VPS Deployment Script
# Run this on your VPS at 187.127.185.56
#
# Before running:
#   1. Create apps/api/.env and apps/web/.env on the VPS
#      (SCP them from your local machine, or create manually)
#   2. Set the GEMINI_API_KEY env var or enter it when prompted
# ============================================================

REPO_URL="https://github.com/Aakibkhan07/trademetrix-terminal.git"
BRANCH="main"
DOMAIN="ai.trademetrix.tech"
API_DOMAIN="api.ai.trademetrix.tech"
MONITOR_DOMAIN="monitor.ai.trademetrix.tech"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info() { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()  { echo -e "${GREEN}[OK]${NC} $1"; }
err() { echo -e "${RED}[ERR]${NC} $1"; }

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════╗"
echo "║      TradeMetrix Terminal — VPS Deploy       ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"

if [ -z "${GEMINI_API_KEY:-}" ]; then
  read -rp "Enter your Gemini API key (or press Enter to skip AI): " GEMINI_KEY
  GEMINI_API_KEY="${GEMINI_KEY:-}"
fi
export GEMINI_API_KEY

info "Checking prerequisites..."
if ! command -v docker &>/dev/null; then
  info "Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"
  ok "Docker installed"
else
  ok "Docker $(docker --version | cut -d' ' -f3 | tr -d ',')"
fi
if ! command -v docker-compose &>/dev/null && ! docker compose version &>/dev/null 2>&1; then
  sudo apt-get install -y docker-compose-plugin
fi
ok "Docker Compose ready"

INSTALL_DIR="$HOME/trademetrix-terminal"
if [ -d "$INSTALL_DIR" ]; then
  info "Updating existing installation..."
  cd "$INSTALL_DIR"
  git fetch origin
  git reset --hard "origin/$BRANCH"
  ok "Repo updated"
else
  info "Cloning repository..."
  git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
  cd "$INSTALL_DIR"
  ok "Repo cloned"
fi

# Check .env files exist
if [ ! -f apps/api/.env ]; then
  err "apps/api/.env not found!"
  err "SCP it from your local machine:"
  echo "  scp apps/api/.env root@187.127.185.56:~/trademetrix-terminal/apps/api/.env"
  echo ""
  echo "Or run this on your Mac:"
  echo "  scp /path/to/trademetrix-terminal/apps/api/.env root@187.127.185.56:~/trademetrix-terminal/apps/api/.env"
  exit 1
fi
if [ ! -f apps/web/.env ]; then
  err "apps/web/.env not found!"
  err "SCP it from your local machine:"
  echo "  scp apps/web/.env root@187.127.185.56:~/trademetrix-terminal/apps/web/.env"
  echo ""
  echo "Or run this on your Mac:"
  echo "  scp /path/to/trademetrix-terminal/apps/web/.env root@187.127.185.56:~/trademetrix-terminal/apps/web/.env"
  exit 1
fi

# Inject Gemini key into API .env
if [ -n "$GEMINI_API_KEY" ]; then
  if grep -q "GEMINI_API_KEY=" apps/api/.env; then
    sed -i "s/^GEMINI_API_KEY=.*/GEMINI_API_KEY=$GEMINI_API_KEY/" apps/api/.env
  else
    echo "GEMINI_API_KEY=$GEMINI_API_KEY" >> apps/api/.env
  fi
  ok "Gemini API key configured"
fi

ok "Environment files ready"

info "Checking DNS..."
VPS_IP=$(curl -s ifconfig.me || echo "187.127.185.56")
for sub in "$DOMAIN" "$API_DOMAIN" "$MONITOR_DOMAIN"; do
  RESOLVED=$(dig +short "$sub" 2>/dev/null || host "$sub" 2>/dev/null | grep "has address" | awk '{print $NF}' || echo "")
  if [ "$RESOLVED" = "$VPS_IP" ]; then
    ok "$sub → $RESOLVED"
  else
    err "$sub does not point to $VPS_IP (got: ${RESOLVED:-not resolved})"
    err "Update DNS before Caddy can issue TLS certs"
  fi
done

info "Building and starting services..."
cd "$INSTALL_DIR"
docker compose -f infra/production/docker-compose.yml pull redis
docker compose -f infra/production/docker-compose.yml build --parallel api web
docker compose -f infra/production/docker-compose.yml up -d

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           Deployment Complete!              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo "  Frontend:  https://$DOMAIN"
echo "  API:       https://$API_DOMAIN/docs"
echo "  Monitor:   https://$MONITOR_DOMAIN (admin/admin)"
echo ""
echo "  Logs:      docker compose -f infra/production/docker-compose.yml logs -f"
echo "  Restart:   docker compose -f infra/production/docker-compose.yml restart"
echo "  Stop:      docker compose -f infra/production/docker-compose.yml down"
echo ""
echo "  SSL:       watch docker compose -f infra/production/docker-compose.yml logs caddy"

# Healthcheck
echo ""
info "Waiting for services to be healthy..."
sleep 10
for i in {1..12}; do
  STATUS=$(curl -so /dev/null -w "%{http_code}" https://$API_DOMAIN/health 2>/dev/null || echo "000")
  if [ "$STATUS" = "200" ]; then
    ok "API is healthy (HTTP $STATUS)"
    break
  fi
  if [ "$i" -eq 12 ]; then
    err "API healthcheck failed after 2 minutes"
    err "Check: docker compose -f infra/production/docker-compose.yml logs api"
  fi
  sleep 10
done

FRONTEND_CODE=$(curl -so /dev/null -w "%{http_code}" https://$DOMAIN 2>/dev/null || echo "000")
if [ "$FRONTEND_CODE" = "200" ] || [ "$FRONTEND_CODE" = "301" ] || [ "$FRONTEND_CODE" = "302" ]; then
  ok "Frontend is up (HTTP $FRONTEND_CODE)"
else
  err "Frontend returned HTTP $FRONTEND_CODE (may still be starting)"
fi
