# Sprint 3 — Component Consolidation (W6) — Final Report

**Repo:** `/Users/aakib/trademetrix-terminal` (monorepo: `apps/web` Next.js frontend)
**Sprint:** 3 / Consolidation · Week 6
**Date:** 2026-08-06
**Scope:** UI-only internal reuse. No API, backend, routing, or state changes. No visual redesign. Pages render identically; duplicates are replaced with shared primitives.

---

## 1. Objective

Consolidate duplicated inline UI markup (KPI cards, status badges, empties, skeletons, dialogs, and related primitives) into a single shared folder `apps/web/components/ui/`, with zero behavioral or visual change, then validate, deploy, verify in production, and stop.

## 2. What shipped

New shared primitives in `apps/web/components/ui/`:

- `kpi-card.tsx` — `KpiCard` (variants: `stat`/`metric`/`beta`), used by `/backtest`, `/admin/beta`, `/strategies/[key]`, `/dashboard` (pnl tab).
- `badge.tsx` — `Badge`, `Dot`, `Chip`, `OrderStatusBadge`, `InstrumentTypeBadge`, `TierBadge` via `BadgeVariant`; colors delegated to design tokens (`t-badge`/`t-dot`/`t-chip`).
- `skeleton.tsx` — `SkeletonBar` (`w`/`h`/`background`/`style`) + `PageLoading`; re-exported from `apps/web/components/skeleton.tsx`.
- `dialog.tsx` — `Dialog` (single source replacing legacy `t-modal` wrappers).
- Legacy re-export shims in `components/`: `empty-state.tsx`, `skeleton.tsx`.

Existing primitives retained/centralized: `sparkline.tsx`, `empty-state.tsx`, `chart-shell.tsx`, `chart-tooltip.tsx`, `drawer.tsx`, `form.tsx`, `data-table.tsx`, `toast.tsx`, `loading.tsx`.

Refactored pages (all delegates to `components/ui/`):

- `/backtest`, `/strategies/[key]`, `/admin/beta`, `/admin/admins`, `/admin/broadcast`, `/dashboard` (admin-content + pnl tab + loading), `/settings`, `/account`, `/brokers`, `/strategies`, `/strategies/catalog`, `/strategies/builder`, `/marketdata` (two dialogs), `/trade`, `/terminal/builder`, `/terminal/loading`, `/portal/loading`, `/analytics`.

## 3. Non-goals respected (zero-touch verification)

- **No API changes:** `apps/api` untouched this sprint (11 Sprint-2 files remain uncommitted working-tree only; not part of this deploy).
- **No routing changes:** route table identical (verified against pre-change build).
- **No state/behavior changes:** dialog close actions behave equivalently; badge/pill markup and CSS-variable token values preserved 1:1 (see Visual Verification report).
- **No dependency additions:** no new libraries; only Node built-ins / existing React usage.

## 4. Validation gates (see `W6-Validation.md` for detail)

| Gate | Command | Result |
|---|---|---|
| TypeScript | `npx tsc --noEmit` | pass, 0 errors |
| Lint | `npm run lint` | 0 errors (1 pre-existing warning in `deploy-wizard.tsx`) |
| Build | `npm run build` | pass, all routes emitted |
| API regression | `pytest tests/ -q` (`apps/api`) | 955 passed, 1 xfailed (baseline parity) |
| Visual parity | SSR HTML diff of 12 prod routes + component-level markup equivalence | see `W6-Visual-Verification.md` |

## 5. Outcomes

- Duplicate inline helpers removed at their old sites (verified absent via grep: `colorVar_`, `fmtMoney2`, duplicated `tiCard`/`kpiCard` defs in `/backtest`).
- Single source of truth for badges/skeletons/dialogs; 9+ inline dialog overrides collapsed to `Dialog`.
- Route bundle decreases measurable on pages that stopped bundling local copies (e.g. `/admin/admins` 91.8 kB, `/strategies/catalog` 91.6 kB first-load).

## 6. Deployment

Executed per `infra/deploy-prod.sh` (web-only commit → push `origin/main` → VPS `git reset --hard origin/main` → docker compose build/up). See `docs/DEPLOY.md`. Post-deploy verification in `W6-Visual-Verification.md`.

## 7. STOP declaration

Sprint 3 (W6) is complete. Work halts here; **Sprint 4 is not started** by instruction. Any further breakdown is out of scope.