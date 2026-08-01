# WIREFRAMES.md

ASCII wireframes for the new surfaces. Styling follows existing design system
(tokens.css + components.css classes).

## Phase 1 — Quick Order Drawer (right slide-in, 360px desktop / full-screen mobile)

```
┌─────────────────────────────────────────────┐
│ App (watchlist, chain, portal — any page)   │
│                                    ┌────────┴──────────────┐
│                                    │ QUICK ORDER   [×]     │
│                                    ├───────────────────────┤
│                                    │ NSE:NIFTY26AUG24450CE │
│                                    │ NIFTY 24450 CE        │
│                                    │ LTP 270.98  ▲ +2.4%   │
│                                    │ Bid 270.6 Ask 271.3   │
│                                    ├───────────────────────┤
│                                    │ [ BUY ]  [ SELL ]     │
│                                    │ Qty    [−] 65 [+1 lot]│
│                                    │ Product  INTRADAY ▾   │
│                                    │ Type     MARKET   ▾   │
│                                    │ Limit Price  (LIMIT)  │
│                                    ├───────────────────────┤
│                                    │ Auto-protection:      │
│                                    │  SL 243.88 / Tgt 311.63│
│                                    │ Margin ≈ ₹17,613      │
│                                    │ Charges ≈ ₹48 (est)   │
│                                    ├───────────────────────┤
│                                    │ [PAPER] [LIVE]        │
│                                    │ [ CONFIRM BUY ]       │
│                                    └───────────────────────┘
```

## Phase 2 — Watchlist Hub (app/marketdata)

```
┌───────────────────────────────────────────────────────┐
│ Watchlist   [Intraday|Options|Stocks|Swing|ETF|+]  🔍 │
├───────────────────────────────────────────────────────┤
│ SYMBOL   LTP      %      VOL    OI    TREND  ACTIONS  │
│ NIFTY   24455  +0.8%   1.2M    —     ▁▃▅   [B][S][⚲]… │
│ 24450CE  271   +2.4%   85K   12.4M  ▁▃▆   [B][S][⚲]… │
│ RELIANCE 2950  -0.3%   3.1M    —     ▅▃▁   [B][S][⚲]… │
└───────────────────────────────────────────────────────┘
 Actions: B=Buy  S=Sell  ⚲=more (Chart/Analyzer/Chain/Strategy/Backtest/Alert)
 Row click → Quick Order Drawer (Phase 1)
 Drag ⇅ to reorder · pin ⭐ · filter by name
```

## Phase 3 — Analyzer (single screen, action bar fixed bottom of chart)

```
┌ Chart (lightweight-charts) ─────────────┬ Indicators ▾ │
│  EMA 20/50  VWAP  MACD  RSI  ADX  VOL   │ timeframe 5m │
├──────────────────────────────────────────┤ SR / OI/PCR │
│ Market Structure / Order Blocks / FVG    │ Max Pain /  │
│ (overlay toggles)                        │ Chain ▾     │
├──────────────────────────────────────────┤ AI Summary  │
│ [Trade] [Backtest] [Strategy] [Watchlist] [Portfolio]   │ ← never leaves screen
└──────────────────────────────────────────────────────────┘
```

## Phase 4 — Strategy Builder modes

```
Beginner: [Template gallery] → [NL preview: "Buy when EMA 20 crosses EMA 50,
           SL 10%, target +15%, time 9:30-14:45"] → [Save & Compile]
Advanced: [existing block canvas — unchanged]
```

## Phase 5 — Backtest report

```
┌ Run summary ───────────────┬ Equity curve (SVG) ─────────┐
│ Net ₹/Gross ₹/PF/Sharpe    │                            │
│ Sortino/MaxDD/Monthly      ├ Trades table + CSV export ─┤
└────────────────────────────┴─────────────────────────────┘
```

## Phase 6 — Portal Overview widget grid

```
┌ Portfolio │ PnL │ Orders │ Positions ┐
│ Strategies│Broker│Watchlist│Summary   │
│ Recent Trades │ Notifications │ Events│
└──────────────────────────────────────┘
```
