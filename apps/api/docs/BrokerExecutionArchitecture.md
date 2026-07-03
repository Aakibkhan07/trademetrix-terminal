# Broker Execution Architecture — Phase 4

## Overview

The Broker Execution Layer is the **single unified path** for all order operations. No code outside this layer may directly call a broker adapter for order placement. All orders pass through `ExecutionManager` which handles validation, idempotency, state transitions, retry, audit logging, and observability.

## Architecture

```
Client / Strategy / Webhook
          │
          ▼
  ┌──────────────────┐
  │  ExecutionManager │  ← singleton, central orchestrator
  └──────┬───────────┘
         │
    ┌────┴───────────────┐
    │                    │
    ▼                    ▼
  ┌──────────┐    ┌──────────────┐
  │ Validation │    │  RiskGuard   │
  └─────┬─────┘    └──────┬───────┘
        │                  │
        └──────┬───────────┘
               ▼
       ┌──────────────┐
       │  Event Bus   │  ← async publish
       └──────┬───────┘
              │
              ▼
       ┌──────────────────┐
       │ BrokerExecAdapter│  ← wraps existing BaseBroker
       └──────┬───────────┘
              │
              ▼
       ┌──────────────────┐
       │ BaseBroker (10)  │  ← Fyers, Dhan, Zerodha, etc.
       └──────────────────┘
```

## Sequence Diagram

```
Client              ExecutionManager        Validation         BrokerAdapter        BaseBroker
  │                       │                     │                    │                 │
  │── place_order() ─────▶│                     │                    │                 │
  │                       │── validate() ──────▶│                    │                 │
  │                       │◀──── valid ────────│                    │                 │
  │                       │                     │                    │                 │
  │                       │── check_risk() ────▶│                    │                 │
  │                       │◀─── allowed ───────│                    │                 │
  │                       │                     │                    │                 │
  │                       │── log_order() ─────▶│                    │                 │
  │                       │── publish(Validated)│                    │                 │
  │                       │                     │                    │                 │
  │                       │── connect() ────────────────────────────▶│                 │
  │                       │                     │                    │── auth() ──────▶│
  │                       │                     │                    │◀── session ────│
  │                       │── execute() ────────────────────────────▶│                 │
  │                       │ (with retry)        │                    │── place() ─────▶│
  │                       │                     │                    │◀── result ─────│
  │                       │                     │                    │                 │
  │                       │── publish(Placed)   │                    │                 │
  │                       │── audit_log()       │                    │                 │
  │                       │── update_DB()       │                    │                 │
  │◀── ExecutionResult ───│                     │                    │                 │
```

## State Machine

```
                  ┌──────────────────────────────────────┐
                  │                                      │
     ┌───────┐    │     ┌──────────┐     ┌──────┐        │
     │  NEW  │────┼────▶│VALIDATED │────▶│ SENT │        │
     └───┬───┘    │     └────┬─────┘     └──┬───┘        │
         │        │          │              │            │
         ▼        │          ▼              ▼            │
   ┌─────────┐    │   ┌────────────┐  ┌──────────┐      │
   │ REJECTED│    │   │  PENDING   │  │  FAILED  │      │
   └─────────┘    │   └─────┬──────┘  └──────────┘      │
                  │         │                            │
                  │    ┌────┴──────┐                     │
                  │    │           │                     │
                  ▼    ▼           ▼                     │
           ┌────────────┐    ┌───────────┐               │
           │PARTIALLY_   │    │  FILLED   │              │
           │  FILLED     │    └───────────┘              │
           └──────┬─────┘                                │
                  │                                      │
                  ▼                                      │
           ┌──────────┐                                  │
           │CANCELLED │                                  │
           └──────────┘                                  │
                  │                                      │
                  ▼                                      │
           ┌──────────┐                                  │
           │ EXPIRED  │                                  │
           └──────────┘                                  │
                                                         │
                  ┌──────────┐                            │
                  │ FAILED   │◀───────────────────────────┘
                  └──────────┘
```

### State Transition Rules

| Current State | Allowed Next States |
|---------------|-------------------|
| NEW | VALIDATED, REJECTED, FAILED |
| VALIDATED | SENT, REJECTED, FAILED |
| SENT | PENDING, PARTIALLY_FILLED, FILLED, REJECTED, FAILED |
| PENDING | PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED, EXPIRED |
| PARTIALLY_FILLED | PENDING, FILLED, CANCELLED, REJECTED |
| FILLED | *(terminal)* |
| REJECTED | *(terminal)* |
| CANCELLED | *(terminal)* |
| FAILED | *(terminal)* |
| EXPIRED | *(terminal)* |

## Broker Execution Adapter Design

Each broker is wrapped by `BrokerExecutionAdapter` which provides a uniform interface:

```python
class BrokerExecutionAdapter:
    async def connect() -> bool
    async def disconnect()
    async def health() -> dict
    def capabilities() -> BrokerCapabilities
    async def place_order(order) -> OrderResult
    async def modify_order(id, changes) -> OrderResult
    async def cancel_order(id) -> OrderResult
    async def get_order(id) -> NormalizedOrder | None
    async def get_orders() -> list[NormalizedOrder]
    async def get_positions() -> list[Position]
    async def get_holdings() -> list[Holding]
    async def get_funds() -> Funds
    async def validate_order(order) -> dict
```

The adapter delegates to the existing `BaseBroker` implementation. No existing broker code is modified.

## Capability Registry

Each broker exposes its capabilities:

```python
BrokerCapabilities(
    supports_orders=True,
    supports_modify=True,
    supports_cancel=True,
    supports_bracket=False,   # Only Fyers, Zerodha, Angel, Upstox, Kotak
    supports_cover=False,     # Only Zerodha, Angel, Upstox
    supports_gtt=False,       # Only Dhan, Zerodha, Angel, Upstox, Kotak
    supports_websocket=True,
    supports_option_chain=False,
    supports_positions=True,
    supports_holdings=True,
)
```

## Retry Logic

- **Transient errors** (TIMEOUT, NETWORK_ERROR, TOKEN_EXPIRED, RATE_LIMITED): Retry with exponential backoff (1s, 2s, 4s, 8s, max 30s), up to 3 attempts.
- **Non-transient errors** (INVALID_SYMBOL, VALIDATION_FAILED, ORDER_REJECTED, USER_CANCELLED, MARGIN_INSUFFICIENT): Never retry.
- Configured via `execution/retry.py` constants: `MAX_RETRIES=3`, `BASE_DELAY=1.0`, `MAX_DELAY=30.0`.

## Audit Flow

Every execution event is logged to the `audit_log` Supabase table with:

| Field | Description |
|-------|-------------|
| `user_id` | Who placed the order |
| `broker` | Which broker |
| `action` | placed / modified / cancelled / failed / validation_failed |
| `execution_request_id` | Unique request identifier |
| `broker_order_id` | Broker-assigned order ID |
| `symbol`, `side`, `quantity`, `price` | Order details |
| `latency_ms` | End-to-end latency |
| `status` | filled / rejected / failed |
| `message` | Human-readable result |
| `payload_hash` | SHA256 of request payload (16 chars) |
| `result` | JSON-encoded broker response |

## Idempotency

- Every request generates an `execution_request_id` (SHA256 hash of `user_id:broker:symbol:side:timestamp`, truncated to 16 chars).
- Before placing an order, the manager checks if a request with the same `execution_request_id` already exists in the DB.
- Duplicate requests return the existing order result without contacting the broker.
- Counter `duplicate_requests_prevented` is incremented in metrics.

## File Structure

```
apps/api/execution/
├── __init__.py          # Public API, singleton exports
├── models.py            # Core types: ExecutionState, ExecutionRequest, ExecutionResult, BrokerCapabilities, etc.
├── broker_adapter.py    # BrokerExecutionAdapter wrapping existing adapters + capability registry
├── validation.py        # Order validation (fields, session, duplicate, margin)
├── event_bus.py         # Async pub/sub execution event bus
├── audit.py             # Structured audit logging to Supabase
├── retry.py             # Exponential backoff retry engine
├── observability.py     # Metrics counters and latency tracking
└── manager.py           # Central ExecutionManager orchestrator
```

## Rollback Strategy

```bash
cd /Users/aakib/trademetrix-terminal
# Remove execution layer
rm -rf apps/api/execution/
# Remove docs
rm apps/api/docs/BrokerExecutionArchitecture.md

# Verify existing routes still work
python3 -m pytest tests/test_marketdata.py tests/test_backtest.py tests/test_gate.py -q

# No database changes → no DB rollback needed
# No route changes → no API consumers affected
# No config changes → no environment changes needed
```

## Key Decisions

1. **No modifications to existing brokers** — `BrokerExecutionAdapter` wraps, never modifies.
2. **No new routes** — The execution layer is a library, not a set of endpoints. Existing routes (`/engine/trade`, `/engine/orders/{id}/cancel`) continue to work.
3. **Singleton manager** — `execution_manager` is a module-level singleton like `shared_socket` and `market_cache`.
4. **Async event bus** — Decoupled pub/sub with `*` wildcard support. No external dependency.
5. **Supabase audit log** — Same `audit_log` table used by the existing codebase. No new tables.
6. **No database schema changes** — All data fits into existing `orders` and `audit_log` tables.
7. **Validation before broker contact** — All validation (fields, session, duplicate, margin) runs before any broker API call.
8. **Deterministic state machine** — Each state has a fixed set of allowed transitions. Terminal states (FILLED, REJECTED, CANCELLED, FAILED, EXPIRED) cannot transition.
