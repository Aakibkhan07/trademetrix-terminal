# Weekly Most Used Features Report — Week 2026-W31 (2026-07-25 → 2026-08-01)

## Top tracked events (7d: event | count | users)
No event data yet (tracker ships this week).

## All-time events: 0
- Errors (7d): errors7d=0

Feature usage proxies (all-time, from DB tables):
- Builder strategies created: 7 (vs 9 legacy strategies — the builder is the primary path already)
- Backtest runs: 2 (1 user)
- Orders placed: 43 (2 users; FILLED 29 / CANCELLED 8 / REJECTED 6)
- Broker connections: 4 (1 valid token + 3 needs_attention)

## Analysis
- Inferred usage order before event data: Strategy Builder (7 strategies) > order execution (43 orders by 2 users) > backtests (2 runs by 1 user).
- REJECTED 6 of 43 orders (14%) is the largest quality signal in usage data this week; earlier evidence pointed at duplicate-order/cooldown rules and Fyers token expiry as causes.
- Cannot rank page-level features (option chain, backtest exports, etc.) until click/page events accumulate.

## Recommendations
- W32 report: first real ranking; compare against the proxy ranking above.
- Track order rejection reasons from W32 onward (server-side order.rejected event) to quantify the 14% rejection cost.
