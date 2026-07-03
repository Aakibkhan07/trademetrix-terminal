# Portfolio Engine Architecture — Phase 5.5

## Overview

The Portfolio Engine is the single source of truth for positions, holdings, funds, margin, and PnL across all brokers. It continuously maintains synchronized account state via periodic broker reconciliation and event-driven updates.

## Architecture

```
ExecutionManager            PortfolioManager            BrokerAdapter
     │                            │                         │
     │── OrderPlaced ────────────▶│                         │
     │                            │── refresh() ───────────▶│
     │                            │◀── positions ──────────│
     │                            │◀── holdings ───────────│
     │                            │◀── funds ──────────────│
     │                            │◀── orders ─────────────│
     │                            │                         │
     │                            │── compute_pnl()         │
     │                            │── reconcile()           │
     │                            │── publish events        │
     │◀── PortfolioUpdated ──────│                         │
```

## State Model

Each `(user_id, broker)` pair has a `PortfolioState` containing:

| Component | Type | Source |
|-----------|------|--------|
| Positions | `dict[str, PortfolioPosition]` | Broker `get_positions()` |
| Holdings  | `dict[str, PortfolioHolding]` | Broker `get_holdings()` |
| Funds     | `PortfolioFunds` | Broker `get_funds()` |
| PnL       | `PortfolioPnL` | Computed from positions + today's fills |
| Orders    | `list[dict]` | Broker `get_orders()` |
| SyncStatus | `BrokerSyncStatus` | Per-sync tracking |
| Reconciliation | `ReconciliationResult` | Broker vs DB comparison |

## Components

### `portfolio/models.py`
- `PortfolioPosition` — Single position with qty, avg price, PnL
- `PortfolioHolding` — Holding with T1 quantity, PnL
- `PortfolioFunds` — Margin breakdown (total/used/available)
- `PortfolioPnL` — Realised, unrealised, daily, weekly, monthly, drawdown
- `PortfolioState` — Aggregated per-user/broker state
- `PortfolioSummary` — Cross-broker summary
- `BrokerSyncStatus` — Last sync timestamps per data type
- `ReconciliationResult` — Drift detection details
- `SyncStatus` — SYNCED / PENDING / FAILED / DRIFTED

### `portfolio/manager.py`
- `PortfolioManager` singleton (same pattern as `ExecutionManager`, `RiskManager`)
- `refresh(user_id, broker)` — Full sync from broker (positions, holdings, funds, orders)
- `get_positions()` / `get_holdings()` / `get_margin()` / `get_portfolio()` / `get_pnl()` — Read APIs
- `get_summary(user_id)` — Cross-broker aggregation
- `reconcile(user_id, broker)` — Detect ghost positions, missing orders, quantity drift
- `validate_risk_exposure()` — Exposure calculation for risk engine
- Invalidates cache on events

### `portfolio/observability.py`
- `PortfolioMetrics` singleton tracks: sync count, failures, reconciliation drifts, latencies
- Per-broker sync counts

### `portfolio/event_subscriber.py`
- Listens to `OrderPlaced`, `OrderFilled`, `OrderCancelled`, `OrderRejected`
- Triggers `portfolio_manager.refresh()` or `invalidate_cache()` accordingly

## Events Published

| Event | Trigger |
|-------|---------|
| `PortfolioUpdated` | After full refresh completes |
| `PositionOpened` | New non-zero position appears |
| `PositionClosed` | Position quantity becomes zero |
| `PositionUpdated` | Position quantity changes |
| `HoldingUpdated` | Holdings refreshed |
| `MarginUpdated` | Funds refreshed |
| `PnLUpdated` | PnL recomputed |

## Reconciliation

Detects:
- **Missing Orders** — Symbols in local DB but not in broker response
- **Ghost Positions** — Symbols in broker response but not in local DB
- **Duplicate Positions** — Multiple entries for same symbol
- **Out-of-sync quantities** — Quantity mismatch between broker and DB

Drift detection sets `SyncStatus.DRIFTED` and logs details.

## Integration Points

| Layer | Integration |
|-------|-------------|
| `execution/manager.py` | Calls `portfolio_manager.refresh()` after `OrderPlaced` |
| `execution/event_bus.py` | PortfolioEventSubscriber listens for order events |
| Portfolio risk rules | Can use `portfolio_manager.validate_risk_exposure()` |

## Public API

```python
await portfolio_manager.get_positions(user_id, broker)    # → list[PortfolioPosition]
await portfolio_manager.get_holdings(user_id, broker)     # → list[PortfolioHolding]
await portfolio_manager.get_margin(user_id, broker)       # → PortfolioFunds
await portfolio_manager.get_portfolio(user_id, broker)    # → PortfolioState
await portfolio_manager.get_pnl(user_id, broker)          # → PortfolioPnL
await portfolio_manager.get_summary(user_id)              # → PortfolioSummary
await portfolio_manager.refresh(user_id, broker)           # → PortfolioState
await portfolio_manager.reconcile(user_id, broker)         # → ReconciliationResult
```

## Files

```
apps/api/portfolio/
├── __init__.py              # Public API exports
├── models.py                # Portfolio models
├── manager.py               # PortfolioManager singleton
├── observability.py         # Portfolio metrics
└── event_subscriber.py      # Event bus subscription

apps/api/docs/PortfolioArchitecture.md
```

## Rollback Strategy

```bash
cd /Users/aakib/trademetrix-terminal
# Remove portfolio layer
rm -rf apps/api/portfolio/
rm apps/api/docs/PortfolioArchitecture.md
# Revert execution/manager.py change
git checkout apps/api/execution/manager.py
# Verify existing routes still work
python3 -m pytest tests/ -q
```
