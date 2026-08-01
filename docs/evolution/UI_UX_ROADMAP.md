# UI_UX_ROADMAP.md

Goal: TradeMetrix becomes a complete Trading Operating System inside the User Portal
(`/portal`) — analyze → build → backtest → deploy → trade → monitor → review → risk —
while staying as simple as Zerodha Kite. Admin panel (`/dashboard`) stays fully separate.

## Design Language (locked, no redesign)

- Dark-first premium fintech, glassmorphism accents (existing tokens.css: violet #8b5cf6,
  cyan #22d3ee, green #34d399, red #f87171).
- Typography: Outfit (display) / DM Sans (body) / JetBrains Mono (numerics) — existing.
- Motion: subtle, ≤200ms, reduced-motion respected (globals.css already does).
- No icon library — continue inline glyphs/SVG (existing convention).
- Responsive: drawers become full-screen sheets on mobile; tables scroll horizontally.

## Phase Roadmap (each ends with regression + CHANGELOG entry)

### Phase 1 — Trade Terminal UX (3-click order)
- Quick Order Drawer (right slide-in, `t-drawer-*`) with: symbol + live LTP, BUY/SELL,
  Quantity (lot stepper), Product (INTRADAY/NRML/DELIVERY), Order Type (MARKET/LIMIT/SL),
  limit price, auto-protection preview (SL −10% / target +15%, from OMS auto-bracket),
  Margin Preview (margin-estimate API), Charges estimate, PAPER/LIVE toggle, Confirm.
- Watchlist rows get BUY/SELL quick actions → drawer opens pre-filled. Row click opens too.
- Success → toast + orders/positions refetch (useExecuteTrade already invalidates).
- Kite-parity: entry surface is wherever the symbol is; no page navigation.

### Phase 2 — Watchlist V2 (trading hub)
- Multi-watchlist tabs: Intraday / Options / Stocks / Swing / ETF (+ custom), persisted
  (localStorage per-list + backend watchlist for server list).
- Rows: Symbol | LTP | % | Volume | OI | Trend sparkline. Realtime via existing ticks store.
- Quick actions per row: BUY, SELL, Chart, Analyzer, Option Chain, Strategy, Backtest, Alert.
- Drag-drop reorder (pointer events), pin-to-top, search/filter.

### Phase 3 — Market Analyzer (in-portal)
- Replaces the standalone analyzer split: analyzer.trademetrix.tech is NOT maintained
  separately — every analysis surface ships inside /portal and reuses backend APIs.
- Timeframes + EMA/VWAP/MACD/RSI/ADX/Volume, S/R, OI/PCR/Max Pain/Option Chain
  (reuse terminal/option-chain), Market Structure/Order Blocks/Liquidity/FVG/SMC,
  AI Market Summary (reuse /ai).
- Every analysis page has action bar: Trade (opens Quick Order Drawer), Backtest,
  Strategy Builder, Watchlist, Portfolio — without leaving the screen.

### Phase 4 — Strategy Builder V2
- Beginner Mode (templates + NL preview → compile) / Advanced Mode (existing block canvas
  at app/strategies/builder — kept, enhanced).
- Natural Language Preview: block graph → readable sentence (client-side render of
  existing block configs via api.builder.preview).
- Templates & Marketplace ready (existing marketplace page).

### Phase 5 — Backtest Engine V2
- Reuse api.backtest.*; add: Performance Report (Net/Gross PnL, Sharpe, Sortino,
  Profit Factor, Max DD, Monthly Returns, Trade List), Equity Curve (reuse
  equity-curve.tsx), TradingView Replay stub, CSV export (downloadCSV pattern exists).
- Execution realism: slippage/brokerage/STT/exchange charges/partial fills (API fields
  already present in BacktestResultsData).

### Phase 6 — User Dashboard (portal Overview V2)
- Widgets: Portfolio, PnL, Orders, Positions, Strategies, Broker Status, Watchlist,
  Market Summary, Recent Trades, Notifications, Upcoming Events. All data via existing
  hooks — pure composition.

### Phase 7 — Performance
- Virtualize long tables, lazy-load below-fold sections, react-query staleTime tuning
  (existing 10s/15s/30s), memoize list rows, optimistic order confirm, skeleton loading
  (SkeletonTable exists), WS tick batching (250ms flush exists — keep).

## Regression Checklist (after every phase)
- [ ] `npx tsc --noEmit` clean
- [ ] `next build` clean
- [ ] /portal loads, tabs intact, RBAC: user sees portal, admin sees dashboard
- [ ] Affected pages render on prod (deployed web container)
- [ ] Order flow verified end-to-end (paper)
- [ ] CHANGELOG.md updated
