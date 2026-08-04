# Beta Hardening Sprint Report — v1.5.1 (2026-08-04)

Data-driven reliability pass for the v1.5.0-beta release, driven by 48h of production
telemetry, browser error instrumentation, and beta feedback. Scope: no new features —
fix reliability, usability, performance, and correctness defects with regression tests
and documentation.

## Telemetry sources

- **48h prod API logs** (`docker logs trademetrix_api`, captured read-only from the VPS).
- **Browser error events** ingested by the API analytics pipeline (`client_error`, `api_error`,
  `feedback_items`).
- **Schema probe** via the PostgREST API (Supabase service role) — direct psql is blocked,
  so all schema inspection went through the REST layer.

## Findings (prioritized)

| ID | Signal | Evidence (48h) | Severity | Verdict |
|----|--------|----------------|----------|---------|
| P1 | Kill-switch global gate silently disabled | 8× `invalid input syntax for type uuid: "system"` → probe always False | Critical | **Fixed** (INC-015) |
| P1 | Emergency stop lost on container restart + audit persistence dead | `risk_audit_log` missing (`PGRST205` ×3-4); state was in-memory | Critical | **Fixed** (INC-015) |
| P1 | `/engine/positions\|funds` raw 500s | 43× `Token refresh failed ... CircuitBreaker[broker_fyers] is open` | High | **Fixed** (INC-016) |
| P2 | Paper bracket SL/TARGET quotes starved + log flood | 5542× `Paper bracket quote refresh failed` | Medium | **Fixed** (INC-017) |
| P2 | `async_safe_single` None-masking noise | ~70× `'NoneType' object has no attribute 'data'` | Medium | **Fixed** |
| P3 | Rate-limit budget exhaustion by client telemetry | track-batch alone ≈12/60 RPM; 19× 429 hits | Low | **Fixed** |

Browser `client_error` events were **all pre-2026-08-03** (`Failed to parse color: color-mix(...)`)
and stopped after the v1.5.0 web build — 0 post-deploy. `feedback_items` = 9 rows, all test data.
`api_error` events: option-chain 503s (upstream) and an old auth/signup 500; no action this sprint.

## Fixes

### 1. Kill switch — restart-safe, real global gate, surviving audits (P1)
`apps/api/risk/kill_switch.py` rewritten:

- `global_kill_switch_active()` now reads the Redis key `global:kill_switch` (set/cleared by the
  admin enable/disable actions). The previous implementation probed `risk_settings` for a row with
  `user_id='system'`, which is a uuid FK column — the literal could never match, raising
  `22P02 invalid input syntax for type uuid: "system"` and **returning False every time**. The
  global gate therefore never fired. Now fail-secure: an admin `enable` sets the key and the gate
  reads it in-process.
- Emergency-stop state persists to Redis under `kill_switch:emergency:{uid}` before the in-memory
  flag flips closed. `recover()` restores from Redis first, then the DB audit trail, so a container
  restart cannot silently re-arm trading after an emergency stop.
- `_persist_audit()` writes to `risk_audit_log` and falls back to the existing `audit_log` table when
  the dedicated table is absent. Emergency-stop audit records survive even on a broken schema.
- New migration: `supabase/migrations/20260804_01600_risk_audit_log.sql` (idempotent,
  `user_id` TEXT to avoid the uuid-vs-`'system'` trap, index on `(user_id, event, created_at DESC)`).
  **Not yet applied to prod** — the API has no DDL access; apply via the Supabase SQL editor. Until
  then the `audit_log` fallback persists audits (one `PGRST205` warn per emergency audit write).

### 2. Graceful broker-token expiry (P1)
`apps/api/core/exceptions.py`:

- New `BrokerTokenExpiredError` (AppError, `401 BROKER_TOKEN_EXPIRED`).

`apps/api/brokers/token_manager.py`:

- Fast-fails with `BrokerTokenExpiredError` when the stored `token_expires_at`/`expiry` is already
  past — raised **before** any broker client is constructed.
- An open circuit breaker during a refresh attempt is translated into `BrokerTokenExpiredError`
  rather than leaking `RuntimeError: Token refresh failed ...`.

`apps/api/application/services/engine_service.py`:

- `get_positions`/`get_funds` propagate `BrokerTokenExpiredError` (→ 401 with code, so the web app
  can prompt broker re-auth) and still swallow transient `RuntimeError`/`CircuitBreakerError`/
  `ValueError` → empty data (no more 500s on read-only endpoints).

### 3. Paper bracket quotes independent of a live broker token (P2)
`apps/api/oms/manager.py` `_bracket_quote_fetch`:

- Paper orders now resolve SL/TARGET prices from the market cache, then a broker-agnostic Yahoo
  `fetch_quotes` (with write-back), and only fall back to the broker REST client last.
- New `_log_throttled(fmt, symbol, *args)` warns at most 1/60s per symbol — the 5542-line flood
  collapses to a handful of lines.

### 4. `async_safe_single` None guard (P2)
`apps/api/core/safe_query.py`:

- Guards against `execute()` returning None, logs (once) a meaningful message, and returns None —
  stop masking underlying queries with `'NoneType' object has no attribute 'data'`.

### 5. Rate limiter (P3)
`apps/api/core/ratelimit.py`:

- Default per-IP budget 60 → 120 RPM.
- `/analytics/track-batch` is exempt from the shared per-IP budget (returns with
  `X-RateLimit-*` headers) so client telemetry can never starve functional endpoints.

## Regression tests

| File | Cases | Covers |
|------|-------|--------|
| `tests/test_kill_switch_hardening.py` | 7 | global gate from Redis, trigger/release Redis persistence, restart-safe recover, `audit_log` fallback, no-table audit, fail-closed trading on audit failure |
| `tests/test_token_manager_hardening.py` | 4 | expired stored token fast-fails pre-`create_broker`, future expiry still refreshes, CircuitBreaker→`BROKER_TOKEN_EXPIRED`, valid-session path |
| `tests/test_safe_query_hardening.py` | 3 | None result, data result, exception→None |
| `tests/test_ratelimit_hardening.py` | 3 | exemption predicate, track-batch bypass, functional paths still counted |
| `tests/test_bracket_quote_hardening.py` | 4 | cache-first, stale→Yahoo, no-token-need, all-sources-dead→0.0 |
| `tests/test_engine_service.py` (+4) | — | propagates `BrokerTokenExpiredError`, degrades transient broker errors |
| `tests/test_risk_fail_closed.py`, `test_auto_trading.py` | adapted | sync fixtures + Redis cleanup (async autouse fixture unsupported in this pytest-asyncio setup) |

Full suite: **858 passed, 1 xfailed** (v1.5.0 baseline 832 passed, 1 skipped, 1 xfailed).

## Production verification

- Deployed commit `fd896ca` via repo sync (`/root/trademetrix-terminal` at `origin/main`) +
  hot-copy of the 7 changed API files into `trademetrix_api` + container restart; API healthy
  (`/health` and `/health/ready` → 200).
- Kill-switch smoke (in-container, prod Redis): emergency POST → `kill_switch:emergency:{uid}` set →
  fresh `KillSwitch().recover()` sees the stop → release clears the key ✅; global enable sets the
  Redis flag and `global_kill_switch_active()` → True ✅; both fully cleaned up after ✅.
- `/engine/positions` and `/engine/funds` → **200 with live data** (the prod Fyers token was
  re-validated by the auto-refresh cron; the 401 path is covered by unit tests).
- Prod logs since restart (30 min): **0×** `invalid input syntax for type uuid`, **0×**
  `Paper bracket quote refresh failed`, **0×** `CircuitBreaker[broker_fyers] is open` tracebacks,
  **0×** `async_safe_single query failed` (`--since` windows bounded by the 05:37:41Z restart
  timestamp).

## Follow-ups

- Apply `20260804_01600_risk_audit_log.sql` to the prod Supabase project (SQL editor) to eliminate
  the `PGRST205` fallback warn (tracked in KNOWN_ISSUES item 14).
- Observe the next Fyers token expiry: `/engine/*` should now yield a clean
  `401 BROKER_TOKEN_EXPIRED` that the web app can surface as a "re-connect broker" prompt.