# Reskin Report — Terminal v3 Visual Design Language

## Route Checklist

| Route | Status | Notes |
|-------|--------|-------|
| `/` (index) | ✅ Token-level | Uses CSS variables, auto-updated |
| `/auth` | ✅ Updated | Hardcoded colors replaced with CSS vars |
| `/terminal` | ✅ Updated | Inline font refs replaced, all classes restyled |
| `/terminal/builder` | ✅ Token-level | Uses `t-*` classes, auto-updated |
| `/terminal/option-chain` | ✅ Token-level | Uses `t-*` classes, auto-updated |
| `/positions` | ✅ Token-level | Uses `t-*` classes, auto-updated |
| `/strategies` | ✅ Token-level | Uses `t-*` classes, auto-updated |
| `/strategies/[key]` | ✅ Token-level | Uses `t-*` classes, auto-updated |
| `/strategies/builder` | ✅ Token-level | Uses `t-*` classes, auto-updated |
| `/strategies/catalog` | ✅ Token-level | Uses `t-*` classes, auto-updated |
| `/strategies/multi-leg` | ✅ Token-level | Uses `t-*` classes, auto-updated |
| `/backtest` | ✅ Token-level | Uses `t-*` classes, auto-updated |
| `/analytics` | ✅ Token-level | Uses `t-*` classes, auto-updated |
| `/dashboard` | ✅ Token-level | Uses `t-*` classes, auto-updated |
| `/settings` | ✅ Token-level | Uses `t-*` classes, auto-updated |
| `/brokers` | ✅ Token-level | Uses `t-*` classes, auto-updated |
| `/risk` | ✅ Token-level | Uses `t-*` classes, auto-updated |
| `/portal` | ✅ Token-level | Uses `t-*` classes, auto-updated |
| `/admin` + sub-routes | ✅ Token-level | Uses `t-sidebar*` classes, restyled |
| All others | ✅ Token-level | CSS variable changes propagate everywhere |

## Files Touched

```
 apps/web/styles/tokens.css              | 123 ++--
 apps/web/styles/components.css          | 1038 ++++++++++++----------
 apps/web/app/globals.css                |  19 +
 apps/web/app/layout.tsx                 |  24 +-
 apps/web/app/auth/page.tsx              | 124 ++--
 apps/web/app/terminal/page.tsx          |  19 +-
```

## `git diff --stat`

```
 6 files changed, 856 insertions(+), 491 deletions(-)
```

## Changes Summary

### CSS Foundation (no .tsx changes)
1. **`styles/tokens.css`** — Replaced all `:root` design tokens with mockup values:
   - `--bg: #050508` (darker background)
   - `--violet: #8b5cf6`, `--cyan: #22d3ee`, `--green: #34d399`, `--red: #f87171`
   - `--font-sans: 'DM Sans'`, `--font-display: 'Outfit'`
   - `--gradient-primary: linear-gradient(135deg, #8b5cf6, #22d3ee)`
   - Ambient background via `body::before` (violet + cyan radial blobs)
   - Gridlines via `body::after` (44px grid with radial mask)

2. **`styles/components.css`** — Full restyle of all 920+ lines:
   - **Layout**: Mockup shell with responsive max-width 1720px
   - **Header**: Sticky, `rgba(5,5,8,.72)` bg, blur, `t-header-nav` segmented pills
   - **Sidebar**: Mockup rail (196px, panel bg, blur, .active with violet gradient)
   - **Ticker**: Mockup `idx-strip` style with panel bg and rounded items
   - **Panels**: Glass recipe — `linear-gradient(165deg, rgba(255,255,255,.046), rgba(255,255,255,.016))`, blur, border
   - **Buttons**: Glass-base with colored variants, 8px radius
   - **Inputs/Selects**: Dark tertiary bg, cyan focus ring with box-shadow
   - **Tables**: Mockup treatment — uppercase headers (10px), 12.5px td, violet hover, `--sc` accent line on stats
   - **Badges → Chips**: Pill-shaped with colored bg/border (buy=green, sell=red, strat=violet, paper=cyan)
   - **Dots**: 7px with glow and pulse animation
   - **Modals**: Glass + blur backdrop
   - **Toasts**: Glass recipe with bottom-right positioning
   - **Tabs**: Mockup segmented pill style
   - **Stats**: Mockup stat cards with top accent line
   - **Progress**: 4px rounded bars
   - **Charts**: Mockup chart controls with `.tf`-style button group
   - **Order ticket**: Glass panel
   - **Builder**: Grid layout preserved
   - **Animations**: `.rise` entrance (translateY + opacity), staggered delays `.d1`-`.d6`
   - **Mode switch**: `.t-mode-switch` + `.t-mode-btn` PAPER/LIVE toggle
   - **Scrollbar**: Violet-tinted thumb (#3b3850 → #5b5875)
   - All legacy classes (`.page-title`, `.btn`, `.input`, `.panel`, `.glass-card`, `.data-table`, `.live-dot`, etc.) updated

3. **`app/globals.css`** — Added `:focus-visible`, `box-sizing: border-box` reset, and `prefers-reduced-motion` reduce rule. Removed stale `terminal.css` import.

### Presentational JSX Changes
4. **`app/auth/page.tsx`** — Replaced all hardcoded old colors with CSS variable references:
   - `#0f1419` → `var(--bg)`
   - `#00d4ff` / `#0096ff` → `var(--violet)` / `var(--cyan)` / `var(--gradient-primary)`
   - `#a1a5b3` → `var(--text-sub)`, `#5f6368` → `var(--text-faint)`
   - `#ef4444` → `var(--text-red)`, `#22c55e` → `var(--text-green)`
   - `'Inter', sans-serif` → removed
   - Ambient background updated to mockup blobs
   - Auth card → glass recipe
   - Inputs → `--bg-tertiary` with violet focus

5. **`app/terminal/page.tsx`** — Replaced inline `'Inter', sans-serif` with inheritance, added `.t-page-title` class, replaced submit button with `.t-order-submit` class

## Compromises

1. **`app-layout.tsx` inline styles**: The main app shell uses extensive inline styles referencing CSS variables. Token changes propagate colors but full mockup header/rail layout requires more significant JSX changes (out of scope for "className only" constraint).
2. **Toast component**: Uses bare `.toast` CSS classes (not `.t-toast`). Pre-existing — not reskinned.
3. **No ESLint**: Not configured in the project — lint skipped.
4. **No screenshots**: Mockup screenshots directory `docs/reskin-screenshots/` not created (requires running app).
5. **`lightweight-charts`**: Chart instance config not updated — requires functional change to chart creation code (out of scope for reskin).

## Verification
- ✅ `npm run build` — passes
- ✅ `npx tsc --noEmit` — passes (0 errors)
- ⚠️ `npm run lint` — ESLint not configured (skipped)

## Branch
- `reskin/terminal-v3` pushed to origin
- PR: https://github.com/Aakibkhan07/trademetrix-terminal/pull/1
- Single squashed commit: `03a6da3`
- Do not merge — for review only
