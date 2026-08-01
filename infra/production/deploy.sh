#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# TradeMetrix Terminal — Production Deploy (single command)
#
#   bash infra/production/deploy.sh
#
# Recreates the production stack from the repo on origin/main:
#   - installs Docker if missing
#   - clones/updates the repo
#   - rebuilds api + web images (all runtime deps baked in —
#     NO manual pip install / post-build steps required)
#   - starts the full stack, waits for health
#
# Requirements before first run:
#   - DNS for ai./api./monitor. + n8n. trademetrix.tech → this host
#   - apps/api/.env and apps/web/.env present (see infra/.env.production.example)
#   - .env files are gitignored and survive redeploys
#
# Optional: OPENROUTER_API_KEY env var is read ONLY if the key is
# not already present in apps/api/.env. The script never prompts
# when run non-interactively (CI / cron).
# ============================================================

REPO_URL="https://github.com/Aakibkhan07/trademetrix-terminal.git"
BRANCH="main"
COMPOSE="docker compose -f infra/production/docker-compose.yml"
DOMAIN="ai.trademetrix.tech"
API_DOMAIN="api.ai.trademetrix.tech"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info() { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC} $1"; }

INTERACTIVE=0
if [ -t 0 ] && [ -t 1 ]; then
  INTERACTIVE=1
fi

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════╗"
echo "║      TradeMetrix Terminal — Production       ║"
echo "║              Deploy / Recreate               ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# ------------------------------------------------------------
# 1. Prerequisites
# ------------------------------------------------------------
info "Checking prerequisites..."
if ! command -v docker &>/dev/null; then
  info "Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  usermod -aG docker "$USER" || true
  ok "Docker installed (re-login may be required for non-root users)"
else
  ok "Docker $(docker --version | cut -d' ' -f3 | tr -d ',')"
fi
if ! docker compose version &>/dev/null 2>&1; then
  apt-get install -y docker-compose-plugin
fi
ok "Docker Compose ready"

# ------------------------------------------------------------
# 2. Repo (source of truth)
# ------------------------------------------------------------
INSTALL_DIR="$HOME/trademetrix-terminal"
if [ -d "$INSTALL_DIR" ]; then
  info "Updating existing installation..."
  cd "$INSTALL_DIR"
  git fetch origin
  git reset --hard "origin/$BRANCH"
  ok "Repo updated to $(git log --oneline -1)"
else
  info "Cloning repository..."
  git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
  cd "$INSTALL_DIR"
  ok "Repo cloned to $(git log --oneline -1)"
fi

# ------------------------------------------------------------
# 3. Env files (untracked, survive redeploys)
# ------------------------------------------------------------
if [ ! -f apps/api/.env ]; then
  err "apps/api/.env not found!"
  err "Create it from apps/api/.env.example (supabase keys, secrets, broker creds)."
  exit 1
fi
if [ ! -f apps/web/.env ]; then
  err "apps/web/.env not found!"
  err "Create it from apps/web/.env.example (public keys, URLs)."
  exit 1
fi
ok "Environment files present"

# OpenRouter key: only inject when env var set AND key missing from .env
if [ -n "${OPENROUTER_API_KEY:-}" ] && ! grep -q "^OPENROUTER_API_KEY=.\+" apps/api/.env; then
  echo "OPENROUTER_API_KEY=$OPENROUTER_API_KEY" >> apps/api/.env
  ok "OpenRouter API key configured"
fi

# ------------------------------------------------------------
# 4. DNS check (advisory)
# ------------------------------------------------------------
VPS_IP=$(curl -s --max-time 10 ifconfig.me || echo "")
if [ -n "$VPS_IP" ] && command -v getent &>/dev/null; then
  for sub in "$DOMAIN" "$API_DOMAIN"; do
    RESOLVED=$(getent hosts "$sub" | awk '{print $1}' | head -1 || echo "")
    if [ "$RESOLVED" = "$VPS_IP" ]; then
      ok "$sub -> $RESOLVED"
    else
      err "$sub does not point to $VPS_IP (got: ${RESOLVED:-not resolved}) — TLS may fail"
    fi
  done
else
  info "DNS check skipped (no public IP or getent)"
fi

# ------------------------------------------------------------
# 5. Build + start
# ------------------------------------------------------------
info "Building images (deps baked in: reportlab, pandas, curl_cffi, ...)..."
$COMPOSE build --parallel api web
info "Starting stack..."
$COMPOSE up -d
ok "Stack started"

# ------------------------------------------------------------
# 6. Health checks
# ------------------------------------------------------------
API_OK=0
for i in {1..18}; do
  STATUS=$(curl -so /dev/null -w "%{http_code}" --max-time 10 https://$API_DOMAIN/health || echo "000")
  if [ "$STATUS" = "200" ]; then
    ok "API healthy (HTTP $STATUS)"
    API_OK=1
    break
  fi
  sleep 10
done
if [ "$API_OK" -ne 1 ]; then
  err "API healthcheck failed after 3 minutes"
  err "Inspect: $COMPOSE logs api"
  exit 1
fi

WEB_OK=0
for i in {1..18}; do
  STATUS=$(curl -so /dev/null -w "%{http_code}" --max-time 10 https://$DOMAIN/ || echo "000")
  if [ "$STATUS" = "200" ] || [ "$STATUS" = "301" ] || [ "$STATUS" = "302" ]; then
    ok "Web healthy (HTTP $STATUS)"
    WEB_OK=1
    break
  fi
  sleep 10
done
if [ "$WEB_OK" -ne 1 ]; then
  err "Web healthcheck failed after 3 minutes"
  err "Inspect: $COMPOSE logs web"
  exit 1
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║        Deployment Complete — v1.0 GA        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo "  Frontend:  https://$DOMAIN"
echo "  API:       https://$API_DOMAIN/docs"
echo ""
echo "  Logs:      $COMPOSE logs -f"
echo "  Restart:   $COMPOSE restart"
echo "  Backup:    bash infra/scripts/backup.sh"
