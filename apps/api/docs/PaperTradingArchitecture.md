# Paper Trading Engine Architecture — Phase 7

## Overview

The Paper Trading Engine makes paper trades behave exactly like live trades. The ONLY difference is the execution destination: PaperBroker replaces the real broker adapter. All other logic — Strategy Runtime, Portfolio Engine, Risk Engine, ExecutionManager — runs identically.

## Architecture

```
                    ┌─────────────┐
                    │  Strategy   │
                    │  Runtime    │
                    └──────┬──────┘
                           │ Signal
                    ┌──────▼──────┐
                    │ Portfolio   │
                    │ Engine      │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │    Risk     │
                    │   Engine    │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ Execution   │
                    │  Manager    │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │                         │
       ┌──────▼──────┐          ┌──────▼──────┐
       │    Live     │          │    Paper    │
       │    Broker   │          │   Broker    │
       └─────────────┘          └──────┬──────┘
                                       │
                                ┌──────▼──────┐
                                │ Fill Engine │
                                │  Simulator  │
                                └─────────────┘
```

## Key Design Decision

The paper/live routing is handled inside `ExecutionManager._get_adapter()`:
- If `broker == "paper"` → return `PaperBroker` instance
- Otherwise → return `BrokerExecutionAdapter` instance

This means **zero changes** to the `place_order()` pipeline. Validation, risk evaluation, event publishing, audit logging — all run identically for paper and live trades.

## Components

### `paper/paper_broker.py`
- `PaperBroker` implements the exact same interface as `BrokerExecutionAdapter`
- Methods: `connect()`, `disconnect()`, `health()`, `capabilities()`, `place_order()`, `modify_order()`, `cancel_order()`, `get_order()`, `get_orders()`, `get_positions()`, `get_holdings()`, `get_funds()`, `validate_order()`
- Maintains in-memory: orders dict, positions dict, account state
- Delegates fill simulation to `FillEngine`
- Publishes events: `PaperOrderFilled`, `PaperOrderPending`, `PaperPositionUpdated`

### `paper/fill_engine.py`
- `FillEngine` simulates order fills
- Fill types: INSTANT, NEXT_TICK, PRICE_BASED, VOLUME_BASED
- Handles: market orders, limit orders, stop-loss orders
- Configurable: slippage, commission, exchange charges, STT, stamp duty
- Partial fill simulation with configurable probability

### `paper/models.py`
- `PaperConfig` — initial capital, broker delay, slippage, commissions, fill type
- `PaperAccount` — margin tracking (total, used, available, current value)
- `PaperPosition` — per-symbol position with PnL tracking
- `PaperFill` — individual fill record with charges breakdown
- `PaperOrderStatus` — PENDING, PARTIALLY_FILLED, FILLED, REJECTED, CANCELLED
- `FillType` — INSTANT, NEXT_TICK, PRICE_BASED, VOLUME_BASED

### `paper/observability.py`
- `PaperMetrics` — tracks orders, fills, rejects, cancellations, PnL, latency, errors

## Integration Points

| Layer | Integration |
|-------|-------------|
| `execution/manager.py:_get_adapter()` | Routes `broker="paper"` to `PaperBroker` |
| `engine/gate.py:execute_order()` | Sets `order.broker = "paper"` for non-live trades, passes through `ExecutionManager` |
| `execution/event_bus.py` | PaperBroker publishes `PaperOrderFilled`, `PaperOrderPending`, `PaperPositionUpdated` |

## Configuration

Paper trading config per user:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `initial_capital` | 500,000 | Starting capital |
| `broker_delay_ms` | 50 | Simulated broker latency |
| `slippage_pct` | 0.01 | Price slippage per order |
| `commission_pct` | 0.0 | Brokerage commission |
| `exchange_charges_pct` | 0.0 | Exchange transaction charges |
| `stt_pct` | 0.0 | Securities transaction tax |
| `fill_type` | INSTANT | Fill simulation method |

## Files

```
apps/api/paper/
├── __init__.py              # Public API exports
├── models.py                # PaperConfig, PaperAccount, PaperPosition, PaperFill
├── paper_broker.py          # PaperBroker (same interface as BrokerExecutionAdapter)
├── fill_engine.py           # Fill simulation engine
└── observability.py         # Paper trading metrics

apps/api/docs/PaperTradingArchitecture.md
```

## Rollback Strategy

```bash
cd /Users/aakib/trademetrix-terminal
rm -rf apps/api/paper/
rm apps/api/docs/PaperTradingArchitecture.md
git checkout apps/api/execution/manager.py apps/api/engine/gate.py
```

## Key Decisions

1. **PaperBroker implements BrokerExecutionAdapter interface** — no new interface, no adapter pattern
2. **Paper routing inside `_get_adapter()`** — single decision point, zero pipeline changes
3. **No duplicate execution logic** — all orders flow through the same `place_order()` pipeline
4. **In-memory state** — no DB schema changes; positions/orders tracked in PaperBroker instance
5. **Configurable fill engine** — supports realistic simulation with slippage, partial fills, charges
6. **Existing `gate.py` simplified** — removed `_paper_execute()`; non-live orders set `broker="paper"` and flow through ExecutionManager
