#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░"
echo "  Trade Metrix Terminal  —  Starting..."
echo "░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░"
echo ""

# ── Check .env files ──────────────────────────────────────────
for f in apps/api/.env apps/web/.env; do
  if [ ! -f "$ROOT/$f" ]; then
    echo "[FAIL] $f not found. Copy from $f.example"
    exit 1
  fi
done

# ── Python virtual env ────────────────────────────────────────
if [ ! -d "$ROOT/.venv" ]; then
  echo "[...] Creating Python virtual env..."
  python3.12 -m venv "$ROOT/.venv"
fi
"$ROOT/.venv/bin/pip" install -q -r "$ROOT/apps/api/requirements.txt" 2>/dev/null

# ── npm deps ──────────────────────────────────────────────────
if [ ! -d "$ROOT/apps/web/node_modules" ]; then
  echo "[...] Installing frontend dependencies..."
  cd "$ROOT/apps/web" && npm install --silent
fi

# ── Colima ─────────────────────────────────────────────────────
if ! command -v colima &>/dev/null; then
  echo "[FAIL] colima not found. Install: brew install colima"
  exit 1
fi

if ! colima status &>/dev/null; then
  echo "[...] Starting Colima..."
  colima start
fi
echo "[OK] Colima is running"

# Switch Docker context to colima
docker context use colima 2>/dev/null || docker context create colima --docker "host=unix://${HOME}/.colima/default/docker.sock" 2>/dev/null
docker context use colima

# ── Supabase ───────────────────────────────────────────────────
echo "[...] Starting Supabase (first pull may take a while)..."
cd "$ROOT"
supabase start --exclude vector 2>/dev/null
echo "[OK] Supabase is running"

# ── Start API server ──────────────────────────────────────────
echo "[...] Starting API on port 8000..."
kill $(lsof +c0 -ti :8000) 2>/dev/null || true
sleep 1
cd "$ROOT/apps/api"
mkdir -p "$ROOT/logs"
nohup "$ROOT/.venv/bin/uvicorn" main:app --host 0.0.0.0 --port 8000 > "$ROOT/logs/api.log" 2>&1 &
API_PID=$!
sleep 3
if curl -s http://localhost:8000/health >/dev/null 2>&1; then
  echo "[OK] API running on http://localhost:8000"
else
  echo "[FAIL] API failed to start. Check logs/api.log"
  exit 1
fi

# ── Start Web frontend ────────────────────────────────────────
echo "[...] Starting web frontend on port 3000..."
cd "$ROOT/apps/web"
PORT=3000 nohup node_modules/.bin/next dev > "$ROOT/logs/web.log" 2>&1 &
WEB_PID=$!
echo "[OK] Web running on http://localhost:3000"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Trade Metrix Terminal                          ║"
echo "║   API:  http://localhost:8000                    ║"
echo "║   Web:  http://localhost:3000                    ║"
echo "║   Docs: http://localhost:8000/docs               ║"
echo "║   Supabase Studio: http://localhost:54323        ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "Press Ctrl+C to stop all services"

wait $API_PID $WEB_PID
