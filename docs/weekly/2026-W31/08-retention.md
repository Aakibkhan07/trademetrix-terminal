# Weekly Retention Report — Week 2026-W31 (2026-07-25 → 2026-08-01)

## Cohort table (cohort | users | returned after week 1)
No event cohorts yet — tracker ships this week; first cohorts will appear in W32+.

Proxy retention signals (all-time, from auth + strategy tables):
- 26 accounts; 11 signed in ever; 9 signed in in the last 7 days.
- Backtest runs: 2 runs, both by a single user (1 of 26 = 4% reach the most complex feature).
- Strategies: 9 live/user strategies, 7 builder strategies — the most heavily used feature after sign-in.

## Analysis
- No cohort math is possible from week 1 data. The only defensible statement: the platform retains a small core (≈9 weekly actives ≈ 35% of accounts) and the tail is dormant (15 accounts never active).
- The 1 user who ran 2 backtests is the only evidence of deep feature usage — insufficient to rank features yet.
- Retention can only be attributed after the event tracker records weekly cohorts; until then, treat sign-in counts as noise floor, not retention.

## Recommendations
- Baseline week. Measure W32–W34 with event cohorts (weekly returned-share) before judging retention.
- Open #6 (dormant accounts) already tracks the 15-never-signed-in tail as a P3 backlog item — do not action until cohorts exist.
