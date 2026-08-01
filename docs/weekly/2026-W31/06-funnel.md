# Weekly Funnel Report — Week 2026-W31 (2026-07-25 → 2026-08-01)

## Tracked activity (7d)
- events=0 users=0 sessions=0 (tracker not deployed yet — baseline week)

## Step conversions (7d: event | users)
No events tracked — client tracker ships with Beta Ops Mode (next release).

## Analysis
- Funnel infrastructure is live server-side (signup → broker.connected → strategy.created → backtest.run → order.placed); the web tracker (session/page/click/error events) ships this week, so W32 will produce the first real funnel.
- Proxy signal for the activation funnel (all-time, from auth/broker/orders tables):
  - total_users=26 → broker_connected=4 (15% connect a broker) → traded=2 (50% of connected trade) → live_traded=1.
  - The biggest structural drop is at signup→broker-connection: 22 of 26 users (85%) never connect a broker. 15 users (58%) never signed in after creating the account.
- Order mix (all-time): 43 orders — FILLED 29, CANCELLED 8, REJECTED 6. Rejections (14%) are a second funnel leak for users who do trade.

## Recommendations
- W32: compare event-funnel vs proxy funnel; expect signup→broker.connected as the dominant drop-off; no action yet — collect two weeks of event data before any onboarding work.
