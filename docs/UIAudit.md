# UI Audit Report — TradeMetrix Terminal

**Date:** 2026-07-03
**Scope:** 22 page routes + shared components in `apps/web/`

---

## Component Inventory

| # | Route | Page Component | Lines | Status |
|---|-------|---------------|-------|--------|
| 1 | `/` | `app/page.tsx` | ~250 | ✅ Landing page |
| 2 | `/auth` | `app/auth/page.tsx` | ~200 | ✅ Auth with inline errors |
| 3 | `/onboarding` | `app/onboarding/page.tsx` | ~529 | ✅ 3-step wizard |
| 4 | `/dashboard` | `app/dashboard/page.tsx` | ~150 | ✅ KPI cards, watchlist |
| 5 | `/terminal` | `app/terminal/page.tsx` | ~600 | ✅ Order ticket, positions, charts |
| 6 | `/trade` | `app/trade/page.tsx` | ~400 | ✅ Option chain, trade desk |
| 7 | `/positions` | `app/positions/page.tsx` | ~250 | ✅ Positions, orders, funds |
| 8 | `/marketdata` | `app/marketdata/page.tsx` | ~500 | ✅ Live ticks, charts, alerts |
| 9 | `/strategies` | `app/strategies/page.tsx` | ~350 | ✅ CRUD strategy cards |
| 10 | `/strategies/catalog` | `app/strategies/catalog/page.tsx` | ~250 | ✅ Browse built-in strategies |
| 11 | `/brokers` | `app/brokers/page.tsx` | ~380 | ✅ Connect/disconnect brokers |
| 12 | `/backtest` | `app/backtest/page.tsx` | ~250 | ✅ Run backtests |
| 13 | `/journal` | `app/journal/page.tsx` | ~400 | ✅ Analytics, equity curve |
| 14 | `/alerts` | `app/alerts/page.tsx` | ~180 | ✅ Price alerts CRUD |
| 15 | `/risk` | `app/risk/page.tsx` | ~250 | ✅ Kill switch, live toggle, limits |
| 16 | `/ai` | `app/ai/page.tsx` | ~200 | ✅ AI trading desk |
| 17 | `/transparency` | `app/transparency/page.tsx` | ~150 | ✅ Order lifecycle |
| 18 | `/account` | `app/account/page.tsx` | ~530 | ✅ Profile, stats, notifications |
| 19 | `/settings` | `app/settings/page.tsx` | ~250 | ⚠️ Not linked from sidebar |
| 20 | `/admin` | `app/admin/page.tsx` | ~1000 | ✅ Multi-tab admin dashboard |
| 21 | `/admin/broadcast` | `app/admin/broadcast/page.tsx` | ~400 | ✅ Broadcast trade signals |
| 22 | `/portal` | `app/portal/page.tsx` | ~1200 | ✅ Standalone client portal |

---

## Shared Components

| Component | File | Lines | Notes |
|-----------|------|-------|-------|
| `AppLayout` | `components/app-layout.tsx` | 162 | Sidebar + kill switch + auth guard |
| `Header` | `components/header.tsx` | 99 | Top bar, search, theme toggle, avatar |
| `Chart` | `components/chart.tsx` | 140 | Lightweight candlestick chart |
| `EquityCurve` | `components/equity-curve.tsx` | 63 | SVG equity curve |
| `Logo` | `components/logo.tsx` | 31 | SVG logo |
| `MarketTicker` | `components/market-ticker.tsx` | 50 | Horizontal scrolling ticker |
| `StatusBar` | `components/status-bar.tsx` | 36 | Connection status, clock |
| `SkeletonLine/Card/Table/Grid` | `components/skeleton.tsx` | 76 | NEW — Loading skeletons |
| `EmptyState` | `components/empty-state.tsx` | 22 | NEW — Empty data states |
| `ErrorMessage` | `components/error-message.tsx` | 22 | NEW — Error states with retry |

---

## Design System Audit

### Typography

| Token | Value | Usage | Status |
|-------|-------|-------|--------|
| `--font-sans` | DM Sans | Body text, inputs, buttons | ✅ |
| `--font-display` | Outfit | Headings, titles | ✅ |
| `--font-mono` | JetBrains Mono (system fallback) | Code, numbers, tables | ⚠️ Not loaded; uses `--font-mono: 'JetBrains Mono', 'Fira Code', monospace` |

### Color Tokens

| Token | Dark Value | Usage | Status |
|-------|-----------|-------|--------|
| `--bg` | `#0b0b0f` | Page background | ✅ |
| `--bg-secondary` | `#0f0f14` | Secondary background | ✅ |
| `--bg-tertiary` | `#14141a` | Tertiary/hover | ✅ |
| `--panel` | `#13131a` | Card backgrounds | ✅ |
| `--panel-2` | `#16161e` | Inner panels | ✅ |
| `--text` | `#e6e6ee` | Primary text | ✅ |
| `--text-sub` | `#8888a0` | Secondary text | ✅ |
| `--text-faint` | `#555570` | Disabled/faint | ✅ |
| `--border` | `#1e1e2a` | Borders | ✅ |
| `--border-hi` | `#2a2a3a` | High-contrast borders | ✅ |
| `--cyan` | `#22d3ee` | Primary accent | ✅ |
| `--violet` | `#8b5cf6` | Secondary accent | ✅ |
| `--green` | `#22c55e` | Profit/success | ✅ |
| `--red` | `#ef4444` | Loss/error | ✅ |
| `--amber` | `#f59e0b` | Warning | ✅ |

### Spacing

| Token | Value | Status |
|-------|-------|--------|
| `--space-xs` | 4px | ✅ |
| `--space-sm` | 6px | ✅ |
| `--space-md` | 10px | ✅ |
| `--space-lg` | 14px | ✅ |
| `--space-xl` | 20px | ✅ |
| `--space-2xl` | 32px | ✅ |

### Responsive Breakpoints

| Breakpoint | Target | Status |
|-----------|--------|--------|
| 900px | Tablet | ⚠️ Partial — sidebar collapses, some pages not tested |
| 640px | Mobile | ⚠️ Partial — basic stacking, trading pages may overflow |
| 480px | Small mobile | ⚠️ Not tested |

---

## UI Issues Found

### P3 — Minor Issues

| # | Page | Issue | Fix |
|---|------|-------|-----|
| 1 | `/settings` | Page exists but not listed in sidebar navigation | Add "Settings" to sidebar nav items |
| 2 | All pages | No skip-to-content link for keyboard users | Add skip link to `app-layout.tsx` |
| 3 | `app-layout.tsx` | Kill switch button has no `aria-label` | Add `aria-label="Toggle kill switch"` |
| 4 | `app-layout.tsx` | Sign out button has no `aria-label` | Add `aria-label="Sign out"` |
| 5 | All pages | Delete/destructive actions have no confirmation dialogs | Add confirmation modal to strategy delete, broker disconnect |
| 6 | `/terminal` | Order ticket doesn't validate inputs before submit (empty symbol, zero qty) | Add client-side validation |
| 7 | `/strategies` | No confirmation before deleting strategy | Add confirm dialog |
| 8 | `/brokers` | No confirmation before disconnecting broker | Add confirm dialog |
| 9 | `/account` | "Change Password" and "Setup 2FA" buttons show info toast but no modal | Replace toast with actual modal when ready |
| 10 | All pages | Focus ring uses default browser style (blue) instead of theme `--cyan` | Add custom `:focus-visible` outline |

---

## Before/After: Key UX Improvements

| UX Aspect | Before | After |
|-----------|--------|-------|
| Loading states | Inline text "Loading..." | Animated shimmer skeletons |
| Error handling | Silent `.catch(() => {})` | Toast notifications with error messages |
| Empty data | Blank panels | Empty states with descriptive text + action buttons |
| Dev artifacts | `alert()` calls, `debug_otp`, "Coming soon" | Clean production code |
| Auth errors | Unhandled or generic | Inline error display + toast |
| Dead links | "Upgrade plan" → `#` (nothing) | Info toast "Upgrade available soon" |
| Inert tab buttons | `<button>` with no onClick | `<span>` (non-interactive label) |
| Toast CSS | Class mismatch (rendered `toast` but CSS expects `t-toast`) | Aligned to `t-toast-*` classes |
