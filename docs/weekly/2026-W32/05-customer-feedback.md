# Weekly Customer Feedback Summary — Week 2026-W32 (2026-07-29 → 2026-08-05)

## New user reports this week
- 9 submissions, ALL artifacts of the 2026-08-02 prod-readiness E2E (title verbatim: "E2E prod-readiness test — please ignore"). Zero real user reports.

## Themes
- No real user feedback exists yet for W32. The in-app Feedback Center (floating button → `/api/v1/feedback`, categories bug/feature/nps/report) shipped with Beta Ops (08-01) and the tracker was live all week, so this is a **channel-usage** result, not a channel-availability gap.
- The only user-derived evidence of pain remains behavior: 4/31 broker connections, 2/4 of those trading (see 06-funnel); the two `needs_attention` Fyers credentials correlate with the token-expiry incident this week.

## Classification summary
| Priority | Open | Resolved |
|----------|------|----------|
| P0 | 0 | 0 |
| P1 | 0 | 0 |
| P2 | 0 | 0 |
| P3 | 0 | 0 |

## Recommendations
- ✅ DONE 2026-08-05: the 9 test artifacts were marked `wontfix` + notes via PostgREST — the W33 dashboard starts at 0 real items. Require the E2E runner to submit feedback with a `test: true` flag or to clean up after itself.
- Add an NPS/feedback nudge after the 2nd completed backtest (38 runs this week by 5 users — the deepest activity; that is where users have opinions). This is a small, evidence-anchored prompt, not a feature.
