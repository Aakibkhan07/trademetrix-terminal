# Phase 2 — Trading Workspace V2: COMPONENT_TREE

```
app/workspace/page.tsx                      (new — layout + state owner)
├── components/workspace/sidebar.tsx        (new — 56px icon nav)
├── components/workspace/top-bar.tsx        (new — status/search/bell)
├── components/workspace/watchlist-panel.tsx (new — tabs + virtualization)
│   ├── components/workspace/watch-row.tsx  (new — memoized row, virtualized)
│   ├── components/workspace/mini-chart.tsx (new — SVG sparkline from ticks)
│   └── components/workspace/indicator.ts   (new — pure math: ema/rsi/macd/adx/vwap/swings)
├── components/chart.tsx                    (REUSED — symbol prop sync, no changes)
├── components/workspace/market-panel.tsx   (new — summary/gainers/losers/VIX/PCR/OI/ATM/SR/AI)
├── components/workspace/analyzer-panel.tsx (new — LAZY via next/dynamic, ssr:false)
│   └── components/workspace/indicator.ts   (shared)
└── components/quick-order-drawer.tsx       (EXTENDED — collapsible Advanced section)

Shared state (no new stores):
- useMarketData()  → ticks, connected, feedMode, subscribe, startFeed  (reused)
- useUIStore()     → quickOrder.openQuickOrder/close (reused)
- useAuth()        → user gate (reused)
- useBrokerCredentials() → broker status (reused hook)
- useOrders/usePositions/useFunds → react-query (reused; invalidated by drawer)
- useToast()       → feedback (reused)
- api.marketdata.{watchlist,historical,optionChain} / api.alerts.* / api.market.instruments (reused)

New localStorage keys:
- tm_watchlist_groups  → { groupId: WatchItem[] } (Intraday/Options/Stocks/Swing/ETF/All)
- tm_watchlist_favs    → string[] of pinned symbols

Explicitly NOT duplicated:
- chart.tsx (center), drawer (global), ticker (market-ticker.tsx — top strip),
  modal/alert flows (marketdata page logic moved behind the same api.alerts calls),
  indicator math is new (no existing indicator component exists).
```

## Data flow
- Workspace page owns `activeSymbol` + `activeGroup`. Rows call `useMarketData()` per-row
  through the memoized `WatchRow` (React.memo, tick prop) — windowed render caps per-flush
  re-render cost; feed batches ticks every ~2s (existing flush timer).
- Chart fetches candles itself (`historical`), keyed by `activeSymbol`.
- Analyzer fetches `historical` + `optionChain` on open, memoized per symbol.
- Drawer remains globally mounted; workspace rows call `openQuickOrder`.
