# Weekly Funnel Report — Week 2026-W32 (2026-07-29 → 2026-08-05)

## Tracked activity (7d)
- events=1529 users=77 sessions=74

## Step conversions (7d: event | users)
page.view | 73;session.start|73;click|27;client_error|7;backtest.run|3;strategy.created|3;broker.connected|1

## Analysis
- First real tracked-week (tracker shipped 08-01). 73 session-start/page-view users (mix of anonymous visitors and signed-in users; user_id resolution is server-side, so anonymous visits are sessions) → 27 users clicked (37%) → 7 hit a client error → 3 ran a backtest → 3 created a builder strategy → 1 connected a broker.
- **The structural drop-off is the same as the W31 proxy funnel and unchanged by product work: broker connection.** Broker-connected = 1 tracked + 4 all-time (13% of 31 accounts); of the 3 backtest power-users this week, none are in the broker-connected set — they use the backtest/builder surfaces that don't require a broker.
- Click-rate 37% of session users is depressed by anonymous landing sessions (65% bounce); for signed-in sessions, avg depth is 20.7 events/session.
- client_error 7 users is the first measurable crash funnel (20 events, all pre-08-03 build; fixed since).
- Activation funnel (all-time, proxy): 31 signups → 4 broker_connected (13%) → 2 traded (6%) → 1 live trade (3%).

## Recommendations
- W33 gate: measure with an `is_auth` property split so the funnel excludes anonymous landing traffic; until then treat "session users" as visitors, not signups.
- The one conversion worth engineering this week: broker step (4/31). Re-auth UX + token-expiry countdown on the Brokers page (KNOWN_ISSUES #1) is the highest-leverage funnel change with direct user evidence.
- Do not yet add onboarding work beyond broker step: no other stage shows a drop-off worth a change.
