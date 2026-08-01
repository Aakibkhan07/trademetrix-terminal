# USER_FLOW.md

Canonical user journeys. All flows stay inside the User Portal surface; the Quick Order
Drawer is global so every entry point (watchlist, chain, analyzer, portfolio) is 3 clicks.

## A. The 3-Click Order (Phase 1 target — Kite parity)

```
1. Click symbol row (watchlist / option chain / anywhere symbol appears)
2. Quick Order Drawer opens pre-filled (side=LTP context, qty=1 lot, product=INTRADAY)
   → adjust BUY/SELL, qty, order type, limit price; Margin Preview + Charges visible
3. Confirm → order placed → toast + orders/positions refresh
```

Explicit BUY/SELL buttons on watchlist rows skip the side selection (still 3 clicks).

## B. Login → First Trade (new user)

```
/auth signup → /onboarding → /portal
  → Brokers tab: Activate + Fyers authorize (existing flow)
  → Watchlist (marketdata): add symbols
  → BUY on a row → Quick Order Drawer → Confirm (PAPER default) → order filled (paper)
```

## C. Analyze → Strategy → Backtest → Deploy → Trade (full TOS journey)

```
/portal → Market Analyzer (Phase 3): pick symbol, timeframe, indicators
        → "Strategy" action → Strategy Builder (Phase 4) prefilled with symbol context
        → Builder: Beginner (template/NL) or Advanced (block canvas, existing)
        → Save → Backtest Lab (Phase 5): run → performance report → export CSV
        → Deploy (existing user-strategies deploy) → engine run starts
        → Monitor: portal Positions/Orders/Performance tabs + alerts
        → Risk: existing /risk settings + kill switch
```

## D. Option Trading (existing trade desk + new drawer)

```
/trade (existing desk): pick underlying + expiry → chain → CE/PE → ticket
/marketdata → Options watchlist row → BUY → Quick Order Drawer (auto ITM snap on backend)
```

## E. Admin (unchanged, isolated)

```
/dashboard — business tabs. No user-portal modules render here (RBAC enforced in
app-layout.tsx + admin/layout.tsx — untouched).
```

## F. Realtime behavior expectations

- LTP in drawer/watchlist updates via existing WS tick store (250ms flush).
- Order state changes arrive via SSE (useEvents) + refetch invalidation.
- PAPER default; LIVE requires explicit toggle (same as existing /trade desk).
