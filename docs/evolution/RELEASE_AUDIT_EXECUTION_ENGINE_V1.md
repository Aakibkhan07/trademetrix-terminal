# Release Audit — Execution Engine v1.0 (2026-08-03)

## Scope

Production-readiness audit of the Execution Engine v1.0 at commit `b1cef9e`
(`apps/api/execution_engine/`). Objective: **verify the engine under production
conditions and fix any verified production defect** — no features, no
architecture changes, no speculative optimization.

Audit harness: `ee_audit.py` (scratch), run from `apps/api`, exits non-zero on
any failed check. All checks PASS (43/43), exit 0.

## Method

- Static read of every engine module: `events`, `state_machine`, `fifo`,
  `trades`, `positions`, `pnl`, `portfolio_engine`, `engine`, `metrics`,
  `init`.
- Traced the **production event path**: `oms/manager.py`,
  `paper/paper_broker.py`, `execution/manager.py` → legacy string bus →
  `bridge_legacy_events()` → canonical bus → `TradeManager` → `PositionManager`
  → `PnLEngine` → `PortfolioEngine`.
- Stress harness (10 test groups, 43 checks): multi-broker/multi-user/multi-
  account isolation, FIFO vs an independent reference implementation, partial +
  multiple fills + duplicate acks, 10k-fill stress (3 brokers, 5 users, 4
  symbols, 4 strategies), 20k-thread event storm, facade lifecycle flows,
  graceful shutdown + restart continuity, memory/leak (tracemalloc), mixed-3000
  fill consistency (FIFO vs position vs PnL vs equity vs snapshot), and a new
  legacy-bridge integration group.

## Verified production defect (fixed)

**The engine never received production fills.** Two independent faults in the
legacy bridge combined, so the canonical engine (positions / PnL / portfolio)
could not update from any real order:

1. `bridge_legacy_events()` subscribed with the wrong signature:
   `execution_event_bus.subscribe(_forward)` (one argument). The legacy bus
   `subscribe(event_type, callback)` requires two; the call raised
   `TypeError` which was caught and only logged as a warning. The bridge had
   **zero subscribers** — verified: `legacy subscribers: {}` after wiring.
2. The `_TYPE_MAP` mapped the never-produced event name `OrderFilled`, but the
   real producers emit:
   - OMS fills → `"OrderCompleted"` (`oms/manager.py:479,495,622`) — **unmapped**
   - paper fills → `"PaperOrderFilled"` / `"PaperOrderPartiallyFilled"` /
     `"PaperOrderPending"` (`paper/paper_broker.py:198,221`) — **unmapped**
   - `"OrderFilled"` is produced nowhere in the repo (verified by exhaustive
     string search).

Even with the mapping corrected, the forwarder only copied
`user_id/broker/execution_request_id/message/payload`; fill fields
(`symbol`, `side`, `quantity`, `filled_quantity`, `avg_price`) were absent, so
`TradeManager._build_trade` would have dropped every trade
(`filled_quantity=0` → skipped).

### Fix (`apps/api/execution_engine/events.py`)

- Correct subscription: `execution_event_bus.subscribe("*", _forward)`.
- Extend `_TYPE_MAP`:

  | Legacy event | Canonical event |
  |---|---|
  | `OrderCompleted` | `order.filled` |
  | `PaperOrderFilled` | `order.filled` |
  | `PaperOrderPartiallyFilled` | `order.partially_filled` |
  | `PaperOrderPending` | `order.pending` |
  | `OrderRejected` / `OrderPending` / `OrderCancelled` / `OrderExpired` / `RiskDecision` | (already mapped) |

- Populate the canonical fields for fill events from the payload (OmniOrder
  dump for OMS, `order`/`fill` for paper): `symbol`, `side`, `quantity`,
  `filled_quantity`, `avg_price`, `order_id`, `broker_order_id`.
- Idempotence guard (`_LEGACY_BRIDGE_WIRED`) so init/shutdown/init does not
  double-wire the forwarder (the legacy bus dedupes by callback identity, but a
  fresh closure per call otherwise leaks duplicates).

### Secondary lifecycle fix (`apps/api/execution_engine/init.py`)

`shutdown_execution_engine()` now resets the module `_initialized` flag. Before:
`init → shutdown → init` was a no-op (bus stayed stopped, silently falling back
to non-thread-safe inline dispatch). After: the documented idempotent
init/shutdown lifecycle cycle re-wires and restarts the bus.

## Audit results

### Behavior / correctness

| Check | Result |
|---|---|
| Multi-broker isolation (paper/fyers/zerodha positions) | 10/20/30 |
| Multi-user isolation | PASS |
| FIFO realized vs independent reference (2000 fills) | 3910.04 == 3910.04 |
| FIFO net qty vs reference | 17782 == 17782 |
| Partial fills (3 tranches) net / trade count / VWAP | 65 / 3 / 100.92 |
| Final-tranche `order.filled` | 75 |
| 10k stress: 3 brokers × 5 users × 4 symbols × 4 strategies | trades=10000/10000, 1531 fills/s |
| Ledger↔position consistency across 60 position buckets | mismatches=0 |
| Ring-buffer sequence strictly increasing | PASS |
| Storm: single-publisher FIFO (5000) | delivered 5000, dup=0, ooo=0 |
| Storm: 4-thread publish (20k) | all delivered, 0 dups, 0.9s |
| Facade: filled / rejected / duplicate-silent / failed / cancel / modify / not-found | all PASS |
| Graceful shutdown stops bus | PASS |
| Restart re-initializes bus + position continuity (6 qty, 40.0 pnl) | PASS |
| Memory: ring ≤2000, ledger ≤20k/bucket, inline tasks drained | PASS |
| Consistency (3000 fills): realized / net / PnL / equity / snapshot | 2889.49 / 537, all matched |
| **Legacy bridge: `OrderCompleted` → position 10 @ 71.75** | PASS |
| **Legacy bridge: `PaperOrderFilled` → position 4 @ 73.25** | PASS |
| **Legacy bridge: `PaperOrderPartiallyFilled` → trade recorded** | PASS |
| **Legacy bridge: unmapped events ignored; wiring idempotent** | PASS |

Full raw output: audit harness log (scratch; `TOTAL: 43 checks, 0 FAILURES`);
**known limitations are reported separately** and intentionally do not fail the
harness.

## Regression

- `tests/test_execution_engine.py` → **45 passed** (40 baseline + 5 new:
  `TestLegacyBridge` × 4, `TestInit::test_shutdown_then_reinit_restarts_bus`).
- Full suite `pytest tests/` → **762 passed, 1 xfailed** (baseline 757 + 5).

## Files changed

- `apps/api/execution_engine/events.py` — bridge subscribe fix, extended
  `_TYPE_MAP`, fill-field population, idempotence guard.
- `apps/api/execution_engine/init.py` — shutdown resets `_initialized`.
- `apps/api/tests/test_execution_engine.py` — +5 regression tests.

## Open items (not blocking, tracked)

- Persist the audit harness under `tests/` or `tools/` for repeatable
  certification (currently in scratch).
- Consider a durable `TradeStore`/`SnapshotStore` adapter (see Known
  Limitations).