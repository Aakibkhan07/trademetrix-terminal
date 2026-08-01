#!/usr/bin/env bash
# TradeMetrix Weekly Report Generator (Founder Mode)
# Usage: TMX_VPS_PASSWORD='...' bash infra/scripts/weekly_report.sh
# Output: docs/weekly/<YYYY-Wnn>/{01-product-health,02-crash-report,03-ux-report,04-performance-report,05-customer-feedback}.md
# Data sources: Prometheus (VPS 127.0.0.1:9090), Supabase (remote Postgres), API container logs.
set -euo pipefail

VPS_HOST="${TMX_VPS_HOST:-root@187.127.185.56}"
SSH_PASS="${TMX_VPS_PASSWORD:-}"
SUPA_PW="${TMX_SUPABASE_PASSWORD:-${SSH_PASS}}"
WEEK=$(date +%G-W%V)
OUT="/Users/aakib/trademetrix-terminal/docs/weekly/${WEEK}"
mkdir -p "$OUT"

ssh_cmd() {
  if [ -n "$SSH_PASS" ]; then
    sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$VPS_HOST" "$@"
  else
    ssh -o StrictHostKeyChecking=no "$VPS_HOST" "$@"
  fi
}

pq() {
  # psql on VPS hitting remote Supabase
  ssh_cmd "PGPASSWORD='$SUPA_PW' psql 'postgresql://postgres@db.nwutlfuowiulfpbsrldn.supabase.co:5432/postgres?sslmode=require' -t -A -c \"$1\" 2>&1"
}

prom() {
  ssh_cmd "curl -s \"http://127.0.0.1:9090/api/v1/query?query=$1\" 2>/dev/null | python3 -c '
import sys, json
r = json.load(sys.stdin)
for res in r.get(\"data\", {}).get(\"result\", []):
    m = res.get(\"metric\", {})
    v = res.get(\"value\", [None, \"\"])[1]
    label = \"\"
    for k in (\"path\", \"status\", \"breaker\", \"le\"):
        if k in m:
            label = m[k] + \" \"
            break
    print(f\"{label}{float(v):.4g}\")
' 2>/dev/null" || echo N/A
}

num() { echo "$1" | awk '{printf "%.0f", $1}'; }
join() { echo "$1" | tr '\n' ', ' | sed 's/[, ]*$//'; }

week_start=$(date -v-7d +%Y-%m-%d)
week_end=$(date +%Y-%m-%d)

# ---------- data collection ----------
req_total=$(num "$(prom "sum(increase(http_requests_total%5B7d%5D))")")
req_5xx=$(num "$(prom "sum(increase(http_requests_total%7Bstatus=~%225..%22%7D%5B7d%5D))")")
req_4xx=$(num "$(prom "sum(increase(http_requests_total%7Bstatus=~%224..%22%7D%5B7d%5D))")")
req_by_status=$(prom "sum(increase(http_requests_total%5B7d%5D))%20by%20(status)")
top_paths=$(prom "topk(12,sum(rate(http_requests_total%5B7d%5D))%20by%20(path))")
breakers=$(prom "circuit_breaker_state")
exceptions=$(num "$(prom "sum(increase(exceptions_total%5B7d%5D))")")
p95=$(prom "histogram_quantile(0.95,sum(rate(http_request_duration_seconds_bucket%5B7d%5D))%20by%20(le))" | awk '{printf "%.3fs", $1}')
caddy_p95=$(prom "histogram_quantile(0.95,sum(rate(caddy_http_response_duration_seconds_bucket%5B7d%5D))%20by%20(le))" | awk '{printf "%.3fs", $1}')

users=$(pq "select 'users='||count(*) from auth.users")
signins=$(pq "select 'signed_in_ever='||count(*) from auth.users where last_sign_in_at is not null; select 'last7d_signins='||count(*) from auth.users where last_sign_in_at >= now() - interval '7 days'")
usage=$(pq "select 'strategies='||count(*) from strategies; select 'builder_strategies='||count(*) from builder_strategies; select 'backtest_runs='||count(*) from backtest_runs; select 'orders='||count(*) from orders; select 'creds='||count(*) from broker_credentials")
orders_by_status=$(pq "select status||'='||c from (select status, count(*) c from orders group by status) t order by c desc")
creds=$(pq "select broker||'/'||token_status||'='||c from (select broker, token_status, count(*) c from broker_credentials group by broker, token_status) t order by c desc")
runs_by_user=$(pq "select 'runs_by_user='||count(distinct user_id)||' total_runs='||count(*) from backtest_runs")

ex_log=$(ssh_cmd "docker logs trademetrix_api --since 168h 2>&1 | grep -oE 'CircuitBreakerError|Token refresh failed for|access token has expired|Exception in ASGI application|async_safe_single query failed' | sort | uniq -c | sort -rn | head -6" || true)
safeq=$(ssh_cmd "docker logs trademetrix_api --since 168h 2>&1 | grep -c 'async_safe_single query failed' || true")
restarts=$(ssh_cmd "docker inspect trademetrix_api --format 'api restarts={{.RestartCount}} started={{.State.StartedAt}}'; docker inspect trademetrix_web --format 'web restarts={{.RestartCount}} started={{.State.StartedAt}}'")
mem=$(ssh_cmd "docker stats --no-stream --format '{{.Name}} mem={{.MemUsage}} cpu={{.CPUPerc}}' 2>/dev/null | head -8" || true)

users=$(join "$users"); signins=$(join "$signins"); usage=$(join "$usage")
creds=$(join "$creds"); orders_by_status=$(join "$orders_by_status")
breakers=$(join "$breakers"); req_by_status=$(join "$req_by_status"); top_paths=$(join "$top_paths")

# ---------- report 1: product health ----------
cat > "$OUT/01-product-health.md" <<EOF
# Weekly Product Health Report — Week ${WEEK} (${week_start} → ${week_end})

## Summary
- Users: ${users} · Sign-ins: ${signins}
- Adoption: ${usage}
- Backtest runs: ${runs_by_user//$'\n'/, }
- Requests (7d): ${req_total} · 5xx: ${req_5xx} · 4xx: ${req_4xx}
- Exceptions (7d): ${exceptions} · Breakers: ${breakers//$'\n'/ · }
- Credentials: ${creds}

## Orders by status (7d)
${orders_by_status}

## Top paths by rate (7d)
${top_paths}

## Open P0/P1 issues
(GitHub labels p0/p1 — populated by triage)

## Analysis
(Author — observations grounded in the data above)

## Recommendations
(Author — improvements from observed behavior only)
EOF

# ---------- report 2: crash report ----------
cat > "$OUT/02-crash-report.md" <<EOF
# Weekly Crash Report — Week ${WEEK} (${week_start} → ${week_end})

## Restarts
${restarts}

## Exception signatures (7d, API logs)
${ex_log}

## Recurring warnings
- \`async_safe_single query failed: 'NoneType' object has no attribute 'data'\`: ${safeq} occurrences in 7d

## Metrics
- exceptions_total increase (7d): ${exceptions}
- 5xx requests (7d): ${req_5xx} (${req_by_status//$'\n'/ · })

## Analysis
(Author)

## Recommended fixes
(Author — with P0–P3 classification)
EOF

# ---------- report 3: UX report ----------
cat > "$OUT/03-ux-report.md" <<EOF
# Weekly UX Report — Week ${WEEK} (${week_start} → ${week_end})

## Observed usage signals
- Active users (7d sign-ins): computed above in product health
- Strategies/backtests/orders created per active user
- Broker credential states: ${creds}

## Friction points observed
- (e.g., 15 of 26 users never signed in; no onboarding completion data)
- 4xx rate breakdown: ${req_by_status//$'\n'/ · }

## Feedback capture status
- In-app feedback channel: NONE (gap)
- Support inbox: NONE (gap)
- GitHub issues: see tracker

## Analysis
(Author — usability-first, behavior-observed-only)

## Recommendations
(Author)
EOF

# ---------- report 4: performance report ----------
cat > "$OUT/04-performance-report.md" <<EOF
# Weekly Performance Report — Week ${WEEK} (${week_start} → ${week_end})

## Traffic (7d)
- Total requests: ${req_total}
- By status: ${req_by_status//$'\n'/ · }
- p95 latency: API ${p95} · edge (Caddy) ${caddy_p95}

## Error rates
- 5xx (7d): ${req_5xx} · 4xx (7d): ${req_4xx}

## Capacity / resources
${mem}

## Circuit breakers
${breakers//$'\n'/ · }

## Analysis
(Author)

## Recommendations
(Author)
EOF

# ---------- report 5: customer feedback ----------
cat > "$OUT/05-customer-feedback.md" <<EOF
# Weekly Customer Feedback Summary — Week ${WEEK} (${week_start} → ${week_end})

## New user reports this week
(One entry per report: user, verbatim, channel, P0–P3 classification, status)

## Themes
(Author — cluster of recurring themes)

## Classification summary
| Priority | Open | Resolved |
|----------|------|----------|
| P0 | 0 | 0 |
| P1 | 0 | 0 |
| P2 | 0 | 0 |
| P3 | 0 | 0 |

## Recommendations
(Author — improvements from feedback only; no invented features)
EOF

# ---------- report 12: top 10 issues ----------
cat > "$OUT/12-top-10-issues.md" <<EOF
# Weekly Top 10 Issues — Week ${WEEK} (${week_start} → ${week_end})

| # | Issue | Priority | User impact (evidence) | Status |
|---|-------|----------|------------------------|--------|
| 1 | (from GitHub, ranked by priority × user impact) | P? | (cite analytics/feedback/metrics) | Open/In progress/Resolved |
| 2 |  |  |  |  |
| 3 |  |  |  |  |
| 4 |  |  |  |  |
| 5 |  |  |  |  |
| 6 |  |  |  |  |
| 7 |  |  |  |  |
| 8 |  |  |  |  |
| 9 |  |  |  |  |
| 10 |  |  |  |  |

## Closed this week
(Author — issues resolved, with verification evidence)

## Analysis
(Author — what the top 10 say about reliability and user pain)
EOF

# ---------- report 13: next week priorities ----------
cat > "$OUT/13-next-week-priorities.md" <<EOF
# Next Week Priorities — Week ${WEEK} (${week_start} → ${week_end})

## Priority actions for next week
| Action | Evidence source (gate: analytics / feedback / ticket / metrics / security) | Priority |
|--------|-----------------------------------------------------------------------------|----------|
| (action) | (cite the report/issue/metric that justifies it — opinion alone is not sufficient) | P0–P3 |
|  |  |  |
|  |  |  |

## Mission alignment
- Paying customers: (current count → goal: first 10)
- Beta user support: (open issues under SLA)
- Production bugs: (open P0/P1)
- UX improvements: (evidence-backed changes shipped)

## Explicitly NOT doing
- (anything without evidence backing — recorded here so scope creep is visible)
EOF

echo "Week ${WEEK} report skeletons written to ${OUT}"
echo "Next: author the Analysis sections from the real data, then file/triage GitHub issues."
