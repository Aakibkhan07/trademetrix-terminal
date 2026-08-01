#!/usr/bin/env bash
# TradeMetrix Beta Ops — Weekly Analytics Report Generator
# Usage: TMX_VPS_PASSWORD='...' TMX_SUPABASE_PASSWORD='...' bash infra/scripts/analytics_report.sh
# Output: docs/weekly/<YYYY-Wnn>/06-funnel.md 07-activation.md 08-retention.md
#         09-most-used-features.md 10-drop-off.md 11-most-requested-features.md
# Data source: Supabase (remote Postgres) — analytics_events + feedback_items.
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
  # psql on VPS hitting remote Supabase (multiple statements; rows pipe-joined)
  ssh_cmd "PGPASSWORD='$SUPA_PW' psql 'postgresql://postgres@db.nwutlfuowiulfpbsrldn.supabase.co:5432/postgres?sslmode=require' -t -A -F '|' -c \"$1\" 2>&1" | tr '\n' '; ' | sed 's/; *$//' || echo N/A
}

ev_filter() {
  echo "created_at >= now() - interval '7 days' and event in ('signup','login','page.view','click','scroll.depth','session.start','strategy.created','backtest.run','order.placed','broker.connected','client_error')"
}

week_start=$(date -v-7d +%Y-%m-%d)
week_end=$(date +%Y-%m-%d)

# ---------- data collection ----------
summary=$(pq "select 'events='||count(*)||' users='||count(distinct coalesce(user_id::text,session_id))||' sessions='||count(distinct session_id) from analytics_events where created_at >= now() - interval '7 days'")
events_total=$(pq "select count(*) from analytics_events")
errors7=$(pq "select 'errors7d='||count(*) from analytics_events where created_at >= now() - interval '7 days' and event in ('error','crash','unhandled_error','api_error','client_error')")

funnel=$(pq "select event, count(distinct coalesce(user_id::text,session_id)) from analytics_events where $(ev_filter) group by event order by 2 desc")
activation=$(pq "select 'total_users', count(*) from auth.users; select 'broker_connected', count(distinct user_id) from broker_credentials; select 'traded', count(distinct user_id) from orders; select 'live_traded', count(distinct user_id) from orders where is_paper = false")
dau7=$(pq "select to_char(created_at,'YYYY-MM-DD'), count(distinct coalesce(user_id::text,session_id)) from analytics_events where $(ev_filter) group by 1 order by 1")

top_events=$(pq "select event, count(*), count(distinct coalesce(user_id::text,session_id)) from analytics_events where $(ev_filter) group by event order by 2 desc limit 15")
sessions_stats=$(pq "select 'sessions7d', count(distinct session_id) from analytics_events where created_at >= now() - interval '7 days'; select 'bounce_sessions', count(*) from (select session_id from analytics_events where created_at >= now() - interval '7 days' and event='page.view' group by session_id having count(distinct properties->>'path') = 1) t; select 'avg_events_per_session', round(count(*)::numeric/nullif(count(distinct session_id),0),1) from analytics_events where created_at >= now() - interval '7 days'")
retention=$(pq "with base as (select coalesce(user_id::text,session_id) uid, date_trunc('week', created_at) act_wk, min(date_trunc('week', created_at)) over (partition by coalesce(user_id::text,session_id)) first_wk from analytics_events) select to_char(first_wk,'YYYY-MM-DD'), count(distinct uid), count(distinct case when act_wk > first_wk then uid end) from base group by 1 order by 1")
crashes_by_key=$(pq "select coalesce(properties->>'key','unknown'), count(*) from analytics_events where created_at >= now() - interval '7 days' and event in ('client_error','api_error') group by 1 order by 2 desc limit 8")

feedback_stats=$(pq "select 'feedback', count(*) from feedback_items; select category, count(*) from feedback_items group by 1")
feedback_by_status=$(pq "select status, count(*) from feedback_items group by 1")
requested=$(pq "select coalesce(title,'(no title)'), count(*) from feedback_items where category='feature' group by 1 order by 2 desc limit 10")
feedback7=$(pq "select to_char(created_at,'MM-DD'), category, status, left(coalesce(title,''),40) from feedback_items where created_at >= now() - interval '7 days' order by 1")

# ---------- report 6: funnel ----------
cat > "$OUT/06-funnel.md" <<EOF
# Weekly Funnel Report — Week ${WEEK} (${week_start} → ${week_end})

## Tracked activity (7d)
- ${summary}

## Step conversions (7d: event | users)
$(echo "$funnel" | sed 's/|/ | /')

## Analysis
(Author — conversion gaps between steps, most common drop-off point)

## Recommendations
(Author)
EOF

# ---------- report 7: activation ----------
cat > "$OUT/07-activation.md" <<EOF
# Weekly Activation Report — Week ${WEEK} (${week_start} → ${week_end})

## Activation stages (all-time: stage | users)
$(echo "$activation" | sed 's/|/ | /')

## Daily active tracked users (7d: date | users)
$(echo "$dau7" | sed 's/|/ | /')

## Analysis
(Author — where signups stall: broker connection, first strategy, first order)

## Recommendations
(Author)
EOF

# ---------- report 8: retention ----------
cat > "$OUT/08-retention.md" <<EOF
# Weekly Retention Report — Week ${WEEK} (${week_start} → ${week_end})

## Cohort table (cohort | users | returned after week 1)
$(echo "$retention" | sed 's/|/ | /')

## Analysis
(Author — cohort size trend, returning-user share)

## Recommendations
(Author)
EOF

# ---------- report 9: most used features ----------
cat > "$OUT/09-most-used-features.md" <<EOF
# Weekly Most Used Features Report — Week ${WEEK} (${week_start} → ${week_end})

## Top tracked events (7d: event | count | users)
$(echo "$top_events" | sed 's/|/ | /')

## All-time events: ${events_total}
- Errors (7d): ${errors7}

## Analysis
(Author — what real users actually do vs what we expected)

## Recommendations
(Author)
EOF

# ---------- report 10: drop-off ----------
cat > "$OUT/10-drop-off.md" <<EOF
# Weekly User Drop-Off Report — Week ${WEEK} (${week_start} → ${week_end})

## Session stats (7d)
- ${sessions_stats}

## Crash signatures (7d: key | count)
${crashes_by_key:-None}

## Analysis
(Author — where users abandon: bounce sessions, dead pages, error bursts)

## Recommendations
(Author)
EOF

# ---------- report 11: most requested ----------
cat > "$OUT/11-most-requested-features.md" <<EOF
# Weekly Most Requested Features Report — Week ${WEEK} (${week_start} → ${week_end})

## Feedback received
- Total: $(echo "$feedback_stats" | cut -d';' -f1)
- By category: $(echo "$feedback_stats" | sed 's/^[^;]*;\?//;s/|/ /g')
- By status: $(echo "$feedback_by_status" | sed 's/|/ /g')

## Most requested (feature category: title | count)
${requested:-None}

## New feedback this week (date | category | status | title)
${feedback7:-None}

## Analysis
(Author — evidence for roadmap: only requests backed by user behavior)

## Recommendations
(Author)
EOF

echo "Week ${WEEK} analytics reports written to ${OUT}"
echo "Next: author the Analysis sections from the real data, then file/triage GitHub issues."
