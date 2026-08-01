# IMPLEMENTATION_PLAN.md

Execution order with regression gates. Each phase is independently shippable to prod.
Production stability first — every phase is additive, never a rewrite.

## Phase 1 — Trade Terminal UX (Quick Order Drawer)
1. Append `t-drawer-*` CSS to `styles/components.css` (overlay, slide-in panel,
   header/body/footer, responsive full-screen ≤640px). No existing class modified.
2. Add `quickOrder` state to `lib/stores/ui-store.ts` (open, symbol, defaults, side).
3. Build `components/quick-order-drawer.tsx`:
   - Reads tick from market-store; subscribes on open.
   - BUY/SELL toggle, qty stepper (LOT_SIZES), product/order-type/limit fields.
   - Protection preview (SL −10% / target +15% — matches OMS auto-bracket).
   - Margin preview via `api.marginEstimate` (leg form) + charges estimate line.
   - PAPER/LIVE chip toggle (default PAPER). Confirm → `useExecuteTrade` (E mutation)
     → success toast → auto-close → orders/positions invalidated.
   - Error state inline (never silently close).
4. Mount `<QuickOrderDrawer />` once in `app/layout.tsx` (global, any page can open).
5. Wire `app/marketdata/page.tsx` watchlist rows: row click + BUY/SELL quick actions
   call `useUIStore.openQuickOrder(symbol, side?)`.
6. **Regression:** tsc, build, deploy web container, verify drawer on prod with paper
   trade, verify watchlist/portal pages unaffected.

## Phase 2 — Watchlist V2
1. `components/watchlist/` hub: multi-list tabs (Intraday/Options/Stocks/Swing/ETF +
   custom), localStorage per list, server seed merge.
2. Row component: LTP/%-volume/OI/trend sparkline (tick store), quick actions
   (BUY/SELL → drawer; Chart → /terminal chart; Analyzer/Chain/Strategy/Backtest/Alert).
3. Drag-drop reorder + pin. Search/filter.
4. Replace `/marketdata` page body with hub (page route stays).
5. Regression as Phase 1.

## Phase 3 — Market Analyzer
1. `app/analyzer/` — tabbed analysis page: Chart (E chart.tsx multi-timeframe),
   Indicators (EMA/VWAP/MACD/RSI/ADX/Volume overlays), S/R, OI/PCR/Max Pain (E chain),
   Structure/Order Blocks/Liquidity/FVG/SMC (drawn overlays), AI Summary (E /ai).
2. Global action bar: Trade → drawer, Backtest, Strategy Builder, Watchlist, Portfolio.
3. Route stays inside portal-accessible tree; analyzer.trademetrix.tech is retired as a
   separate surface (not maintained; no duplicate logic).
4. Regression.

## Phase 4 — Strategy Builder V2
1. Beginner Mode: template gallery (E api.builder.templates) + NL preview
   (E api.builder.preview) + one-click save/compile.
2. Advanced Mode = existing block canvas, untouched, surfaced via mode toggle.
3. Regression.

## Phase 5 — Backtest V2
1. Report panel (Net/Gross, Sharpe, Sortino, PF, Max DD, Monthly Returns) — data from
   existing run response; client-side math where absent.
2. Trade list + Equity Curve (E equity-curve.tsx) + CSV export (E downloadCSV pattern).
3. Regression.

## Phase 6 — User Dashboard (portal Overview V2)
1. Widget grid composing existing hooks (portfolio, PnL, orders, positions, strategies,
   broker status, watchlist, market summary, recent trades, notifications).
2. Keep existing portal tabs; Overview becomes widgetized.
3. Regression.

## Phase 7 — Performance
1. React-query tuning, memoized rows, virtualized tables, lazy sections, skeleton reuse.
2. Regression + load check.

## Definition of Done (each phase)
- tsc + build clean · deployed to prod web container · live-verified on
  https://ai.trademetrix.tech (user flow via paper) · RBAC intact (portal/dashboard
  separation) · CHANGELOG.md entry · docs updated.
