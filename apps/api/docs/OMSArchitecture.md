# OMS Architecture — Phase 8

## Overview

The Order Management System (OMS) owns the complete order lifecycle. ExecutionManager executes orders. OMS owns orders.

## Architecture

```
Client / Strategy / Runtime
        │
        ▼
  OrderManager
  ┌──────────────────────────────────────────┐
  │  place_order() → OmniOrder               │
  │  cancel_order() → OmniOrder              │
  │  create_bracket() → [OmniOrder]          │
  │  create_oco() → [OmniOrder]              │
  │  retry_order() → OmniOrder              │
  └────────────┬─────────────────────────────┘
               │
               ▼
        Order Queue (FIFO / Priority / Retry)
               │
               ▼
        State Machine
        NEW → VALIDATED → QUEUED → SENT →
        PENDING → PARTIAL → FILLED
                           → CANCELLED
                           → REJECTED
                           → EXPIRED
               │
               ▼
        ExecutionManager.place_order()
               │
               ▼
        RiskManager → BrokerAdapter / PaperBroker
```

## Components

### `oms/manager.py`
- `OrderManager` singleton
- `place_order(req)` — creates OmniOrder, enqueues, processes via queue → ExecutionManager
- `cancel_order(id)` — cancels via queue or directly via ExecutionManager
- `create_bracket(req, sl, target)` — creates entry + auto SL/TP
- `create_oco(req_a, req_b)` — creates two orders, one cancels the other
- `retry_order(id)` — re-enqueues with exponential backoff
- Background `_process_queue()` loop dequeues and delegates to ExecutionManager

### `oms/models.py`
- `OmniOrder` — full order with state, timestamps, relation links
- `OMSOrderState` — NEW, VALIDATED, QUEUED, SENT, PENDING, PARTIAL, FILLED, CANCELLED, REJECTED, EXPIRED
- `BracketOrder` — entry + SL + target tracking
- `OCOOrder` — two linked orders, one fill cancels the other
- `OrderQueueItem` — queue entry with priority and retry info

### `oms/state_machine.py`
- `OMSStateMachine` — validates all state transitions
- Terminal states: FILLED, CANCELLED, REJECTED, EXPIRED

### `oms/order_queue.py`
- `OrderQueue` — FIFO + priority heap + retry heap
- `enqueue(item)` — adds to FIFO and priority heap
- `enqueue_retry(item, delay)` — adds to retry heap with scheduled time
- `dequeue()` — returns highest-priority ready item (retry first, then priority)
- Thread-safe via `asyncio.Lock`

### `oms/observability.py`
- `OMSMetrics` — orders submitted/filled/cancelled/rejected/expired, queue depth, retries, fill latency, broker latency, bracket/oco counts

## State Machine

```
                    ┌──────────────────────────────────┐
                    │                                  │
       ┌───────┐    │     ┌──────────┐     ┌──────┐    │
       │  NEW  │────┼────▶│VALIDATED │────▶│QUEUED│    │
       └───┬───┘    │     └────┬─────┘     └──┬───┘    │
           │        │          │              │        │
           ▼        │          ▼              ▼        │
     ┌─────────┐    │   ┌────────────┐  ┌──────────┐   │
     │ REJECTED│    │   │   SENT     │  │CANCELLED │   │
     └─────────┘    │   └─────┬──────┘  └──────────┘   │
                    │         │                         │
                    │    ┌────┴──────┐                  │
                    │    │           │                  │
                    ▼    ▼           ▼                  │
             ┌────────────┐    ┌───────────┐            │
             │  PENDING   │    │  PARTIAL  │            │
             └──────┬─────┘    └─────┬─────┘            │
                    │                │                  │
                    ▼                ▼                  │
             ┌──────────┐    ┌───────────┐              │
             │  FILLED  │    │  EXPIRED  │              │
             └──────────┘    └───────────┘              │
                                                         │
                   ┌──────────┐                          │
                   │ REJECTED │◀─────────────────────────┘
                   └──────────┘
```

## Event Bus Events

| Event | Trigger |
|-------|---------|
| `OrderQueued` | Order added to queue |
| `OrderSent` | Order dequeued and sent to ExecutionManager |
| `OrderCompleted` | Order filled successfully |
| `OrderRejected` | Order rejected (terminal) |
| `OrderCancelled` | Order cancelled |
| `OrderExpired` | Order expired |

## OMS vs ExecutionManager

| Concern | Owner |
|---------|-------|
| Order tracking | OMS |
| Order lifecycle state | OMS |
| Queue management | OMS |
| Parent/child (bracket, OCO) | OMS |
| Broker execution | ExecutionManager |
| Risk evaluation | RiskManager |
| Broker adapter connection | ExecutionManager |

## Files

```
apps/api/oms/
├── __init__.py              # Public API exports
├── models.py                # OmniOrder, BracketOrder, OCOOrder, queue models
├── manager.py               # OrderManager singleton
├── state_machine.py         # State machine with transition validation
├── order_queue.py           # FIFO/Priority/Retry queues
└── observability.py         # OMS metrics

apps/api/docs/OMSArchitecture.md
```

## Rollback

```bash
rm -rf apps/api/oms/
rm apps/api/docs/OMSArchitecture.md
# No existing files modified
```
