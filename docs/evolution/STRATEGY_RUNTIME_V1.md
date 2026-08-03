# Strategy Runtime V1.0 — Deterministic Strategy Execution Layer

**Status:** IMPLEMENTED + CERTIFIED (26 unit/integration tests + 3 HTTP route tests, benchmarked)
**Date:** 2026-08-04
**Package:** `apps/api/strategy_runtime/`
**Version:** `1.0.0`

## 1. What it is

A first-class runtime that owns the full lifecycle of a running strategy:
start → run → pause/resume → stop → restart → recover — with per-strategy
isolation, a strict state machine, deterministic/idempotent restart, bounded
backpressure, and automatic recovery across restarts and broker disconnects.

It is the canonical replacement for the legacy ad-hoc runner path
(`engine/graph_strategy_runner`), which is retained as a fallback and bridged
for backward compatibility. The runtime composes on the frozen infra
(Broker SDK v2, Execution Engine v1, shared market socket, candle aggregator)
**without modifying any of it**.

## 2. Component map

```
strategy_runtime/
├── __init__.py          public API + __version__ = "1.0.0"
├── models.py            StrategySpec, StrategyTrigger, RuntimeState, statuses
├── state_machine.py     RuntimeStateMachine + IllegalTransition + can_transition
├── registry.py          RuntimeRecord + RuntimeRegistry (per-user/per-broker)
├── context.py           RuntimeContext + position_memory_for()
├── lifecycle.py         RuntimeLifecycle + strategy_runtime_lifecycle singleton
├── manager.py           StrategyRuntimeManager + strategy_runtime_manager singleton
├── dispatchers.py       RuntimeDispatcher / CandleDispatcher / TriggerDispatcher
├── workers.py           StrategyWorker (run loop, candles, time, manual evaluate)
├── recovery.py          RuntimeRecovery (restore + adopt + fail-open)
├── observability.py     RuntimeObservability + runtime_observability singleton
├── events.py            RuntimeEvent / runtime_bus
└── state_store.py       StrategyStateStore + CheckpointStateStore + InMemoryStateStore
```

## 3. Lifecycle & state machine

```
                   ┌──────────────────────────────┐
                   ▼                              │
   ┌────────┐  start  ┌──────────┐  pause  ┌─────────┐
   │STOPPED ├────────►│ RUNNING  ├────────►│ PAUSED  │
   └───▲────┘         └───┬───▲──┘         └────┬────┘
       │                  │   │                 │
       │                  │   └── resume ───────┘
       └── stop ──────────┘
```

Valid transitions are enforced by `RuntimeStateMachine.can_transition()`;
illegal ones raise `IllegalTransition`. State is persisted via
`StrategyStateStore` (Supabase-backed in prod, in-memory in tests) and
restored idempotently by `RuntimeRecovery` on startup:

| Persisted state | Restored to | Action |
|---|---|---|
| `running` | RUNNING | `start_strategy` re-run (same canonical path) |
| `paused` | PAUSED | start worker, immediately pause, resume resets MTF |
| `stopped` | STOPPED | no action |
| engine-held (legacy) | RUNNING | **adopted** — legacy task cancelled via `_stop_legacy`, ownership transferred |

Recovery is fail-open: any checkpoint failure degrades to "restore nothing"
rather than crashing startup.

## 4. Runtime guarantees

- **One worker per strategy**: single `StrategyWorker` task + per-strategy
  lock (`asyncio.Lock`) — no concurrent evaluation of the same strategy.
- **Order path unchanged**: `engine.gate.execute_order(..., source="graph_strategy")`;
  outcomes bridged to the Execution Engine via `execution_event_bus` (fire-and-forget).
- **Backpressure**: bounded per-worker queues with drop-and-count; dropped
  ticks are tracked by `strategy_runtime_dropped_ticks_total` (0 dropped in
  benchmark at ~78k ticks/s).
- **Seen-candle dedup**: per-strategy timestamp dedup persisted to the cache
  (Redis in prod), fail-open; replays collapse to a single evaluation
  (10,000 replays → 1 eval, 1 order in benchmark).
- **MTF aggregation**: `RuntimeContext` provides `add_candle()`/`get_candle()`
  per interval; time trigger folds into the candle pipeline with dedup.
- **Broker resilience**: disconnect → auto-pause; reconnect → auto-resume
  (per-broker isolation, verified by tests).
- **Idempotent stop/restart**: restarting from `stopped` restarts cleanly;
  restart mid-run restores to `running`; engine recovery **skips**
  runtime-owned strategies (checkpoint kind `strategy_runtime`).

## 5. Prometheus metrics (additive, in `core/prometheus.py`)

| Metric | Type | Labels |
|---|---|---|
| `strategy_runtime_running` | Gauge | — |
| `strategy_runtime_lifecycle_events_total` | Counter | `state` |
| `strategy_runtime_orders_total` | Counter | `outcome` |
| `strategy_runtime_errors_total` | Counter | — |
| `strategy_runtime_restarts_total` | Counter | — |
| `strategy_runtime_ticks_total` | Counter | — |
| `strategy_runtime_dropped_ticks_total` | Counter | — |
| `strategy_runtime_latency_seconds` | Histogram | — |
| `strategy_runtime_recovery_seconds` | Histogram | — |

## 6. HTTP surface (`/api/v1/runtime`, auth-gated)

| Method | Path | Action |
|---|---|---|
| POST | `/deploy` | start strategy from spec |
| POST | `/{id}/stop` | stop |
| POST | `/{id}/pause` | pause |
| POST | `/{id}/resume` | resume |
| POST | `/{id}/restart` | restart |
| POST | `/{id}/evaluate` | dry-run manual evaluate (no orders) |
| GET | `/{id}/status` | status + metrics |
| GET | `/strategies` | list runtime strategies |
| GET | `/health` | runtime health + metrics |
| POST | `/event` | admin event publish (`require_admin`) |

Builder routes (`/api/v1/builder/...deploy/start/stop`) now **delegate to the
runtime first**, falling back to `start_graph_strategy` only if the runtime
is unavailable.

## 7. App integration (`main.py`)

1. `strategy_runtime_manager.configure_state_store(SupabaseCheckpointStore())`
2. `await strategy_runtime_manager.initialize()` (fail-open)
3. Background task: sleep 4s (engine recovery runs first) → `RuntimeRecovery(...).recover()`
4. Graceful shutdown: `strategy_runtime_manager.shutdown()` (scheduler → workers → dispatcher)

## 8. Verification

- `tests/test_strategy_runtime.py` — 18 tests: lifecycle, state machine table,
  pause/resume/restart, restart-from-stopped, candle eval + orders, seen-candle
  dedup, no-signal, two-strategy isolation, MTF aggregation, manual dry-run,
  broker disconnect/reconnect + per-broker isolation, session open/close,
  checkpoint persist/remove, health, user isolation.
- `tests/test_strategy_runtime_recovery.py` — 8 tests: restore running,
  idempotent recovery, skip stopped, paused-as-paused, adopt legacy-running,
  engine-recovery skip guard, legacy-only restart, fail-open broken store.
- `tests/test_strategy_runtime_api.py` — 3 HTTP tests: deploy→status→pause→
  resume→evaluate→stop lifecycle, health, 404 on unknown id.
- Full regression: **806 passed, 1 xfailed** (pre-existing warnings only).

### Benchmark (`benchmark_strategy_runtime.py`)

| Scenario | Result |
|---|---|
| Tick throughput | 50,000 ticks in 0.641s ≈ **78k ticks/s, 0 dropped** |
| Candle evaluation | 10,000 candles, **15.7k evals/s**, avg latency 0.31ms, 10,000 orders |
| Multi-strategy fanout | 10 workers, 10,000 ticks → **4.2k ticks/s**, min=max worker ticks, 0 dropped |
| Seen-candle dedup | 10,000 replays → **1 eval, 1 order** |

Results: `/tmp/strategy_runtime_bench.json`.

## 9. Known limitations

- Order execution still goes through the frozen `engine.gate.execute_order`
  path; runtime-level risk integration (position/order checks) is deferred.
- Recovery checkpoint reads are fail-open by design — a broken store means
  strategies are not auto-restored (never crashes the app).
- Supabase `strategy_runs` insert noise in prod logs (permission-related) is
  benign — non-fatal, warn-level only.

## 10. Rollback

All changes are additive. To disable the runtime: remove the router include +
lifespan init/recovery block in `main.py` and revert the builder-route
delegation — legacy `start_graph_strategy` path remains fully functional.
