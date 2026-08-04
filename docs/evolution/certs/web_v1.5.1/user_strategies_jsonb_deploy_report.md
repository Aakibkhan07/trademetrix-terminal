# Deployment Report — user_strategies JSONB Parity Fix (v1.5.2)

**Date:** 2026-08-04 · **Type:** Correctness deployment (final pre-freeze) · **Commits:** `ebcf9ff`, `19a1bbc` · **Migration:** `20260804_01800_user_strategies_jsonb.sql`

## Summary

The legacy `/api/v1/user-strategies` service assumed a dev-only relational schema
(`user_strategy_legs` join + `entry_time`/`overall_*` columns) that does not exist on
the production Supabase project. Production stores legs as a `legs` jsonb column and the
legacy scalar fields under a `config` jsonb column. Every list/get/create on prod failed
(PGRST200 phantom join / PGRST204 missing columns). This deployment makes the service
write and read the live prod schema, with an additive idempotent migration so dev and
prod column sets converge.

## Schema findings (prod vs dev)

| Aspect | Prod `user_strategies` | Dev (00500 legacy) |
|---|---|---|
| Legs | `legs` jsonb | relational `user_strategy_legs` table |
| `entry_time`, `overall_sl_type/value`, `overall_target_type/value` | inside `config` jsonb | dedicated columns |
| `days_of_week`, `exit_time`, `index_symbol`, ... | columns | columns |

- `user_strategy_legs` does **not exist** in prod (verified: absent from PostgREST OpenAPI definitions).
- `plans` is dead (no live code path); `risk_audit_log` remains a separately tracked pending migration.

## What changed

- **`application/services/strategy_service.py`** — `list/create/get/update/_row_to_strategy` now:
  - `select("*")` (no phantom `legs:user_strategy_legs(*)` join),
  - write legs as jsonb on the row,
  - fold `entry_time`/`overall_sl_type`/`overall_sl_value`/`overall_target_type`/`overall_target_value`
    into `config` jsonb on create and merge into existing `config` on update (columns don't exist on prod),
  - `_row_to_strategy` uses `normalize_user_strategy_row` (config merged back, `days_of_week` array parse).
- **`core/models.py`** — added `normalize_user_strategy_row()`.
- **`engine/user_strategy_runner.py`** — `_get_open_legs` reads the jsonb `legs` column via the normalized row.
- **`ai/copilot.py`** — funds context reads the existing `margin_snapshot` table (no phantom `funds_snapshot`).
- **Migration `20260804_01800_user_strategies_jsonb.sql`** — `ADD COLUMN IF NOT EXISTS config/legs` jsonb with defaults.
  On prod it is a **no-op** (columns already present — verified via OpenAPI). Applied to the local Docker Supabase
  stack and verified; safe to run anywhere (idempotent, additive).

## Deployment (VPS)

1. `git push origin main` → VPS `git fetch && git reset --hard origin/main` (`ebcf9ff` then `19a1bbc`).
2. Hot-copy `strategy_service.py`, `models.py`, `user_strategy_runner.py`, `copilot.py` → `trademetrix_api` → restart.
3. `/health` 200, `/health/ready` `{"status":"ok","dependencies":{"database":true,"cache":true}}` after each restart.
4. **Schema cache reload:** PostgREST OpenAPI fetched from inside the container confirms `user_strategies` exposes
   `legs` and `config` and does **not** expose `user_strategy_legs` — no stale schema remains, no cache reload needed
   (columns pre-existed; no `NOTIFY pgrst` required on prod).

## Verification

### API E2E (prod, in-container, real user token + CSRF)
| Step | Result |
|---|---|
| Create strategy (2 legs + config fields) | 201, id returned |
| Read | legs=1→2 after update, `entry_time=10:00` merged from config, `overall_sl_value=20` |
| Update (name + legs) | 200 |
| List | strategy present with 2 legs |
| **API restart** | strategy re-read: 200, legs=2, updated name, config preserved |
| DB rows (PostgREST select) | `config={"entry_time":"10:00"}`, `legs=2` for both persisted rows |

### Browser E2E (puppeteer, real prod UI + browser session cookies/CSRF) — **13/13 OK**
Flow: UI signup → promote test user (profiles.role=super_admin) → **Create** (POST, 201, 2 legs)
→ **Read** (legs=2, config merged) → **Edit+Save** (PUT name v2, legs=2) → **Reload** (real
`page.reload()`, session persists) → **Deploy/Start** (PAPER deploy, 2/2 results success, status `active`)
→ **Stop** (PATCH status `paused`, verified) → **Delete** (204) → zero page errors.
Artifacts: `web_v1.5.1/user_strategies_jsonb_deploy/{e2e-results.json, 01-signed-up.png, 03-after-reload.png}`.
Script: `e2e-strategy-jsonb.js` (p0e2e harness).

### Logs
- No `PGRST2xx`/`schema cache`/`Could not find the ... column` errors after deploy.
- 3× `RuntimeError("No response returned")` observed during the E2E window — **pre-existing**
  `core/middleware/timeout.py` 30s abort on the deploy's historical-data fetch (request still
  returned 200 to the client; known noise class, not schema-related, not introduced by this change).
- yfinance 404 (`NIFTY26AUGFUT.NS`) and Redis event-queue reconnect blips remain pre-existing noise.

### Regression
Full API suite local: **858 passed, 1 xfailed** (strategy suites 60/60 green with the config-fold write path).

## Findings for the beta backlog (out of scope here)

1. Dashboard admin tab "User Strategies" fetches `/api/v1/admin/strategies/all-user` which does **not exist**
   in the API (404 → tab renders empty). Either implement the admin endpoint or remove the tab.
2. There is no end-user UI for the legacy `user-strategies` lifecycle (create/edit/deploy mutations exist in
   `lib/queries/strategies.ts` but have no consumers) — the browser E2E therefore drove the real prod API
   from inside the browser session. Multi-leg strategies page (`/strategies/multi-leg`) covers a different table.

## Cleanup

- All E2E test strategies deleted (`name=like.*JSONB*` → 0 rows remain).
- 6 test users (`jbjsonb*@example.com`) removed: `audit_log`, `user_strategies`, `positions_snapshot`, `orders`,
  `profiles`, then `auth.users` via GoTrue admin endpoint. 0 remain.

## Verdict

**GO.** Schema cache consistent, no stale schema, no empty legs/config anywhere, health endpoints green,
13/13 browser E2E, no regressions (858+1 xfailed). This is the final correctness deployment; per the
maintainer decision, **feature freeze is now in effect**.
