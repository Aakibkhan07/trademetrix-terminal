# Phase 2 — Trading Workspace V2: WIREFRAME

Route: `/workspace` (standalone, like `/portfolio`). One screen replaces the page-hopping flow
(Portfolio → MarketData → Trade → Orders → Positions).

```
┌──────────┬─────────────────────────────────────────────────────────────┬──────────────────┐
│ SIDEBAR  │ TOP BAR                                                     │                  │
│ (56px)   │ ● Market Status (feed dot) │ ● Broker Status │ 🔍 Search │ 🔔               │
│ Home     ├─────────────────────────────────────────────────────────────┤                  │
│ Trade    │ LEFT COLUMN        │ CENTER                     │ RIGHT      │                  │
│ Analyze  │ WATCHLIST (tabs)   │ Chart (reused Chart.tsx)   │ MARKET     │                  │
│ Automate │ [All][Intraday]    │  - timeframe 5m/15m/1h/1d  │ PANEL      │                  │
│ Portfolio│ [Options][Stocks]  │  - symbol synced from      │  Summary   │                  │
│ Settings │ [Swing][ETF]       │    watchlist single-click  │  Gainers   │                  │
│          │ ┌────────────────┐ │  - quick switch input      │  Losers    │                  │
│          │ │ SYMBOL LTP  %  │ │                            │  VIX       │                  │
│          │ │ OI  VOL  TREND │ │  Analyzer panel slides     │  PCR/OI    │                  │
│          │ │ [B][S][C][A][★]│ │  over chart (right side)   │  ATM       │                  │
│          │ │ ... virtualized│ │                            │  S/R       │                  │
│          │ └────────────────┘ │                            │  AI Summary│                  │
│          │ + Add | Alerts     │                            │            │                  │
│          │                    │                            │            │                  │
│          ├────────────────────┼────────────────────────────┤            │                  │
│          │ Quick Market Panel │                            │            │                  │
│          │ (collapsed on      │  Bottom strip: last order  │            │                  │
│          │  small screens)    │  status / toast feed       │            │                  │
└──────────┴────────────────────┴────────────────────────────┴────────────┴──────────────────┘
```

## Column specs
- **Sidebar (56px)**: 6 icon nav entries. Home→`/portfolio`, Trade→`/workspace`, Analyze→opens analyzer panel on `/workspace?analyze=symbol`, Automate→`/strategies`, Portfolio→`/portfolio`, Settings→`/settings`.
- **Top bar**: market feed status (reused `t-dot` pattern), broker token status (reused `useBrokerCredentials`), global symbol search (reused `/market/instruments` search pattern from app-layout ⌘K), notifications (reuses existing bell w/ alerts count).
- **Watchlist**: tabbed groups stored in localStorage (`tm_watchlist_groups`). Rows: symbol, name, LTP, Δ%, OI, volume, trend arrow (from change_pct), sparkline (mini SVG), actions: BUY / SELL (→ Quick Order Drawer), chart (single-click row), analyzer, pin/favorite (localStorage). Windowed virtualization (~28 visible rows). Price alerts reuse `api.alerts`.
- **Center**: reused `Chart.tsx` (`symbol` prop = active symbol state). Single-click row = chart sync. Search/quick-switch input above chart.
- **Right panel**: market summary (index cards from ticks), top gainers/losers (sorted ticks), India VIX, PCR + OI + ATM (reused `api.marketdata.optionChain`), support/resistance (swing highs/lows from `historical`), AI summary (indicator-based text, no external AI).
- **Analyzer**: side panel, NOT a route. Overlays the center column. Indicators computed client-side from `historical` candles: VWAP, EMA20/50, RSI14, MACD(12,26,9), ADX14, OI/PCR, S/R, trend/SMC labels, AI summary. Buttons: Trade (opens drawer), Backtest (`/backtest`), Strategy (`/strategies/builder`). Lazy-loaded via `next/dynamic`.
- **Drawer**: existing component; adds collapsible **Advanced** (collapsed by default): SL, Target, Trailing SL, Risk %, Capital %, Expected RR, Estimated Margin (placeholder). Inputs project risk/RR client-side; execution payload unchanged (backend auto-bracket unchanged).

## Breakpoints
- ≥1400px: 240px / flex / 260px columns.
- <1400px: right panel collapses to a toggle drawer.
- <900px: watchlist becomes a bottom sheet; chart full width.
