#!/usr/bin/env bash
set -e

echo "=== Trade Metrix — Load Test Runner ==="
echo ""

API_URL="${API_URL:-http://localhost:8000}"
WS_URL="${WS_URL:-ws://localhost:8000/api/v1/marketdata/ws}"
TOKEN="${TOKEN:-}"
VUS="${VUS:-10}"
DURATION="${DURATION:-30s}"

if ! command -v k6 &>/dev/null; then
  echo "k6 not found. Install from https://k6.io/docs/getting-started/installation/"
  exit 1
fi

echo "Target:  $API_URL"
echo "VUs:     $VUS"
echo "Duration: $DURATION"
echo ""

echo "--- API Load Test ---"
API_URL="$API_URL" k6 run "$(dirname "$0")/api.js" --vus "$VUS" --duration "$DURATION"

echo ""
echo "--- WebSocket Load Test ---"
if [ -n "$TOKEN" ]; then
  WS_URL="$WS_URL" TOKEN="$TOKEN" k6 run "$(dirname "$0")/websocket.js" --vus 5 --duration 15s
else
  echo "Skipping WebSocket test (no TOKEN provided)"
fi

echo ""
echo "=== Load tests complete ==="
