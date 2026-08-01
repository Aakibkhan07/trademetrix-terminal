# Weekly UX Report — Week 2026-W31 (2026-07-25 → 2026-08-01)

## Observed usage signals
- Active users (7d sign-ins): computed above in product health
- Strategies/backtests/orders created per active user
- Broker credential states: fyers/needs_attention=3,fyers/valid=1

## Friction points observed
- (e.g., 15 of 26 users never signed in; no onboarding completion data)
- 4xx rate breakdown: 400 1.077,200 4.858e+04,404 59.09,403 8.124,405 8.727,401 469.8,429 652.7,307 2.006,503 87.06,201 4.011

## Feedback capture status
- In-app feedback channel: NONE (gap)
- Support inbox: NONE (gap)
- GitHub issues: see tracker (public repo)

## Analysis
- **Usability signals are scarce because users are scarce — that is the finding.** 15/26 accounts never signed in; the 11 who did produced no product usage beyond the founder's. We cannot yet observe onboarding friction, error-message comprehension, or workflow completion because the funnel is empty.
- **Observed friction signals worth noting even in the empty funnel:**
  1. **Broker re-auth is a hard stop.** 3 of 4 credentials sit in `needs_attention`; the only fix is a manual OAuth dance the user cannot complete from inside the flow without guidance (watchdog only alerts via Telegram, which is unconfigured — `[DEV] No Telegram configured`).
  2. **429 responses (653/7d) hit during normal sessions** (UI polling pattern) — a user mid-flow can be throttled for 60 s with no visible explanation.
  3. **401s (470/7d)** — mostly session-expiry churn; no observed UX impact yet, but token-expiry UX (redirect to login with context) is unverified.
  4. **404s (59/7d)** — stale client routes hitting removed endpoints; indicator the web client may call endpoints the API no longer serves.
- **No feedback channel exists** — no in-app "report a problem", no support address, no analytics. Every user report today would arrive out-of-band (email/DM) and be unrecoverable.

## Recommendations
1. **P1 — add a feedback path before the next beta wave**: a support email address in the app shell (footer) + a "Report a problem" entry that captures the current URL and recent action. This is observation infrastructure, not a feature.
2. **P2 — broker re-auth UX**: when a credential is `needs_attention`, surface a one-line action in the UI ("Reconnect Fyers — token expired") instead of letting users discover it via failed orders. (Observed: 3 broken creds + zero in-app guidance.)
3. **P2 — diagnose the 429 path**: confirm which endpoints trigger the rate limiter during polling and, if it's the pollers, raise the authenticated polling budget. Throttling a paying user mid-dashboard is worse than the traffic it saves at this scale.
4. **P3 — re-engage the 15 dormant accounts** with a single onboarding email once the feedback path exists (activation is unmeasurable without a signal to measure).
