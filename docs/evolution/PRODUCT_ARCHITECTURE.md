# PRODUCT_ARCHITECTURE.md

Evolving the production TradeMetrix platform. No rewrites — everything builds on the
existing, production-tested architecture. Backend stays unchanged for all UI phases.

## Locked Architecture

```
Landing (ai.trademetrix.tech)
  └── /auth login → RBAC (client-side, app-layout.tsx guard)
        ├── USER → /portal            (standalone layout, no admin shell)
        │          ClientDashboard: Overview | Positions | Orders | Performance | Strategies | Brokers
        └── ADMIN → /dashboard        (AppLayout admin shell)
                   tabs: trade-router, users, brokers, strategies, monitoring, audit, ...

Shared modules used by both surfaces:
  apps/web/lib/api.ts            — single canonical API client (cookie auth + CSRF baked in)
  apps/web/lib/use-market-data.tsx — WebSocket tick feed (wss://api.ai.trademetrix.tech/api/v1/marketdata/ws)
  apps/web/lib/use-events.ts     — SSE execution events
  apps/web/lib/queries/*         — react-query hooks (orders, positions, funds, strategies)
  apps/web/lib/stores/*          — zustand (auth, market ticks, ui)
  apps/web/styles/tokens.css     — design tokens (dark/light)
  apps/web/styles/components.css — ~180 utility classes (t-btn, t-panel, t-table, t-modal, ...)
```

## Evolution Rules

1. **Never** touch backend routes, models, or services during UI phases.
2. **Never** remove existing pages/routes. New UX lands as new components + wiring.
3. Reuse `lib/api.ts`, react-query hooks, `useMarketData`, `useToast`, existing CSS
   classes. Only append new CSS classes where a primitive is missing (e.g. drawer).
4. RBAC separation is absolute: user modules never render inside admin shell and
   vice versa. Portal pages stay standalone (no AppLayout).
5. Every phase ends with regression: `npx tsc --noEmit` + `next build` + live check
   of the affected routes (deploy to prod web container).

## What Already Exists (inventory — reuse, do not duplicate)

| Capability | Existing asset |
|---|---|
| Order entry (basic ticket) | app/terminal/page.tsx (t-order-ticket) |
| Option-chain trade desk | app/trade/page.tsx (CE/PE ticket + PAPER/LIVE) |
| Watchlist (single list) | app/marketdata/page.tsx (localStorage `tm_watchlist_custom`) |
| Option chain read-only | app/terminal/option-chain/page.tsx (PCR, max pain, OI buildup) |
| Visual strategy builder | app/strategies/builder/page.tsx (block canvas, drag-drop) |
| Form strategy builder | app/terminal/builder/page.tsx (legs, strikes, exits) |
| Backtest UI | app/backtest/page.tsx (8 strategies, slippage/brokerage/STT, Monte Carlo) |
| Marketplace | app/marketplace/page.tsx |
| Charts | components/chart.tsx (lightweight-charts v5) + inline SVG charts |
| Realtime ticks | useMarketData (zustand market-store `ticks`) |
| Execution events | useEvents (SSE) |
| Orders/positions/funds | useOrders / usePositions / useFunds (10/15/30s refetch) |
| AI assistant | app/ai/page.tsx (+ /copilot redirect) |
| Journal | app/journal/page.tsx |
| Alerts | app/alerts/page.tsx + watchlist bell |
| Margin estimate | api.marginEstimate → POST /margin-estimate/ (leg-based) |

## Missing Primitives (net-new, minimal)

- **Drawer/sheet** — only `t-modal` exists. Phase 1 adds `t-drawer-*` CSS + a single
  reusable `<QuickOrderDrawer />` mounted once in the root layout.
- **Multi-watchlist + drag-drop** — Phase 2.
- No central types file (duplicates exist) — consolidate ONLY where touched.

## Phase → Surface Map (what evolves where)

| Phase | Files touched (new: N, modified: M) |
|---|---|
| 1 Trade Terminal UX | N: components/quick-order-drawer.tsx · M: styles/components.css, lib/stores/ui-store.ts, app/marketdata/page.tsx, app/layout.tsx |
| 2 Watchlist V2 | N: components/watchlist/ (hub, lists, rows, drag-drop) · M: marketdata page, portal |
| 3 Market Analyzer | N: app/analyzer/* (reuse chart.tsx, option-chain, useMarketData) |
| 4 Strategy Builder V2 | N: builder modes + NL preview (reuse existing block canvas) |
| 5 Backtest V2 | N: backtest reports/export (reuse api.backtest.*) |
| 6 Dashboard | N: portal dashboard widgets (reuse portal stat components) |
| 7 Performance | M: lib/queries/* (react-query caching, skeleton reuse, WS throttle) |
