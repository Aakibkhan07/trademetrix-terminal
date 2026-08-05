# Weekly User Drop-Off Report — Week 2026-W32 (2026-07-29 → 2026-08-05)

## Session stats (7d)
- sessions7d|74;bounce_sessions|48;avg_events_per_session|20.7

## Crash signatures (7d: key | count)
unknown|119

## Analysis
- **48 of 74 sessions (65%) are single-page** — but this is visitor traffic, not signed-in behavior (the 73 session users vs 12 accounts-signed-in-ever gap). The 20.7 avg events/session across all sessions shows the engaged minority goes deep (terminal + portfolio loops).
- **The only real crash signature in the week: 20 client_error events from 7 users on 08-01/08-02** — `Failed to parse color: color-mix(...)` thrown by lightweight-charts on a chart panel; fixed in the 08-03 build (hex colors now parsed server-side into the chart API). The "unknown|119" key bucket = server-side `api_error` records (main.py ≥500 event) + the unkeyed client_errors; the 500/503 spike maps to the expired-token window (resolved 08-04).
- Funnel drop-offs by stage (tracked, 7d): 73 session-start → 27 click (37%) → 7 client_error → 3 backtest.run → 3 strategy.created → 1 broker.connected. The steepest product drop is broker connection; the steepest session drop (session→click) is visitor-only.
- 429s (785/7d) hit `/api/v1/alerts/` (610) — poller rate-limited; not yet shown to cause user-visible drop-off (no correlated session errors), but it is a server-side "drop" in poll reliability.

## Recommendations
- Add `is_auth` to page.view/session.start so bounce is computed on signed-in sessions only (W33); until then don't ship "reduce bounce" work — the 65% is a visitor artifact.
- The alerts 429: either throttle the poller or exempt the path (P3, one-line).
- Crash funnels: 0 client_errors since the 08-03 fix — keep the color-parse guard in the chart components as the standing rule for any future lightweight-charts work.
