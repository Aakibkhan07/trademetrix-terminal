#!/usr/bin/env bash
# ============================================================
# TradeMetrix Terminal — Local-to-VPS Production Deploy
# Usage:  bash infra/deploy-prod.sh
# Prereq: SSH key auth to root@187.127.185.56
# ============================================================
set -euo pipefail

VPS="root@187.127.185.56"
DOMAIN="ai.trademetrix.tech"
API_DOMAIN="api.ai.trademetrix.tech"
MONITOR_DOMAIN="monitor.ai.trademetrix.tech"
REPO_DIR="$HOME/trademetrix-terminal"
REMOTE_REPO_DIR="/root/trademetrix-terminal"

info() { echo -e "\033[0;36m[INFO]\033[0m  $1"; }
ok()   { echo -e "\033[0;32m[OK]\033[0m    $1"; }
err()  { echo -e "\033[0;31m[ERR]\033[0m   $1"; }

# ── 1. Push latest code to GitHub ──
info "Pushing latest code to GitHub..."
cd "$(dirname "$0")/.."
git push origin main
ok "Code pushed"

# ── 2. SCP .env files to VPS ──
info "Copying .env files to VPS..."
scp apps/api/.env "$VPS:$REMOTE_REPO_DIR/apps/api/.env"
scp apps/web/.env.production "$VPS:$REMOTE_REPO_DIR/apps/web/.env"
# Copy API env alongside production compose so market-agent can read Supabase creds
ssh "$VPS" "cp $REMOTE_REPO_DIR/apps/api/.env $REMOTE_REPO_DIR/infra/production/.env"
ok "Env files copied"

# ── 3. Run deploy on VPS ──
info "Running deployment on VPS..."
ssh "$VPS" bash -s << 'DEPLOY'
  set -euo pipefail
  cd "$HOME/trademetrix-terminal"

  # Default Gemini key from env (set on VPS ahead of time or leave empty)
  GEMINI_API_KEY="${GEMINI_API_KEY:-}"

  echo "[VPS] Updating repo..."
  git fetch origin
  git reset --hard origin/main

  echo "[VPS] Removing old containers..."
  docker compose -f infra/production/docker-compose.yml down --remove-orphans 2>/dev/null || true

  echo "[VPS] Building and starting services..."
  docker compose -f infra/production/docker-compose.yml pull redis
  docker compose -f infra/production/docker-compose.yml build --parallel api web
  if [ -f infra/production/docker-compose.override.yml ]; then
    docker compose -f infra/production/docker-compose.yml -f infra/production/docker-compose.override.yml up -d
  else
    docker compose -f infra/production/docker-compose.yml up -d
  fi

  echo "[VPS] Waiting for healthcheck..."
  sleep 15
  for i in {1..12}; do
    STATUS=$(curl -so /dev/null -w "%{http_code}" http://localhost:8000/health/live 2>/dev/null || echo "000")
    if [ "$STATUS" = "200" ]; then
      ok "API healthy (HTTP $STATUS)"
      break
    fi
    if [ "$i" -eq 12 ]; then
      err "API healthcheck failed after 2 minutes"
      docker compose -f infra/production/docker-compose.yml logs api --tail 50
    fi
    sleep 10
  done
DEPLOY

ok "Deployment complete!"
echo ""
echo "  Frontend:  https://$DOMAIN"
echo "  API docs:  https://$API_DOMAIN/docs"
echo "  Monitor:   https://$MONITOR_DOMAIN"
echo ""
echo "  Logs:  ssh $VPS 'docker compose -f \$HOME/trademetrix-terminal/infra/production/docker-compose.yml logs -f'"
