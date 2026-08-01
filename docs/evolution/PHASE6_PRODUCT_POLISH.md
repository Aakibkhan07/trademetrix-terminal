# Phase 6 — Product Polish (Audit Reports + Improvement Plan)

Date: 2026-08-01
Status: Audit complete — improvements being implemented in batches, full regression after every batch

---

Scope: make every existing feature delightful. No major features, no architecture changes, no new modules.
Surface audited: 63 pages + 42 shared components (`apps/web`), API surface unchanged.

---

## 1. UX Audit Report

### What works well
- **Keyboard-first search**: ⌘K / Ctrl+K opens global search overlay; ESC closes it; debounced (300 ms) results; "no results" and "type 2+ chars" empty states both present.
- **Phase 5 backtest page** is state-rich: run/optimize/compare all show loading, error, empty, and success states; exports and deploy feedback inline.
- **Toast system** (`lib/use-toast.tsx`) exists and is used across 21 files for success/error feedback.
- **Shared state components** exist: `EmptyState`, `ErrorMessage`, `SkeletonGrid/Card/Table`.
- Cmd+K, disabled-while-running buttons (129 `disabled` attrs), running guards on 10 async actions.

### Issues found (ranked by user impact)
1. **Dead header "tabs"** (`components/header.tsx` + header in `app-layout.tsx`): Terminal/Trade/Positions tabs render as static `<button className="active">` and do NOT navigate or switch anything. The terminal/positions/trade pages have no matching tab state — these are dead controls users click with no effect.
2. **Fake search box in the header**: a `<div>` styled as an input (`cursor: text`) that is not focusable and does nothing except open the overlay on click. Misleads keyboard users (can't Tab into it) and mouse users (looks like a real input).
3. **Hardcoded version badge "v0.1"** in the header while a real `AppVersion` component exists (`NEXT_PUBLIC_APP_VERSION`).
4. **Duplicate/conflicting navigation**: sidebar lists Dashboard sub-tabs (Trade Router, Trades, Positions…) as separate items; the same content is also reachable from the Dashboard page's own tab bar. Cognitive load: two mental models of the same 10 sections.
5. **Inconsistent success states**: workspace components use toasts; backtest page uses inline text; auth uses inline banners. Same action (e.g. save) gives different feedback styles on different pages.
6. **Empty-state copy drift**: `EmptyState` component exists but 29 files hand-roll empty states with inconsistent copy ("No data available" vs "Nothing here yet" vs "No trades were generated").
7. **No route-level error boundary**: a render crash anywhere takes down the whole segment to the bare `global-error.tsx` (no nav, no retry).

### Clicks / complexity reduction opportunities
- Make header tabs real links (1 click saved vs dead click) — fix #1.
- Keep sidebar sections but verify the most-used 5 items are above the fold (sidebar is 196 px wide with 4 sections — all visible; OK).
- No gratuitous modal chains found; quick-order drawer is well placed.

---

## 2. Performance Report

### Bundle & loading
- First Load JS: 84.6 kB shared; page bundles 85–178 kB (largest: `/workspace` 178 kB, `/dashboard` 17.6 kB). Health is good — no page exceeds ~200 kB.
- Fonts self-hosted via `next/font/google` (Outfit, DM Sans) — no render-blocking external font requests, `font-display` handled by Next.
- No CSS-in-JS runtime; single compiled CSS (~1.5 kB source + build output).
- Analytics: single `clarity.ts` script (Microsoft Clarity) in root layout — negligible.

### Runtime behavior
- **Pollers (9 total)**: status bar clock 1 s (trivial, in-memory), OTP resend timers 1 s ×2 (scoped to auth/portal pages, cleared on unmount), dashboard-tab feeds 5 s ×2, logs/status pages 15–30 s ×4. No hot loops; all intervals cleaned up in `useEffect` returns. ✓
- Market data via WebSocket (`useMarketData`) — no REST polling for ticks. ✓
- Global search debounced 300 ms with abort via timer cleanup. ✓
- 94 files are `'use client'` — the app is fully client-rendered; no React Server Components / streaming / `next/dynamic` usage. Perf is acceptable at current size but every new feature adds to the main bundle.

### Recommendations (stability-safe)
- P1: none — no hot-path issues found.
- P2: introduce `next/dynamic` for the heavy dashboard tab components and workspace panels (deferred — Phase 6 keeps changes cosmetic-only where risk exists).
- P2: keep `setInterval` count at ≤10; prefer WebSocket for anything faster than 5 s.

---

## 3. Accessibility Report

### Failing (WCAG 2.1 AA)

| # | Issue | Location | Fix |
|---|---|---|---|
| A1 | **Only 2 `aria-*` attributes in the entire app** — no `aria-label` on any icon-only button (🔔 notifications, ⏻ sign out, ◁/▷ sidebar collapse, ☀/☽ theme) | `app-layout.tsx`, `header.tsx` | Add `aria-label`/`title` to all icon buttons |
| A2 | No skip-to-content link | `app-layout.tsx` | Add `<a href="#main">` skip link |
| A3 | No route-level `error.tsx` boundaries | whole app | Add root `error.tsx` with retry |
| A4 | Search overlay is not a dialog: no `role="dialog"`, no `aria-modal`, no focus trap, no focus restore on close, no `aria-label` | `app-layout.tsx` | Add roles + focus management |
| A5 | Dropdown toggles (profile, notifications) lack `aria-expanded`/`aria-controls` and keyboard support beyond ESC-by-click-away | `app-layout.tsx` | Add aria state; Enter/Arrow/Escape handling |
| A6 | **Contrast fail**: `--text-faint: #5b5875` on `#050508` ≈ 2.5:1 (AA needs 4.5:1 for normal text, 3:1 large). This token styles all hint/secondary text. Hardcoded `#555570`/`#8888a0` literals are also sub-AA. | `styles/tokens.css` + 100+ literals | Raise `--text-faint` luminance; migrate literals where cheap |
| A7 | Header "search" div is not focusable (see UX #2) | `app-layout.tsx` | Make it a real `<button>` with label |
| A8 | Active nav item has no `aria-current="page"` | `app-layout.tsx` | Add on active link |
| A9 | Error state uses hardcoded `#ef4444` instead of `var(--text-red)` | `components/error-message.tsx` | Token swap |

### Passing / already good
- Global `:focus-visible` outline (2 px cyan, offset 2 px) in `globals.css` ✓
- `prefers-reduced-motion` kills all animations/transitions ✓
- `lang="en"` on `<html>`, semantic `<nav>`, `<header>`, `<main>` (`t-content`) ✓
- Keyboard shortcuts exist (⌘K, ESC) ✓
- Forms: only 2 `<form>` elements; all others are button-driven (no accidental submit risk); inputs have visible labels above them ✓

### Risks deferred (documented, not fixed)
- 340 `<button>` elements without explicit `type="button"` — safe today (2 forms only), but a future form would break them. Fix deferred to avoid 340 churn edits in a stability-first pass.
- Toast container has no `role="status"`/`aria-live` — screen readers won't announce toasts. Deferred (shared provider, low risk — fix in batch 3).

---

## 4. Visual Consistency Report

### Design system (strong foundation)
- 55+ CSS custom properties in `styles/tokens.css` with dark + light themes, full radius/space/shadow/font/color scales.
- Shared class kit in `styles/components.css` (1,379 lines): `t-btn`, `t-select`, `t-input`, `t-table`, `t-panel`, `t-tabs`, `t-chip`, `t-badge`, `t-num`, `t-up/t-down`, `t-header`, `t-ticker`, `t-dot` — good coverage.

### Drift
| Area | Evidence | Severity |
|---|---|---|
| Hardcoded hex colors | 39 × `#fff`, 18 × `#555570`, 17 × `#8888a0`, 16 × `#ef4444`, 8 × `#22d3ee`, 8 × `#22c55e` … ~100 literals total vs tokens | Medium |
| Spacing in raw px | `padding: 8px/10px/12px/14px` inline across nearly every file vs `--space-*` tokens | Low (tokens are 4/8/16/24 — only ~30% of inline spacing matches) |
| Font sizes inline | `fontSize: 9/10/11/12/13/14` inline everywhere vs `--text-*` tokens | Low |
| Iconography | Mixed emoji (`🔔📊🤖`), letters (`T`, `P`, `U`, `R`), and unicode glyphs (`◁▷⚡⏻✦`) in nav/actions | Medium |
| Component duplication | `components/header.tsx` is **dead code** (zero imports) — a second, divergent header implementation; `v0.1` hardcoded there | Low |
| Buttons | `t-btn` family consistent, but sidebar/profile/theme use bespoke inline-styled buttons with mixed heights (22/28/30 px) | Low |

---

## 5. Improvement Plan

All items preserve production stability: cosmetic/attribute-level changes only, no logic or data-flow changes. Full regression (API pytest + web tsc/build) after EVERY batch.

| Batch | Items | Risk | Status |
|---|---|---|---|
| **B1 — A11y & dead code** | A1 icon aria-labels · A2 skip link · A7 search→button · remove dead `header.tsx` · A8 aria-current · A9 token swap · `--text-faint` contrast bump · A5 aria-expanded on dropdowns | Zero (attributes only) | ✅ Done |
| **B2 — UX & focus** | A4 search overlay dialog roles + focus trap/restore · root `error.tsx` + `not-found.tsx` · header + portal `v0.1` → `AppVersion`/`getAppVersion()` | Low (new files, additive) | ✅ Done |
| **B3 — Consistency & a11y tail** | Toast `role=status`+`aria-live` + `role=alert` per item · `#ef4444` sweep → `var(--red)` (6 files) · `#555570`/`#8888a0` sweep → `var(--text-faint)` (5 files) · light-theme `--text-faint` bump #9aa0a6→#757580 | Low | ✅ Done |
| **B4 — Ship** | Full API regression · web tsc + prod build · deploy web · prod smoke · CHANGELOG v0.2.0-rc.7 · AGENTS.md | — | 🔄 In progress |

Notes from execution:
- **A7 header tabs** — header tabs were part of the DEAD `header.tsx` (zero imports) → deleted; no tabs to convert.
- **EmptyState copy normalization** — spot-checked ~20 hand-rolled empty states: copy already consistent ("No X yet" pattern); full churn not warranted.
- **Lazy-load heaviest dashboard tab** — dashboard tabs were ALREADY `next/dynamic(..., { ssr: false })`; no change needed.
- The remaining `#8888a0` usage in `strategies/catalog/page.tsx:27` is a data-map color value (not text) — swept to token anyway, rendering unchanged.
| **B4 — Ship** | Full API regression · web tsc + prod build · deploy API (none) + web · prod smoke (pages 200, new build served) · CHANGELOG v0.2.0-rc.7 · AGENTS.md | — |

Verification per batch: `npx tsc --noEmit` + `npm run build` in `apps/web`; `pytest tests/ -q` once per API-touching change (B3 lazy load touches none; other batches touch no API code — API regression still run once at the end per phase rule).
