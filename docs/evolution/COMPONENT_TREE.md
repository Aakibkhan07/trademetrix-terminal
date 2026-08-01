# COMPONENT_TREE.md

New components (N) build on existing assets (E). No existing component is rewritten.

## Global Shell (unchanged)

```
app/layout.tsx
└── providers.tsx  [QueryClientProvider → AuthProvider → MarketDataProvider → ToastProvider → StoreInitializer]
    ├── N components/quick-order-drawer.tsx        ← mounted in root layout (global entry)
    └── components/app-layout.tsx (E: admin shell + guard; standalone pages skip shell)
        ├── components/header.tsx (E)
        ├── components/market-ticker.tsx (E)
        ├── components/status-bar.tsx (E)
        └── dashboard tabs (E, admin only)
```

## Quick Order Drawer (Phase 1 — net-new)

```
components/quick-order-drawer.tsx
├── t-drawer-overlay / t-drawer (slide-in right, full-screen on mobile)   [N css]
├── SymbolHeader — symbol + name + live LTP/bid/ask (useMarketData ticks) 
├── SideToggle — BUY / SELL (t-order-side-btn reuse)
├── QtyStepper — lot-size aware +/- (LOT_SIZES map reuse from trade-router-tab)
├── OrderForm — Product select (INTRADAY/NRML/DELIVERY), Order Type
│                (MARKET/LIMIT/SL), Limit Price input (t-input reuse)
├── ProtectionPreview — auto SL −10% / target +15% (matches OMS auto-bracket)
├── CostPreview — Margin Preview (api.marginEstimate, leg-form) + Charges estimate
│                 (client-side: STT/exchange/GST/SEBI/stamp, labeled "estimate")
├── ModeToggle — PAPER/LIVE (t-chip reuse from /trade desk)
└── ConfirmButton — useExecuteTrade mutation (E) → toast → invalidate orders/positions
```

## Watchlist (Phase 2 — evolves app/marketdata/page.tsx)

```
components/watchlist/watchlist-hub.tsx            [N]
├── watchlist-tabs.tsx (Intraday/Options/Stocks/Swing/ETF/custom, localStorage) [N]
├── watchlist-row.tsx (LTP, %, volume, OI, trend sparkline; BUY/SELL/Chart/
│                      Analyzer/Chain/Strategy/Backtest/Alert actions)          [N]
├── drag-drop (pointer-based reorder)                                           [N]
└── reuses: market-store ticks (E), alert modal (E marketdata), QuickOrderDrawer
```

## Analyzer (Phase 3)

```
app/analyzer/* — IndicatorPanel, ChartPanel (E components/chart.tsx), ChainPanel
(E terminal/option-chain internals), AiSummary (E /ai), ActionBar → drawer
```

## Strategy Builder (Phase 4)

```
reuses app/strategies/builder/page.tsx block canvas (E)
├── beginner-mode.tsx (template picker + NL preview)  [N]
└── advanced-mode.tsx = existing canvas (E, kept)
```

## Backtest (Phase 5)

```
app/backtest — reuses api.backtest.* + EquityCurve (E)
├── performance-report.tsx (Sharpe/Sortino/PF/DD/monthly)  [N]
├── trade-list.tsx                                          [N]
└── csv export (E downloadCSV pattern)
```

## Portal Dashboard (Phase 6)

```
app/portal Overview V2 — widget grid (portfolio/PnL/orders/positions/strategies/
broker status/watchlist/summary/recent trades/notifications) — pure composition of E hooks
```

## Existing primitives reused everywhere

| Primitive | Source |
|---|---|
| Buttons/badges/chips/tables/tabs/inputs | styles/components.css (E) |
| Modal | t-modal (E) |
| Toast | useToast (E) |
| Skeleton / EmptyState / ErrorMessage | components/skeleton.tsx, empty-state.tsx, error-message.tsx (E) |
| Charts | components/chart.tsx, equity-curve.tsx (E) |
| Order status badges | STATUS_BADGE maps (E terminal/trade pages) |
| Money/number formatting | fmtInt / formatters (E) |
