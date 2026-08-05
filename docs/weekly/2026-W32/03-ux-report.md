# Weekly UX Report — Week 2026-W32 (2026-07-29 → 2026-08-05)

## Observed usage signals
- Active users (7d sign-ins): computed above in product health
- Strategies/backtests/orders created per active user
- Broker credential states: fyers/needs_attention=2,fyers/valid=2

## Friction points observed
- **Tracked users (7d): 77 sessions-ids; 74 sessions; 48 bounce sessions (65% single-page) — but includes anonymous landing traffic (see analysis).**
- **Client errors hit 7 of the ~12 tracked signed-in users (20 client_error events)** — the top signature `Uncaught Error: Failed to parse color: color-mix(in srgb, var(--green|red) 30%, transparent)` occurred on 08-01/08-02 only and is fixed in the current build (lightweight-charts now receives parsed hex via `colorVar()`/`mix()` in `components/chart.tsx` and `app/backtest/page.tsx`); 0 client_errors since 08-03.
- 4xx rate breakdown: 405 32.87,204 0,200 9.947e+04,401 917.3,404 48.35,403 58.17,400 2.08,429 785.1,307 12.22,503 178,422 1.001,500 0,201 45.02,409 2.004
- **429s (785/7d ≈ 112/day) concentrate on `/api/v1/alerts/` (610/7d)** — the alerts poller is rate-limited; likely invisible to users but saturating limiter budget.
- **401s (917/7d)**: anonymous `/auth/me` probes on page load (expected pattern, previously filtered).
- Backtest runs grew 19× (2 → 38) but only 5 users ran them; the builder score endpoints are the 2nd/3rd busiest API paths — the builder is the daily surface.

## Feedback capture status
- In-app feedback channel: LIVE (`/api/v1/feedback` + floating button) — 9 submissions this week, all test artifacts (`E2E prod-readiness test — please ignore`), 0 real user reports.
- Support inbox: NONE (gap)
- GitHub issues: see tracker

## Analysis
- Usability-first: the dominant structural UX problem in the data is **not a UI bug but the broker step** — 4/31 accounts connected (13%), same as W31, while every other usage axis grew. The broker connection flow (Fyers re-auth, token expiry) is the single biggest user-facing blocker (see 06-funnel, KNOWN_ISSUES #1).
- Bounce of 65% is inflated by anonymous landing traffic (page.view without signed-in events). Real per-session depth is healthy for engaged sessions: avg 20.7 events/session.
- The 08-01/02 color crash is the only user-visible rendering bug in the week's evidence; it was user-visible (page would fail to render a chart panel) and is now fixed — no further occurrences.
- The alerts 429 is the clearest "UX smell" in API telemetry: a poller pinging `/alerts/` faster than the limiter allows.

## Recommendations
- Track whether anonymous vs signed-in for page.view/session.start (one `is_auth` property) so bounce/funnel are measured on the real user base from W33.
- Throttle the alerts poller or exempt `/alerts/` from the global limiter (evidence: 610 429s/7d on that one path).
- Surface a one-tap "Reconnect Fyers" state on the broker page with the token-expiry countdown (evidence: 2 credentials still needs_attention; every connected-user drop-out in the funnel sits here).
