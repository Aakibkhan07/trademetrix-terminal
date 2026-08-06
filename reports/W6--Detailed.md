# W6 — Detailed Work Report (Sprint 3, Week 6)

**Repo:** monorepo root `/Users/aakib/trademetrix-terminal` · **Frontend:** `apps/web`
**Branch:** `main` (web-only commit for deploy; api working tree untouched)
**Date:** 2026-08-06

## 1. Shared primitives authored (all in `apps/web/components/ui/`)

| Primitive | File | API | Consumers |
|---|---|---|---|
| `KpiCard` | `ui/kpi-card.tsx` | `label, value, sub?, prefix?, color?, variant?` | `/backtest`, `/admin/beta`, `/strategies/[key]`, `/dashboard/pnl-dashboard-tab` |
| `PageLoadingSkeleton` / `SkeletonBar` | `ui/skeleton.tsx` (+ `components/skeleton.tsx` shim) | `w,h,background,style` | 3 app-level + 5 page-level loading UI |
| `Badge`, `Dot`, `Chip`, `OrderStatusBadge`, `InstrumentTypeBadge`, `TierBadge` | `ui/badge.tsx` (via `BadgeVariant`) | token-backed colors | `/dashboard/admin-content`, `/strategies/[key]`, `/strategies/catalog`, `/strategies/builder`, `/marketdata`, `/workspace/watchlist-panel` |
| `Dialog` | `ui/dialog.tsx` | `open, onClose, title, children, stayOpenOnOverlay?` | `/settings`, `/account`, `/brokers`, `/strategies`, `/marketdata`, `/workspace/alert-modal`, `/workspace/.../deploy-wizard` |

Also reused/kept (existing primitives): `empty-state.tsx` (`EmptyState`/`TableEmptyRow`/`EmptyPanel`), `sparkline.tsx` (`Sparkline`), `chart-shell.tsx` (`chartOptions()`, `colorVar()`, `mix()`), `chart-tooltip.tsx`, `drawer.tsx`, `form.tsx`, `data-table.tsx`, `toast.tsx`, `loading.tsx`.

## 2. Per-file change log (web)

| File | Change |
|---|---|
| `app/backtest/page.tsx` | Deleted duplicate inline `kpiCard`/`tiCard` internals; delegating wrappers → `KpiCard`. Removed dead helpers `colorVar_`/`fmtMoney2`. |
| `app/admin/beta/page.tsx` | `UIKpiCard`/`SkeletonPanel` → `KpiCard` + `PageLoadingSkeleton`; `EmptyPanel` reused. |
| `app/strategies/[key]/page.tsx` | Inline `MetricCard` → `KpiCard`; `category`/`catLabel` derived labels. |
| `app/dashboard/pnl-dashboard-tab.tsx` | `StatCard` → `KpiCard` (adds `prefix`, numeric `value`). |
| `app/dashboard/admin-content.tsx` | Order/tier statuses → shared `OrderStatusBadge`/`TierBadge`; local skeleton → `SkeletonBar`. |
| `app/admin/admins`, `app/admin/broadcast`, `app/strategies/catalog` | local skeleton fragments → `SkeletonBar`. |
| `app/{dashboard,terminal,portal}/loading.tsx` | Duplicated loading markup → `PageLoadingSkeleton`. |
| `app/settings`, `app/account`, `app/brokers`, `app/strategies`, `app/marketdata` | Inline `t-modal`+backdrop → `Dialog` component (close-on-overlay preserved). |
| `app/terminal/builder`, `components/workspace/{alert-modal,watchlist-panel}` | Legacy modal → `Dialog`. |
| `app/analytics` + `components/{chart,mini-chart}` | Equity mini-chart path maintained via `Sparkline` (existing). |
| `components/empty-state.tsx`, `components/skeleton.tsx` | Re-export shims for legacy import sites. |
| `next.config.js` | untouched (webpack security already in place). |

## 3. Duplicates removed / normalized

- KPI card markup: 4 inline definitions → 1 shared (`KpiCard`).
- Skeleton markup: 8+ inline fragments → 1 (`SkeletonBar` / `PageLoadingSkeleton`).
- Modal/dialog wrapper: 7 inline `t-modal` instances → 1 (`Dialog`).
- Status badge color utilities: inline color constructions → design-token badges.

## 4. Encoding / zoom notes

- Uses light/dark design tokens via CSS variables only; no hardcoded hex introduced (values map to `--text-*`, `--amber`, `#8b5cf6` token set) for theme parity.