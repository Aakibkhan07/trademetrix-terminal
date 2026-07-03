# Execution Layer Integration — Phase 4.5

## Objective

Make `ExecutionManager` the **single unified path** for all order operations across the platform.

## Old Flow (Before Integration)

```
                        ORDER PLACEMENT

  v1_engine.py ──▶ gate.execute_order() ──▶ get_broker() ──▶ adapter.place_order()
  v1_tradingview.py ──▶ gate.execute_order() ──▶ get_broker() ──▶ adapter.place_order()
  v1_admin.py ──▶ gate.execute_order() ──▶ get_broker() ──▶ adapter.place_order()
  executor.py ──▶ gate.execute_order() ──▶ get_broker() ──▶ adapter.place_order()
  manager.py ──▶ adapter.place_order()           (separate path, no validation/audit)

                        ORDER CANCELLATION

  v1_engine.py ──▶ executor.engine.cancel_order() ──▶ adapter.cancel_order()
  executor.py ──▶ adapter.cancel_order()              (no retry, no audit)
  manager.py ──▶ adapter.cancel_order()               (separate path)

                        ORDER MODIFICATION

  manager.py ──▶ adapter.modify_order()               (only path, but no events)
```

**Problems:**
- 6 different code paths for execution
- Duplicate validation, auth, audit logic
- No unified retry, idempotency, or observability
- Direct broker adapter calls bypassing all safeguards

## New Flow (After Integration)

```
                        ORDER PLACEMENT

  All callers ──▶ gate.execute_order() ──▶ ExecutionManager.place_order()
                                              │
                                              ├── duplicate check
                                              ├── validation
                                              ├── broker connect
                                              ├── retry with backoff
                                              ├── event publish
                                              ├── audit log
                                              └── observability

                        ORDER CANCELLATION

  All callers ──▶ ExecutionManager.cancel_order()
                     ├── retry with backoff
                     ├── event publish (OrderCancelled)
                     ├── audit log
                     └── observability

                        ORDER MODIFICATION

  All callers ──▶ ExecutionManager.modify_order()
                     ├── retry with backoff
                     ├── event publish (OrderModified)
                     ├── audit log
                     └── observability
```

## Integration Points

### 1. `engine/gate.py` — `execute_order()`

**Before:** Direct broker adapter resolution and `adapter.place_order()` with inline auth.

**After:** Thin backward-compatible wrapper:
1. Risk check (RiskGuard)
2. Paper mode routing  
3. Broker resolution from DB
4. Converts `NormalizedOrder` → `ExecutionRequest`
5. Delegates to `execution_manager.place_order(req)`
6. Converts `ExecutionResult` → `OrderResult`

**Callers unaffected:**
- `routes/v1_engine.py:128` — POST /trade
- `routes/v1_tradingview.py:61` — webhook handler
- `routes/v1_admin.py:363` — admin broadcast
- `engine/executor.py:46` — execute_signal

### 2. `engine/executor.py` — `cancel_order()`

**Before:** Direct `adapter.cancel_order()` call.

**After:** Delegates to `execution_manager.cancel_order()` with retry and audit.

### 3. `routes/v1_engine.py` — `POST /orders/{id}/cancel`

**Before:** Used `_get_engine()` which created a full ExecutionEngine per user.

**After:** Calls `execution_manager.cancel_order()` directly.

### 4. `execution/manager.py` — `modify_order()` / `cancel_order()`

**Before:** No event bus publishing.

**After:** Publishes `OrderModified`, `OrderCancelled`, `OrderFailed` events.

### 5. `execution/manager.py` — `sync_positions()`

**Before:** No event publishing.

**After:** Publishes `PositionUpdated` event.

## Events Published

| Event | Trigger | Publisher |
|-------|---------|-----------|
| `OrderValidated` | Validation passed | `ExecutionManager.place_order()` |
| `OrderPlaced` | Order successfully placed | `ExecutionManager.place_order()` |
| `OrderRejected` | Validation or broker rejection | `ExecutionManager.place_order()` |
| `OrderFailed` | Execution error | `ExecutionManager.place_order()` |
| `OrderModified` | Order modified successfully | `ExecutionManager.modify_order()` |
| `OrderCancelled` | Order cancelled successfully | `ExecutionManager.cancel_order()` |
| `PositionUpdated` | Positions synced | `ExecutionManager.sync_positions()` |

## Removed Duplication

| Duplication | Resolution |
|-------------|------------|
| Broker authenticate in gate.py | Removed — ExecutionManager handles connect |
| Broker authenticate in executor.py | Removed — ExecutionManager handles connect |
| Direct adapter.place_order() in executor.py | Removed — delegates to ExecutionManager |
| Direct adapter.cancel_order() in executor.py | Removed — delegates to ExecutionManager |
| Inline audit logging in gate.py | Kept for backward compat; ExecutionManager also audits |
| Separate ExecutionEngine per user/broker | Cancel route now bypasses ExecutionEngine |
| Duplicate idempotency check (gate vs manager) | Both exist — gate checks client_order_id, manager checks execution_request_id |

## Files Modified

| File | Changes |
|------|---------|
| `engine/gate.py` | `execute_order()` now delegates to `ExecutionManager.place_order()`. Removed direct broker auth/adapter calls. Added conversion helpers `_normalized_to_execution_request()` and `_execution_result_to_order_result()`. |
| `engine/executor.py` | `cancel_order()` now delegates to `ExecutionManager.cancel_order()` with retry + audit. |
| `routes/v1_engine.py` | `POST /orders/{id}/cancel` now calls `ExecutionManager.cancel_order()` directly instead of `_get_engine()`. |
| `execution/manager.py` | `modify_order()` and `cancel_order()` now publish events. `sync_positions()` publishes `PositionUpdated`. Added `_empty_req()` helper. |

## Remaining Legacy Paths

**None.** All order placement (6 paths) converges through `gate.execute_order()` → `ExecutionManager.place_order()`. All cancellation (3 paths) converges through `ExecutionManager.cancel_order()`.

The following files authenticate with brokers but for **non-order purposes** (market data, token refresh, backtest):
- `market/data_socket.py` — market data feed auth
- `market/historical.py` — historical data fetch
- `market/adapter.py` — market data adapter
- `engine/backtest.py` — backtest data fetch
- `engine/token_refresh.py` — token refresh only

These are **not execution paths** and do not need migration.

## Manual Tests

| Test | Result |
|------|--------|
| All 16 existing tests pass | ✅ |
| All 54 routes import clean | ✅ |
| `ExecutionManager.place_order()` delegates to broker adapter | ✅ |
| `ExecutionManager.cancel_order()` publishes OrderCancelled event | ✅ |
| `ExecutionManager.modify_order()` publishes OrderModified event | ✅ |
| `ExecutionManager.sync_positions()` publishes PositionUpdated event | ✅ |
| `gate.execute_order()` backward-compatible wrapper works | ✅ |
| `executor.py` cancel delegates to ExecutionManager | ✅ |
| `v1_engine.py` cancel route delegates to ExecutionManager | ✅ |
| Event bus subscribe/publish cycle works | ✅ |
| Retry engine correctly classifies transient vs non-transient errors | ✅ |

## Breaking Changes

**0 — Zero breaking changes.**

All APIs preserved:
- `gate.execute_order(user_id, order, source)` — same signature, same return type
- `executor.execute_signal(signal)` — same signature, same return type
- `executor.cancel_order(order_id)` — same signature, same return type
- `v1_engine.py` POST /trade — same request/response format
- `v1_engine.py` POST /orders/{id}/cancel — same request/response format
- All existing routes unchanged
- All existing broker adapters unchanged
- No database schema changes
- No authentication changes
- No frontend changes

## Rollback Plan

```bash
cd /Users/aakib/trademetrix-terminal/apps/api
# Restore gate.py to direct broker adapter calls
git checkout engine/gate.py
# Restore executor.py to direct adapter calls
git checkout engine/executor.py
# Restore v1_engine.py to use _get_engine()
git checkout routes/v1_engine.py
# Restore execution/manager.py
git checkout execution/manager.py

# Verify
python3 -m pytest tests/ -q
```

## Technical Debt

1. **Dual audit logging** — `gate.py` still writes its own audit log (for backward compatibility). `ExecutionManager` also audits. These could be consolidated in a future cleanup.
2. **RiskGuard not in ExecutionManager** — Risk checks still happen in `gate.py` before calling the manager. Future work could move them into the validation pipeline.
3. **Paper mode in gate.py** — Paper trading (simulated fills) is handled in `gate.py` before reaching the manager. The manager only handles live broker execution.
