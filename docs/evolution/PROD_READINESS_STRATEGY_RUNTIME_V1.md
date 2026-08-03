# Strategy Runtime V1.0 — Production Readiness Report

**Date:** 2026-08-04 | **Status:** READY (pending VPS deploy + prod smoke)

## 1. Production configuration

| Item | Config |
|---|---|
| State store | `SupabaseCheckpointStore()` via `configure_state_store` (fail-open) |
| Startup | lifespan `initialize()` (fail-open) + 4s-delayed recovery task |
| Shutdown | `strategy_runtime_manager.shutdown()` on graceful stop |
| Metrics | 9 additive Prometheus metrics in `core/prometheus.py` |
| Auth | `/api/v1/runtime/*` behind `get_current_user`; `/event` admin-gated |
| Builder | deploy/start/stop delegate runtime-first, legacy fallback |

## 2. Failure-mode matrix

| Failure | Behaviour | Verified |
|---|---|---|
| Supabase checkpoint unavailable at boot | init/recover fail-open; runtime still serves | ✔ (fail-open tests) |
| Store error during recovery | restore nothing; no crash | ✔ `test_*_broken_store` |
| Legacy runner holding a strategy | runtime adopts + cancels legacy task | ✔ `test_adopt_legacy_running` |
| Broker disconnect | auto-pause, orders halted per broker | ✔ |
| Broker reconnect | auto-resume, MTF reset | ✔ |
| Redis cache down (seen-ids) | fail-open dedup, evaluation proceeds | ✔ |
| Engine recovery at boot | skips runtime-owned strategies | ✔ |
| Runtime down at builder call time | legacy `start_graph_strategy` fallback | ✔ (delegation) |

## 3. Operations notes

- Prod restart is automatic: strategy checkpoints are restored 4s after boot;
  paused strategies stay paused across restarts.
- Watch metrics: `strategy_runtime_running` (Gauge), `_dropped_ticks_total`
  (must stay 0), `_errors_total` (spikes = investigate).
- Known benign noise: `strategy_runs` insert warnings (permission-related,
  warn-level) during checkpoint persistence.
- Rollback: disable router + lifespan block and revert builder delegation;
  legacy runner remains intact (see `docs/evolution/STRATEGY_RUNTIME_V1.md` §10).

## 4. Deploy checklist

1. [x] Full regression green (806 passed)
2. [x] Benchmark results recorded
3. [ ] Commit + push `main`
4. [ ] VPS `git fetch && git reset --hard origin/main`
5. [ ] `docker restart trademetrix_api`
6. [ ] Prod smoke: `/api/v1/runtime/health`, recovery logs, builder deploy path
