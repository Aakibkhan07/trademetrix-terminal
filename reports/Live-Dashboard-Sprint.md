# Live Dashboard — Sprint Report (v1.6.8)

Date: 2026-08-07 · Scope: unified `/live` operational cockpit + landing wiring (Phase A→D)
Build: web BUILD_ID `YCwC6U2jJMRugxdXVPcI1` (PRODUCTION VERIFIED)

## Summary
A ZingTrade-inspired but not-copied unified dashboard at `/live` was built purely by **composing
existing services** inside the `trademetrix-terminal` monorepo — zero new REST endpoints, zero
OMS/Execution/Broker/Risk/Strategy changes in this release, no deletions, no CSS additions.

## Phases
- **Phase A (backend, earlier)**: canonical `SignalPayload` (signal_version=1) emitted by both
  runtimes via the execution event bus; `apps/api/tests/test_signal_payload.py`; suite 963 passed / 1 xfailed.
- **Phase B (frontend widgets, complete)**: `apps/web/components/live/` — 13 files (types,
  use-live-connection, use-live-data, widget-frame, table, market-overview, positions-panel,
  orders-panel, use-live-feed, signal-card, live-signals, trading-controls). Gates clean:
  `tsc --noEmit` 0, `next lint` 0 new, build clean.
- **Phase C (page + landing wiring, complete)**: `app/live/page.tsx`; logo, Home nav,
  admin-route bounce, sign-in and onboarding redirects → `/live` (non-admins) / `/dashboard`
  (admins); landing CTA → `/live`. Typecheck/build/lint green (env swap + restore).
- **Phase D (production, complete)**: hot-deploy of `.next` (stop / `docker cp` / start /
  `chown -R 1001`); public `/live`, `/`, `/portfolio` 200; API health 200; BUILD_ID matches
  locally, in-container, and in the served manifest.

## Browser smoke on prod (13/13 PASS)
- Anonymous `/live` → redirects to `/auth` gate (expected) — no page errors.
- Fresh signup → `/onboarding` → "Open Dashboard" CTA → `/live` (validates landing chain).
- On `/live` (signup + plain sign-in): header chips (Market CLOSED, Stream, Online), Market
  Overview, NIFTY/BANK ticker cards, Positions/Orders/Portfolio tabs, chart symbol chips,
  Trading Controls (Emergency Stop + Pause All + diagnostics), Live Signals (filters +
  empty-state) all render. Note: panel titles are CSS-uppercased — match case-insensitively.
- Nav logo links to `/live`.
- All smoke users swept from prod (GoTrue admin; total 26).

## Post-deploy state
- Health: API + web 200. Kill switch `global:kill_switch` = `1`, TTL -1 (default, untouched).
- No order placement / state mutations during the browser smoke.

## Notes
- Widgets call only existing `api.*` methods: `market.status`, `marketdata.quote`, `engine.positions`,
  `engine.orders`, `engine.cancelOrder`, `engine.funds`, `paper.positions`, `paper.account`,
  `runtime.health`, `runtime.strategies`, `runtime.emergencyStop`, `runtime.release`,
  `runtime.pauseAll`, SSE `useEvents()/SignalGenerated`.
- Open questions: none blocking. The working tree is uncommitted (no git push performed).