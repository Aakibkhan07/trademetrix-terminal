# W6 — UI Refactor Summary

**Theme:** consolidate duplicated UI surface across the web app into `apps/web/components/ui/` with **pixel-identical output**.

## 1. Shared UI inventory (`apps/web/components/ui/`)

| Component | Purpose | Consumers |
|---|---|---|
| `KpiCard` | stat/metric/beta key-value cards | backtest, admin/beta, strategies/[key], dashboard pnl tab |
| `Badge` / `Dot` / `Chip` | generic status pills + indicator dots | sidebar, admin panels |
| `OrderStatusBadge` | filled/cancelled/rejected/partial pills | dashboard/watchlist, strategy builder |
| `InstrumentTypeBadge` | Equity/Index/Futures/Options/Crypto | watchlist, catalog, strategy builder |
| `TierBadge` | tier + poor-man legend chips | admin-content, catalog |
| `SkeletonBar` / `PageLoadingSkeleton` | shimmer bars + page loading screens | 3 app loading.tsx + 5 page panels |
| `EmptyState` / `TableEmptyRow` / `EmptyPanel` | empty rows/screens | marketdata, admin, watchlist |
| `Sparkline` | tiny series chart | mini charts |
| `Dialog` | unified modal (backdrop, close, focus) | settings, account, brokers, strategies, marketdata, alert-modal, deploy-wizard |
| `Drawer` / `DataTable` / `Form` / `Toast` / `Loading` / `ChartShell` + `ChartTooltip` | existing retained primitives | across app |

## 2. Consolidation wins

- **Dialogs:** 7 inline `t-modal`+backdrop implementations → 1 `Dialog` (settings change-password, account, brokers connect, strategies create, marketdata add-symbol + alert, terminal/builder, watchlist alert-modal).
- **KPI cards:** 4 inline card definitions → 1 `KpiCard` (net P&L / return / win-rate / Sharpe… in backtest, metrics in strategies/[key], admin/beta stats, dashboard StatCards).
- **Skeletons:** 8+ ad-hoc shimmer fragments → 1 `SkeletonBar` + 1 page loader.
- **Badge colors:** hardcoded per-instance color strings → single token-backed set (`var(--text-green)`, `var(--text-red)`, `var(--amber)`, plus `#8b5cf6`/`#22d3ee`/`#22c55e`/`#f87171`/`#fbbf24` token set via `t-badge`).
- **Re-export shims** `components/skeleton.tsx` & `components/empty-state.tsx` keep old import paths working without page churn.

## 3. Constraint compliance

- Only files under `apps/web/` changed; no `apps/api`, no routes, no middleware semantics, no DB/state, no config changes.
- No CSS files, no theme tokens, no Tailwind config altered — appearance preserved.
- RGB-equivalent tokens used; verified visually via HTML-diff equivalence (see `W6-Visual-Verification.md`).

## 4. Next — STOP

Sprint 3 (W6) UI consolidation complete. Deploy + verification done in associated reports. **No Sprint 4.**