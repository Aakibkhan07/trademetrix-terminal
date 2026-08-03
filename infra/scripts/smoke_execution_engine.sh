#!/usr/bin/env bash
# Execution Engine v1.0 — 15-minute production smoke gate.
#
# Runs against the deployed VPS from the workstation. Requires sshpass and the
# VPS password. Does NOT deploy anything; only observes (curl, docker logs,
# docker stats, docker exec probes, one `docker restart trademetrix_api`).
#
# Usage:
#   TMX_VPS_PASSWORD='...' bash infra/scripts/smoke_execution_engine.sh
#
# Env overrides:
#   SMOKE_USER          user id for engine smoke state (default: prod test user)
#   SMOKE_FUTURE_SYMBOL Fyers index-future symbol for the OMS paper order
#                       (default: computed current-month, e.g. NSE:NIFTY26AUGFUT)
#
# Prints a check list and marks the build:
#   READY_FOR_PRODUCTION_DEPLOYMENT   (every item passed)
#   NOT_READY                         (any item failed; exit 1)

set -u

VPS_HOST="root@187.127.185.56"
API_URL="https://api.ai.trademetrix.tech"
CONTAINER="trademetrix_api"
SMOKE_USER="${SMOKE_USER:-fa668109-4b1e-4758-a49b-015027ea4115}"
SMOKE_FUTURE_SYMBOL="${SMOKE_FUTURE_SYMBOL:-}"
if [ -z "$SMOKE_FUTURE_SYMBOL" ]; then
    SMOKE_FUTURE_SYMBOL="NSE:NIFTY$(date -u +%y)$(date -u +%b | tr '[:lower:]' '[:upper:]')FUT"
fi
BUDGET_SECONDS=900
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROBE="$SCRIPT_DIR/smoke_execution_engine_probe.py"

SSH_PASS="${TMX_VPS_PASSWORD:-}"
if [ -z "$SSH_PASS" ]; then
    echo "ERROR: TMX_VPS_PASSWORD not set" >&2
    exit 2
fi

START=$(date +%s)
RESULTS=()

now() { date +%s; }
expire() {
    if [ $(( $(now) - START )) -gt "$BUDGET_SECONDS" ]; then
        echo "FATAL: 15-minute smoke budget exceeded" >&2
        exit 1
    fi
}
ssh_run() { sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$VPS_HOST" "$@"; }
remote_date() { ssh_run "date -u -d @$1 +%Y-%m-%dT%H:%M:%SZ"; }

ck() { # ck <name> <0|1> <detail>
    RESULTS+=("$1|$2|$3")
    if [ "$2" = "1" ]; then
        echo "[PASS] $1${3:+ — $3}"
    else
        echo "[FAIL] $1${3:+ — $3}"
    fi
}

log_count() { # log_count <iso-since> <pattern>
    ssh_run "docker logs --since '$1' $CONTAINER 2>&1 | grep -c \"$2\" || true"
}

get_gauge() { # get_gauge <metric> <label-value>
    curl -s "$API_URL/metrics" | grep "^$1{broker=\"$2\"}" | tail -1 | awk '{print $2}'
}

vmrss_kb() {
    ssh_run "cat /proc/\$(docker inspect --format '{{.State.Pid}}' $CONTAINER)/status 2>/dev/null | grep VmRSS" | awk '{print $2}'
}

run_probe() { # run_probe <phase> <user> [ids...]
    local phase="$1" user="$2"
    shift 2
    local args=""
    for a in "$@"; do args="$args '$a'"; done
    ssh_run "docker exec -i $CONTAINER sh -c 'cd /app && PYTHONPATH=/app python3 - $phase $user $args'" < "$PROBE"
}

echo "=== Execution Engine v1.0 smoke gate ==="
echo "budget: ${BUDGET_SECONDS}s  api: $API_URL  container: $CONTAINER"
echo

# ---------------------------------------------------------------------------
# 0. Preflight: endpoint reachable + baseline memory
# ---------------------------------------------------------------------------
if ! curl -fsS -m 20 "$API_URL/health" >/dev/null; then
    echo "FATAL: API unreachable before smoke" >&2
    exit 1
fi
ISO_START=$(remote_date "$START")
MEM0=$(vmrss_kb)
echo "baseline RSS: ${MEM0:-?} kB"
expire

# ---------------------------------------------------------------------------
# 1. Startup  |  11. Health endpoint
# ---------------------------------------------------------------------------
STARTUP_LOG=$(log_count "$ISO_START" "Execution Engine v1.0 initialized \(bus running=True")
if [ "$STARTUP_LOG" -ge 1 ]; then
    ck "Startup — engine initialized, bus running" 1 "log lines: $STARTUP_LOG"
else
    ck "Startup — engine initialized, bus running" 0 "no init log"
fi
curl -fsS -m 20 "$API_URL/health" >/dev/null && ck "Health endpoint — GET /health" 1 "200" \
    || ck "Health endpoint — GET /health" 0
expire

# ---------------------------------------------------------------------------
# 2. Event bridge active
# ---------------------------------------------------------------------------
BRIDGE_FAIL=$(log_count "$ISO_START" "Legacy event bridge subscription failed")
BRIDGE_STARTUP=$(run_probe startup "$SMOKE_USER")
BRIDGE_WIRED=$(echo "$BRIDGE_STARTUP" | grep '^KEY bridge_wired=' | cut -d= -f2)
STAR_SUB=$(echo "$BRIDGE_STARTUP" | grep '^KEY legacy_star_subscribers=' | cut -d= -f2)
if [ "$BRIDGE_FAIL" = "0" ] && [ "$BRIDGE_WIRED" = "true" ] && [ "${STAR_SUB:-0}" -ge 1 ]; then
    ck "Event bridge active — wired, no subscribe failure" 1 "bridge_wired=$BRIDGE_WIRED star_subscribers=$STAR_SUB"
else
    ck "Event bridge active — wired, no subscribe failure" 0 \
       "bridge_failed_logs=$BRIDGE_FAIL wired=$BRIDGE_WIRED star=$STAR_SUB"
fi
expire

# ---------------------------------------------------------------------------
# 12. Metrics endpoint
# ---------------------------------------------------------------------------
METRICS=$(curl -s -m 20 "$API_URL/metrics")
if printf '%s' "$METRICS" | grep -q '^execution_engine_trades_executed_total' \
   && printf '%s' "$METRICS" | grep -q '^execution_engine_realized_pnl'; then
    ck "Metrics endpoint — GET /metrics exposes engine gauges" 1 "trades+realized present"
else
    ck "Metrics endpoint — GET /metrics exposes engine gauges" 0 "engine gauges missing"
fi
expire

# ---------------------------------------------------------------------------
# 4/6/3. Paper order via OMS (live API process) + propagation
# ---------------------------------------------------------------------------
TRADES0=$(get_gauge execution_engine_trades_executed_total paper)
echo "trades gauge before OMS order: ${TRADES0:-0}"
ISO_OMS=$(remote_date "$(now)")

cat > /tmp/smoke_oms_order.py <<'PY'
import asyncio, sys
from execution.models import ExecutionRequest
from oms.manager import order_manager

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else ""
USER = sys.argv[2] if len(sys.argv) > 2 else ""

async def main():
    req = ExecutionRequest(
        user_id=USER, broker="paper", symbol=SYMBOL, exchange="NSE",
        side="BUY", order_type="MARKET", product="INTRADAY",
        quantity=5, price=0.0, strategy_id="smoke", source="smoke",
        is_paper=True, execution_request_id=f"smoke-oms-{int(asyncio.get_event_loop().time())}",
    )
    order = await order_manager.place_and_wait(req, timeout=30.0)
    print(f"KEY oms_state={order.state.value}", flush=True)
    print(f"KEY oms_qty={order.filled_quantity}", flush=True)
    print(f"KEY oms_avg={order.average_price}", flush=True)
    print(f"KEY oms_broker_order_id={order.broker_order_id}", flush=True)
    print(f"KEY oms_client_id={order.execution_request_id}", flush=True)
    print(f"KEY oms_symbol={SYMBOL}", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
PY
ssh_run "cat > /tmp/smoke_oms_order.py" < /tmp/smoke_oms_order.py
OMS_OUT=$(ssh_run "docker cp /tmp/smoke_oms_order.py $CONTAINER:/tmp/smoke_oms_order.py && docker exec $CONTAINER sh -c 'cd /app && PYTHONPATH=/app python3 /tmp/smoke_oms_order.py \"$SMOKE_FUTURE_SYMBOL\" \"$SMOKE_USER\"'")

OMS_STATE=$(echo "$OMS_OUT" | grep '^KEY oms_state=' | cut -d= -f2)
OMS_QTY=$(echo "$OMS_OUT" | grep '^KEY oms_qty=' | cut -d= -f2)
OMS_AVG=$(echo "$OMS_OUT" | grep '^KEY oms_avg=' | cut -d= -f2)
OMS_CLIENT=$(echo "$OMS_OUT" | grep '^KEY oms_client_id=' | cut -d= -f2)

OMS_SYM=$(echo "$OMS_OUT" | grep '^KEY oms_symbol=' | cut -d= -f2)
echo "note: OMS paper order symbol: ${OMS_SYM:-$SMOKE_FUTURE_SYMBOL}"
expire

if [ "$OMS_STATE" = "FILLED" ] && [ "${OMS_QTY:-0}" -gt 0 ]; then
    ck "Paper order — OMS MARKET filled" 1 "state=$OMS_STATE qty=$OMS_QTY avg=$OMS_AVG"
else
    ck "Paper order — OMS MARKET filled" 0 "state=${OMS_STATE:-?} qty=${OMS_QTY:-0}"
fi
expire

# propagation: order.filled emitted in-window for this paper order + gauge moved
FILL_LOG=$(log_count "$ISO_OMS" "event=order\.filled .*broker=paper")
TRADES1=$(get_gauge execution_engine_trades_executed_total paper)
if [ "${FILL_LOG:-0}" -ge 1 ]; then
    ck "OMS → Engine propagation — order.filled events" 1 "log lines: $FILL_LOG (2 = known paper+OMS double-publish)"
else
    ck "OMS → Engine propagation — order.filled events" 0 "count=${FILL_LOG:-0}"
fi
if [ "${TRADES0:-0}" != "${TRADES1:-0}" ] && [ -n "$OMS_AVG" ] && [ "$OMS_AVG" != "0.0" ]; then
    ck "OMS → Engine propagation — trade recorded (gauge)" 1 "trades ${TRADES0:-0}->${TRADES1:-0}"
else
    ck "OMS → Engine propagation — trade recorded (gauge)" 0 \
       "trades ${TRADES0:-0}->${TRADES1:-0} avg=$OMS_AVG (avg>0 required for a trade)"
fi
expire

# ---------------------------------------------------------------------------
# 5/6/7/8/9/14/15. Container-code probe: partial + complete fills, position,
#                  portfolio, P&L, duplicates, backlog
# ---------------------------------------------------------------------------
STATE=$(run_probe run "$SMOKE_USER" smoke-part-1 smoke-buy-1 smoke-sell-1)

get_k() { echo "$STATE" | grep "^KEY $1=" | cut -d= -f2-; }
IDS=$(get_k ledger_count_per_id)
POS_QTY=$(get_k pos_qty)
POS_REAL=$(get_k pos_realized)
REF_NET=$(get_k ref_net)
REF_REAL=$(get_k ref_realized)
ACC_REAL=$(get_k acc_realized)
SNAP_REAL=$(get_k snap_realized)
QUEUE_EMPTY=$(get_k queue_empty)
INLINE=$(get_k inline_tasks)
BUFFERED=$(get_k buffered)
expire

PARTIAL_1=$(echo "$IDS" | tr '|' '\n' | grep '^smoke-part-1=' | cut -d= -f2)
BUY_1=$(echo "$IDS" | tr '|' '\n' | grep '^smoke-buy-1=' | cut -d= -f2)
SELL_1=$(echo "$IDS" | tr '|' '\n' | grep '^smoke-sell-1=' | cut -d= -f2)

[ "$PARTIAL_1" = "1" ] && ck "Partial fill — PaperOrderPartiallyFilled → 1 trade" 1 "ledger=1" \
    || ck "Partial fill — PaperOrderPartiallyFilled → 1 trade" 0 "ledger=${PARTIAL_1:-0}"
[ "$BUY_1" = "1" ] && ck "Complete fill — PaperOrderFilled BUY → 1 trade" 1 "ledger=1" \
    || ck "Complete fill — PaperOrderFilled BUY → 1 trade" 0 "ledger=${BUY_1:-0}"
[ "$SELL_1" = "1" ] && ck "Complete fill — PaperOrderFilled SELL → 1 trade" 1 "ledger=1" \
    || ck "Complete fill — PaperOrderFilled SELL → 1 trade" 0 "ledger=${SELL_1:-0}"

if [ "$POS_QTY" = "$REF_NET" ]; then
    ck "Position update — engine net == reference FIFO" 1 "qty=$POS_QTY"
else
    ck "Position update — engine net == reference FIFO" 0 "engine=$POS_QTY ref=$REF_NET"
fi
if [ "$POS_REAL" = "$REF_REAL" ] && [ "$POS_REAL" = "100.0" ]; then
    ck "P&L update — realized == reference (100.0)" 1 "realized=$POS_REAL"
else
    ck "P&L update — realized == reference (100.0)" 0 "engine=$POS_REAL ref=$REF_REAL"
fi
if [ "$ACC_REAL" = "$POS_REAL" ]; then
    ck "P&L update — account realized == position realized" 1 "acc=$ACC_REAL"
else
    ck "P&L update — account realized == position realized" 0 "acc=$ACC_REAL pos=$POS_REAL"
fi
if [ "$SNAP_REAL" = "$POS_REAL" ]; then
    ck "Portfolio update — snapshot realized == position realized" 1 "snap=$SNAP_REAL"
else
    ck "Portfolio update — snapshot realized == position realized" 0 "snap=${SNAP_REAL:-None} pos=$POS_REAL"
fi
DUP_OK=1
for e in "$PARTIAL_1" "$BUY_1" "$SELL_1"; do [ "$e" = "1" ] || DUP_OK=0; done
ck "No duplicate events — one trade per fill id" "$DUP_OK" "per-id counts: $IDS"

if [ "$QUEUE_EMPTY" = "true" ] && [ "${INLINE:-1}" = "0" ] && [ "${BUFFERED:-9999}" -le 2000 ]; then
    ck "No event backlog — queue drained, ring bounded" 1 "buffered=$BUFFERED inline=$INLINE"
else
    ck "No event backlog — queue drained, ring bounded" 0 "queue_empty=$QUEUE_EMPTY inline=$INLINE buffered=$BUFFERED"
fi
expire

# ---------------------------------------------------------------------------
# 13. Memory usage — RSS growth bounded
# ---------------------------------------------------------------------------
MEM1=$(vmrss_kb)
if [ -n "$MEM0" ] && [ -n "$MEM1" ] && [ $((MEM1 - MEM0)) -lt 102400 ]; then
    ck "Memory usage — RSS growth < 100 MiB" 1 "$(( (MEM1 - MEM0) / 1024 )) MiB growth (${MEM0}->${MEM1} kB)"
else
    ck "Memory usage — RSS growth < 100 MiB" 0 "before=${MEM0:-?} after=${MEM1:-?} kB"
fi
expire

# ---------------------------------------------------------------------------
# 10. Restart — docker restart, re-init, engine alive after
# ---------------------------------------------------------------------------
echo "restarting $CONTAINER ..."
ssh_run "docker restart $CONTAINER" >/dev/null
ISO_RESTART=$(remote_date "$(now)")
RESTART_OK=0
for _ in $(seq 1 24); do
    expire
    if curl -fsS -m 10 "$API_URL/health" >/dev/null; then
        RESTART_OK=1
        break
    fi
    sleep 5
done
if [ "$RESTART_OK" = "1" ]; then
    ck "Restart — API healthy after restart" 1 "health 200"
else
    ck "Restart — API healthy after restart" 0 "no health within 120s"
fi
sleep 3
RESTART_LOG=$(log_count "$ISO_RESTART" "Execution Engine v1.0 initialized \(bus running=True")
[ "$RESTART_LOG" -ge 1 ] && ck "Restart — engine re-initialized, bus running" 1 "log lines: $RESTART_LOG" \
    || ck "Restart — engine re-initialized, bus running" 0
expire

LIVE_STATE=$(run_probe liveness "$SMOKE_USER")
LIVE_IDS=$(echo "$LIVE_STATE" | grep '^KEY ledger_count_per_id=' | cut -d= -f2)
LIVE_1=$(echo "$LIVE_IDS" | tr '|' '\n' | grep '^smoke-live-1=' | cut -d= -f2)
[ "$LIVE_1" = "1" ] && ck "Restart — fills processed after restart" 1 "ledger=1" \
    || ck "Restart — fills processed after restart" 0 "ledger=${LIVE_1:-0}"
expire

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo "=== SMOKE SUMMARY ==="
FAILS=0
for r in "${RESULTS[@]}"; do
    IFS='|' read -r name ok detail <<< "$r"
    [ "$ok" = "1" ] || FAILS=$((FAILS + 1))
done
echo "TOTAL: ${#RESULTS[@]} checks, $FAILS FAILURES, elapsed $(( ($(now) - START) ))s"
if [ "$FAILS" = "0" ]; then
    echo
    echo "BUILD STATUS: READY_FOR_PRODUCTION_DEPLOYMENT"
    exit 0
else
    echo
    echo "BUILD STATUS: NOT_READY"
    exit 1
fi