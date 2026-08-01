# Phase 2 — Trading Workspace V2: USER_FLOW

## 1. Enter the workspace
- `GET /workspace` (standalone route; sidebar guards unchanged: admins keep /dashboard access, users land here via /portfolio nav).
- Top bar mounts: feed status from `useMarketData` (`connected`, `feedMode`), broker status from `useBrokerCredentials`, search, notifications (alerts count).
- First render subscribes the WS feed to the active watchlist group; ticks batch-flush (existing 2s buffer in `use-market-data`).

## 2. Pick a symbol (watchlist)
- **Single click row** → `setActiveSymbol(symbol)` → center chart reloads (`Chart` `symbol` prop; its own historical fetch + intervals). Right panel recomputes for the symbol. Subscribed symbols stay subscribed.
- **Double click row** → `openQuickOrder(symbol, name)` — Quick Order Drawer opens (existing component, global mount).
- **BUY / SELL buttons** → drawer pre-set to that side.
- **Chart action** → same as single click (no drawer).
- **Analyzer action** → opens analyzer panel for that symbol (lazy chunk).
- **★** toggles favorite → pinned rows float to the top of their group (localStorage `tm_watchlist_groups`).
- **Bell** → price-alert modal (reuses marketdata alert flow + `api.alerts`).

## 3. Chart sync
- Active symbol state lives in the workspace page; watchlist rows highlight the active row; chart quick-switch input (type-ahead via `/market/instruments`) sets the active symbol too. Symbol updates are the ONLY thing that re-fetches chart candles.

## 4. Quick order (drawer)
- Same flow as Phase 1: PAPER default, MARKET/LIMIT, MIS/NRML, lot-aware qty, protection preview, `api.engine.trade` with `source='quick_drawer'`, invalidates `orders`/`positions`/`funds`.
- New: **Advanced** section (collapsed): SL/Target/Trailing SL/Risk%/Capital%/Expected RR fields update the protection preview + risk/RR projections; Estimated Margin shows a placeholder value (no margin API for arbitrary symbols — unchanged). Payload to backend is IDENTICAL (no API change).

## 5. Analyzer panel
- Opens from watchlist action or sidebar "Analyze".
- Computes indicators from `historical` candles (15m, 7d): VWAP, EMA20/50, RSI14, MACD, ADX14, swing S/R, OI/PCR/ATM from `optionChain`, trend + SMC-style labels (structure: HH/HL vs LH/LL), AI summary = rule-based text (e.g., "RSI 61 bullish, price above VWAP, ADX 24 trend strengthening — 2/3 momentum confirm").
- **Trade** → closes panel, opens drawer for the analyzed symbol. **Backtest** → `/backtest`. **Strategy** → `/strategies/builder`.

## 6. Market panel
- Passive: indices summary, top gainers/losers (sorted ticks of the group), VIX, PCR/OI/ATM, S/R for active symbol, AI summary. All read-only.

## 7. Validation checklist (this phase)
- [ ] Quick order places paper order from workspace (drawer)
- [ ] Chart sync on single click + quick switch
- [ ] Realtime ticks update LTP/%/sparkline without page reload
- [ ] Drawer advanced section collapses by default, projects risk/RR
- [ ] Analyzer opens as panel (no route change), indicators render
- [ ] Watchlist groups, pin, alerts work
- [ ] Virtualized watchlist stays smooth with feed on (no unnecessary rerenders)
- [ ] Regression: /portfolio, /marketdata, /trade, /portal intact
