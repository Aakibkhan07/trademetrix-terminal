# Weekly Activation Report — Week 2026-W31 (2026-07-25 → 2026-08-01)

## Activation stages (all-time: stage | users)
total_users | 26; broker_connected|4; traded|2; live_traded|1

## Daily active tracked users (7d: date | users)
No event data yet (tracker ships this week).

Sign-in activity (all-time): 11 of 26 users signed in at least once; 9 signed in within the last 7 days.

## Analysis
- Activation funnel: 26 signups → 4 broker connections (15%) → 2 users who placed trades (8%) → 1 live trade.
- Stall points, in order of magnitude:
  1. Signup → first sign-in: 15 of 26 accounts (58%) never signed in after creation.
  2. Signup → broker connection: 85% never connect a broker (credentials: 4 total, 3 needs_attention — all Fyers).
  3. Connected → traded: 2 of 4 connected users placed orders.
- Usage depth for active users is shallow: 9 strategies total (7 builder), 2 backtest runs by a single user.
- One known external blocker distorts activation: Fyers token expired this week (all 3 needs_attention creds), so some users may have attempted connection and failed at the broker step.

## Recommendations
- Do not act yet — the 58% never-signed-in figure predates the in-app feedback/analytics channels; re-measure with the event tracker for 2 weeks.
- If the never-signs-in share persists, it is a channel-quality (lead) question, not a product question — evidence must separate the two.
