# RESKIN MAP — Trade Metrix Terminal Visual Redesign

## 1. Route Inventory

| Route | Description | Priority |
|-------|-------------|----------|
| `/` (page.tsx) | Landing/index | 4 |
| `/auth` | Login/OTP portal | 2 |
| `/terminal` | Live terminal w/ order ticket, positions, orders | 1 |
| `/terminal/builder` | Multi-leg strategy builder | 1 |
| `/terminal/option-chain` | Option chain viewer | 1 |
| `/positions` | Positions list | 1 |
| `/strategies` | Strategy list | 1 |
| `/strategies/[key]` | Strategy detail | 1 |
| `/strategies/builder` | Strategy builder (single-leg) | 1 |
| `/strategies/catalog` | Strategy marketplace | 3 |
| `/strategies/multi-leg` | Multi-leg strategies | 1 |
| `/backtest` | Backtest engine | 3 |
| `/analytics` | Analytics dashboard | 3 |
| `/dashboard` | Trading dashboard w/ broker filter, equity curve | 1 |
| `/settings` | User settings | 3 |
| `/brokers` | Broker management | 2 |
| `/risk` | Risk settings | 3 |
| `/account` | Account page | 3 |
| `/admin` + sub-routes | Admin panel | 4 |
| `/portal` | User portal | 2 |
| `/marketdata` | Market data viewer | 3 |
| `/marketplace` | Strategy marketplace | 3 |
| `/alerts` | Alerts | 3 |
| `/trade` | Trade page | 3 |
| `/onboarding` | User onboarding | 2 |
| `/copilot` | AI copilot | 3 |
| `/journal` | Trading journal | 3 |
| `/feedback` | Feedback | 4 |
| `/transparency` | Transparency report | 4 |
| `/status` | System status | 4 |
| `/ai` | AI features | 4 |
| `/legal/*` | Legal pages (terms, privacy, etc.) | 4 |

## 2. Styling System

| Property | Current Value | Mockup Target |
|----------|---------------|---------------|
| Method | Flat CSS (no Tailwind, no CSS-in-JS) | Same |
| Global styles | `app/globals.css` (imports 3 files) | Same |
| Tokens | `styles/tokens.css` — `:root` with 70+ vars | Override with mockup values |
| Components | `styles/components.css` — `.t-*` classes (920 lines) | Restyle to mockup visual language |
| Terminal | `styles/terminal.css` — new terminal v3 styles | Already has mockup recipes |
| Font loading | `next/font/google` — Outfit (--font-display) + DM Sans (--font-body) | Already correct |
| No-italics | `* { font-style: normal !important }` in globals.css | Already correct |
| Light theme | `[data-theme="light"]` block in tokens.css | Out of scope (keep as-is) |

## 3. Component Inventory

### Shared UI Primitives (in `styles/components.css`)

| CSS Class | Element | Reskin Action |
|-----------|---------|---------------|
| `.t-layout` | App shell flex container | Keep, update tokens |
| `.t-header` + children | Top navigation bar | Restyle to mockup header |
| `.t-sidebar` + children | Left sidebar nav | Restyle to mockup `.rail` |
| `.t-content` | Main content area | Keep, update tokens |
| `.t-statusbar` | Bottom status bar | Keep, update tokens |
| `.t-ticker` | Market index ticker | Keep, update tokens |
| `.t-panel` | Generic card/panel | Apply `.glass` recipe |
| `.t-btn` variants | Button system | Restyle to mockup button look |
| `.t-input` / `.t-select` | Form inputs | Dark glass, cyan focus |
| `.t-table` | Data tables | Mockup table treatment |
| `.t-badge` variants | Status badges | Restyle to `.chip` recipe |
| `.t-dot` variants | Status dots | Restyle to mockup `.dot` with pulse |
| `.t-modal` | Modal dialogs | Apply glass + blur backdrop |
| `.t-toast` | Toast notifications | Apply glass recipe |
| `.t-chip` | Toggle chips | Keep, update tokens |
| `.t-progress` | Progress bars | Keep, update tokens |
| `.t-tabs` / `.t-tab` | Tab navigation | Restyle to mockup tabs |
| `.t-stat` | Stat display | Restyle to `.stat` recipe |
| `.t-order-ticket` | Order ticket panel | Restyle to mockup glass |
| `.t-chart-box` / `.t-chart-btn` | Chart container/controls | Restyle to mockup chart |
| `.t-kill` | Kill switch button | Keep, update tokens |
| `.t-builder-*` | Strategy builder layout | Keep, update tokens |

### Page Components (`components/`)

| Component | Purpose | Reskin Action |
|-----------|---------|---------------|
| `app-layout.tsx` | Shell: sidebar + header + content | Restyle to use mockup tokens |
| `clarity.tsx` | Microsoft Clarity analytics | No change |
| `feedback-wrapper.tsx` | Feedback button | No change |

### Terminal Components (`components/terminal/`)

These were created in a prior session for the v3 redesign. Since the reskin task forbids building new panels or changing logic, these should NOT be referenced by the reskin. The existing `app/terminal/page.tsx` has its own inline UI that will receive the token-level reskin.

## 4. Chart Library

| Property | Value |
|----------|-------|
| Library | `lightweight-charts` v5.2.0 |
| Usage | Imported in multiple page components |
| Reskin | Recolor via config: up=#34d399, down=#f87171, accent=#8b5cf6, grid=rgba(255,255,255,.05), font=Outfit |

## 5. Reskin Map Table

| Route/Area | Mockup Recipe | Files to Touch | Type |
|------------|---------------|----------------|------|
| **Global tokens** | `:root` colors, fonts, radii | `styles/tokens.css` | CSS |
| **Global no-italics** | Already applied | — | — |
| **Ambient background** | `.ambient` + `.gridlines` | `app/globals.css` | CSS added |
| **App shell (sidebar + header)** | `.rail` nav + mockup header | `components/app-layout.tsx` | Presentational JSX + className |
| **Header/top bar** | Mockup `<header>` sticky treatment | `components/app-layout.tsx` | className changes |
| **Sidebar/nav** | `.rail-item` rounded, active glow | `components/app-layout.tsx` | className changes |
| **All `.t-btn`** | Glass button with violet accent | `styles/components.css` | CSS |
| **All `.t-input`** | Dark glass, cyan focus ring | `styles/components.css` | CSS |
| **All `.t-panel`** | `.glass` recipe | `styles/components.css` | CSS |
| **All `.t-table`** | Mockup table (uppercase headers, hover rows) | `styles/components.css` | CSS |
| **All `.t-badge`** | `.chip` / `.status` recipe | `styles/components.css` | CSS |
| **All `.t-modal`** | Glass + blur backdrop | `styles/components.css` | CSS |
| **All `.t-toast`** | Glass recipe | `styles/components.css` | CSS |
| **PAPER/LIVE toggle** | `.mode-switch` styling | `styles/components.css` | CSS class added |
| **Charts** | Recolor via config | Page files that create chart instances | Config object changes only |
| **Terminal page** | Token-level reskin only | `app/terminal/page.tsx` | className changes |
| **Terminal builder** | Token-level reskin only | `app/terminal/builder/page.tsx` | className changes |
| **Terminal option-chain** | Token-level reskin only | `app/terminal/option-chain/` | className changes |
| **Positions page** | Token-level reskin | `app/positions/page.tsx` | className changes |
| **Strategies pages** | Token-level reskin | `app/strategies/*` | className changes |
| **Dashboard** | Token-level reskin | `app/dashboard/page.tsx` | className changes |
| **Auth/OTP** | Dark glass form, cyan focus | `app/auth/page.tsx` | className changes |
| **Brokers page** | Token-level reskin | `app/brokers/page.tsx` | className changes |
| **Onboarding** | Token-level reskin | `app/onboarding/page.tsx` | className changes |
| **Portal** | Token-level reskin | `app/portal/page.tsx` | className changes |
| **Analytics** | Token-level reskin | `app/analytics/page.tsx` | className changes |
| **Backtest** | Token-level reskin | `app/backtest/page.tsx` | className changes |
| **Settings** | Token-level reskin | `app/settings/page.tsx` | className changes |
| **Risk** | Token-level reskin | `app/risk/page.tsx` | className changes |
| **Account** | Token-level reskin | `app/account/page.tsx` | className changes |
| **Admin** | Token-level reskin | `app/admin/*` | className changes |
| **Scrollbars** | Thin violet-tinted | `styles/tokens.css` | CSS |

## 6. CSS Change Plan

### Phase A — Foundation (no .tsx files)
1. Update `styles/tokens.css` — mockup `:root` values
2. Add ambient background to `app/globals.css`
3. Update `styles/components.css` — restyle `.t-*` classes to mockup visual language
4. Add `:focus-visible` cyan outline globally

### Phase B — Layout Reskin (app-layout.tsx only)
5. Update `components/app-layout.tsx` — apply mockup className patterns to sidebar, header

### Phase C — Page Reskin (className changes in all route files)
6. Apply new class names / update existing class references in each route page

## 7. Branch Strategy

Branch name: `reskin/terminal-v3`
Squash strategy: Single commit so `git revert` restores old look completely

## 8. COMPROMISES (anticipated)

- If the app's number formatting differs from `Intl.NumberFormat('en-IN')`, we cannot change it (forbidden). Note and move on.
- `lightweight-charts` recoloring via config may not support all mockup chart visual details.
- The mockup's `--font-display: Outfit` is already applied; verify all headings/numbers use it.
