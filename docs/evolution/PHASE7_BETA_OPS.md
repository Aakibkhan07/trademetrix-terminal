# Phase 7 — Beta Operations Mode (evidence collection, GA)

Status: SHIPPED (v1.0.1, 2026-08-01)

## Mandate
The platform is GA. No new product features. The only work allowed: collect evidence from real users and make roadmap decisions from that evidence. Build the 7 components below, generate the 6 weekly reports below, and never ship a requested feature without user-behavior or user-request evidence.

## Components (7)
1. **Feedback Center** — in-app dialog (bug / feature / nps / report) persisted to Supabase; admin triage (new → triaged → resolved / wontfix) with notes.
2. **Product Analytics** — persistent event store (`analytics_events`), replaces the lossy in-memory tracker that lost everything on restart.
3. **User Journey Tracking** — session-scoped event stream (session.start, page.view, click, scroll.depth, client_error) with session replay per session.
4. **Funnel Analytics** — step funnels (default: signup → broker.connected → strategy.created → backtest.run → order.placed) with per-step users, cumulative, and drop-off %.
5. **Session Recording** — privacy-respecting event timeline (no DOM capture, no screenshots, no PII); redaction + sampling + excluded paths + Do-Not-Track respected.
6. **Crash Correlation** — client_error / api_error grouped by key/stack/path, affected sessions, crash-free rate.
7. **Beta Dashboard** — `/admin/beta`: overview KPIs, funnel, retention cohorts, feature usage, sessions + replay, crashes, feedback triage.

## Weekly reports (6) — `infra/scripts/analytics_report.sh` → `docs/weekly/<W>/`
- 06-funnel.md, 07-activation.md, 08-retention.md, 09-most-used-features.md, 10-drop-off.md, 11-most-requested-features.md

## Privacy invariants
- Client never sends `user_id`; the batch endpoint resolves it server-side from the auth cookie.
- Value events (order.placed, broker.connected, …) are recorded server-side from auth context.
- Sanitization: secret-like keys stripped, strings truncated, arrays capped, depth-limited.
- Configurable via `NEXT_PUBLIC_ANALYTICS_ENABLED` / `NEXT_PUBLIC_ANALYTICS_SAMPLE`; excluded paths `/auth`, `/admin`; Do-Not-Track honored.

## Architecture
- `application/services/analytics_service.py` — single DB-backed service (fail-open memory fallback) for ingest, feedback, and all queries.
- `routes/v1_analytics.py` — anonymous `track` / `track-batch` (CSRF-protected) + admin `overview|funnel|retention|features|sessions|sessions/{id}/events|crashes`.
- `routes/v1_feedback.py` — POST feedback (auth), GET/PATCH admin.
- `core/deps.py` `get_optional_user` — auth that degrades to anonymous.
- `main.py` timing middleware records `api_error` on 5xx.
- Migration `supabase/migrations/20250801_01300_analytics_persistence.sql` (applied to remote).

## Gotchas
- Test mocks must patch `application.services.analytics_service.get_supabase`/`async_supabase` (module-level imports), not `core.db`.
- `track_batch` skips malformed events silently (fail-open); `track_event` raises ValueError → 400.
- Client tracker CSRF: fetch `/auth/csrf` lazily, send `X-CSRF-Token`; keepalive fetch for page-hide flush (sendBeacon can't set headers).
- `docker cp` into the container intermittently fails with `/proc/self/fd` when the destination file already exists — `docker exec -u root rm -f` first.
- Deployment artifacts drift: container `/app` may hold older hot-deployed files — diff container vs repo before troubleshooting startup errors.
- Smoke script pattern: `create_access_token(<uuid sub>)` (NOT email), CSRF jar handshake, run with `docker exec -w /app -e PYTHONPATH=/app`.

## Evidence baseline (W31, real data)
- 26 accounts / 11 signed in ever / 9 last-7d; 15 never signed in. 4 broker creds (3 needs_attention), 2 traded users, 1 live trade. 7 builder strategies, 2 backtests by 1 user, 43 orders (29/8/6). ~49.9k requests (87 5xx, 653 429s). Fyers token churn dominant exception signature (issue #2).
- Analytics events = 0 in W31 (tracker shipped at end of W31) — W32 is the first real measurement week.
