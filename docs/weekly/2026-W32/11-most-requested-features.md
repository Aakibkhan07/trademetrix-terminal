# Weekly Most Requested Features Report — Week 2026-W32 (2026-07-29 → 2026-08-05)

## Feedback received
- Total: feedback|9
- By category: feedback 9;bug 9
- By status: new 9

## Most requested (feature category: title | count)
None

## New feedback this week (date | category | status | title)
08-02|bug|new|E2E prod-readiness test — please ignore;08-02|bug|new|E2E prod-readiness test — please ignore;08-02|bug|new|E2E prod-readiness test — please ignore;08-02|bug|new|E2E prod-readiness test — please ignore;08-02|bug|new|E2E prod-readiness test — please ignore;08-02|bug|new|E2E prod-readiness test — please ignore;08-02|bug|new|E2E prod-readiness test — please ignore;08-02|bug|new|E2E prod-readiness test — please ignore;08-02|bug|new|E2E prod-readiness test — please ignore

## Analysis
- **0 real feature requests this week.** All 9 feedback rows are self-identified E2E test artifacts from the 2026-08-02 prod-readiness run (title "E2E prod-readiness test — please ignore"). The channel itself is live and functional (9 rows persisted end-to-end).
- Roadmap evidence for W32 therefore comes from behavior, not requests: the deepest engaged loop is backtest → builder (38 runs, 20 strategies by 5/3 users); the biggest silent "request" is the broker step (4/31 connected; 2 needs_attention creds) and the Fyers data gaps (option-chain WAF 403, history 404 → KNOWN_ISSUES #2).

## Recommendations
- ✅ DONE 2026-08-05: all 9 rows marked `wontfix` (notes: E2E artifact). Next step for the E2E runner: submit with a `test: true` flag or self-clean so real reports are never mixed with artifacts.
- No feature enters the roadmap from this report. Only the broker-step fixes (re-auth UX, data-source fallbacks) are justified, and those come from behavior evidence (06-funnel, 02-crash).
