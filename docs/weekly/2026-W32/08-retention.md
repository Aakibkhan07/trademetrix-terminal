# Weekly Retention Report — Week 2026-W32 (2026-07-29 → 2026-08-05)

## Cohort table (cohort | users | returned after week 1)
2026-07-27 | 22|3;2026-08-03|55|0

## Analysis
- First real cohorts, but the 08-03 cohort of 55 is **inflated by anonymous session-ids** (only 31 accounts exist; an anonymous visitor counts as a fresh "user" every week). Do not interpret it as 55 new signups.
- The only defensible cohort read: the 07-27 cohort (22 accounts, the W31 signup week) had **3 return in the week after** — 14% weekly return on the account base; combined with 12 accounts signed-in-ever and 3 in the last 7 days, retention is a small core, not a returning majority.
- No second-week cohort math is possible yet (needs one more full week); treat 08-03 numbers as a floor to re-measure in W33 with the auth split.

## Recommendations
- Cohort query must key on `user_id` only (drop the session_id fallback) so anonymous visitors stop creating phantom cohorts; re-run the table in W33.
- No retention work before W33–W34 cohort baselines exist; the only retention-adjacent change now is broker re-auth (the 2 needs_attention rows are the likeliest churn point for connected users).
