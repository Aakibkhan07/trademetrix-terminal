# Backtesting Architecture (Phase 9)

## Overview

The Phase 9 backtesting engine **reuses the existing live trading architecture** instead of building a separate simulation pipeline. The same components that execute live trades (ExecutionManager, PaperBroker, PortfolioManager, RiskManager) are driven by historical data replay.

## Key Design Principle

> **Only the data source changes — the execution pipeline stays the same.**

| Component | Live Trading | Backtesting |
|-----------|-------------|-------------|
| Data Source | WebSocket / live feed | Historical replay (CSV, DB, broker API) |
| Execution | BrokerAdapter (real broker) | PaperBroker (simulated fills) |
| Risk Checks | Live risk rules | Same rules (configurable) |
| Portfolio Tracking | PortfolioManager | Same PortfolioManager |
| Strategy Pipeline | Strategy.on_candle() | Same Strategy.on_candle() |
| Order Flow | RT → OMS → ExecMgr → Broker | ReplayEngine → ExecMgr → PaperBroker |

## Architecture Flow

```
                    ┌──────────────────────────────────────┐
                    │          BacktestManager              │
                    │   (orchestrator, collects results)    │
                    └────┬───────────────────────────┬──────┘
                         │                           │
               ┌─────────▼──────────┐    ┌──────────▼───────────┐
               │   BacktestDataLoader│    │  PerformanceAnalytics│
               │   (CSV/JSON/Parquet │    │  (metrics, ratios,   │
               │    /HistoricalEngine)│    │   equity curve)      │
               └─────────┬──────────┘    └──────────────────────┘
                         │
               ┌─────────▼──────────┐
               │    ReplayEngine     │
               │  (pause/resume/     │
               │   seek/speed ctrl)  │
               └─────────┬──────────┘
                         │
              ┌──────────▼───────────┐
              │   Strategy.on_candle()│
              │   (returns SignalResult│
              │    with NormalizedOrder)│
              └──────────┬───────────┘
                         │
              ┌──────────▼───────────┐
              │   ExecutionManager    │  ◄── REUSED from live
              │   .place_order()      │
              └──────────┬───────────┘
                         │
                    ┌────▼────┐
                    │RiskMgr  │  ◄── REUSED (configurable)
                    └────┬────┘
                         │
              ┌──────────▼───────────┐
              │    PaperBroker        │  ◄── REUSED (simulated fills)
              │   .place_order()      │
              └──────────┬───────────┘
                         │
              ┌──────────▼───────────┐
              │  PortfolioManager     │  ◄── REUSED (positions, PnL)
              │   .refresh()          │
              └──────────┬───────────┘
                         │
              ┌──────────▼───────────┐
              │   PerformanceAnalytics│
              │   .calculate()        │
              └──────────────────────┘
```

## Components

### 1. `backtest/models.py` — Data Models

| Model | Purpose |
|-------|---------|
| `BacktestConfig` | Input config: strategy, symbol, interval, capital, speed |
| `BacktestStatus` | IDLE, RUNNING, PAUSED, COMPLETED, FAILED, CANCELLED |
| `ReplaySpeed` | 1x, 2x, 5x, 10x, 100x, MAX (no delay) |
| `TradeRecord` | Individual trade with entry/exit/pnl |
| `EquityPoint` | Equity curve data point with drawdown |
| `BacktestResult` | Full results: stats, trades, equity curve, ratios |

### 2. `backtest/data_loader.py` — Data Loading

- `BacktestDataLoader` (singleton via `backtest_data_loader`)
- Supports CSV, JSON, Parquet, and auto (uses `HistoricalDataEngine` for broker data)
- Caches loaded data by key
- Converts raw dicts to `Candle` models via `to_candle()`

### 3. `backtest/replay_engine.py` — Candle Replay

- `ReplayEngine` (singleton via `replay_engine`)
- Iterates through candles at configurable speed
- Supports `pause()`, `resume()`, `stop()`, `seek()`
- Converts `NormalizedOrder` to `ExecutionRequest` for the execution pipeline
- Collects portfolio snapshots after each candle

### 4. `backtest/performance.py` — Performance Analytics

- `PerformanceAnalytics` (singleton via `performance_analytics`)
- Computes from snapshots and trade records:
  - Trade statistics (win rate, avg win/loss, streaks)
  - Equity curve and drawdown
  - Sharpe, Sortino, Calmar ratios
  - Monthly and daily returns
  - Profit factor, return %

### 5. `backtest/manager.py` — Orchestrator

- `BacktestManager` (singleton via `backtest_manager`)
- Creates a unique backtest user (`backtest:{run_id}`)
- Configures PaperBroker with backtest capital
- Injects PaperBroker into ExecutionManager's adapter cache
- Creates strategy instance and runs replay
- Closes open positions on completion
- Cleans up cached adapters and portfolio state
- Returns `BacktestResult` with full analytics

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/backtest/run` | **Legacy** — uses old BacktestEngine (kept for compat) |
| POST | `/backtest/run-v2` | **New** — uses BacktestManager with full pipeline reuse |
| GET | `/backtest/v2/status` | Current backtest status and progress |
| POST | `/backtest/v2/pause` | Pause running backtest |
| POST | `/backtest/v2/resume` | Resume paused backtest |
| POST | `/backtest/v2/stop` | Cancel running backtest |
| GET | `/backtest/strategies` | List available strategies |

## Backtest Lifecycle

```
IDLE → RUNNING → PAUSED → RUNNING → COMPLETED
                        ↘ CANCELLED
                   RUNNING → FAILED
                   RUNNING → CANCELLED
```

## What's Reused vs New

### Reused from Live Architecture
- `ExecutionManager.place_order()` — full order pipeline
- `PaperBroker.place_order()` — simulated fills, position tracking, margin checks
- `PortfolioManager` — position tracking, PnL computation, reconciliation
- `RiskManager.evaluate()` — configurable risk rules
- `Strategy.on_candle()` — strategy logic (unchanged)
- `ExecutionEventBus` — event publishing

### New Components
- `BacktestManager` — orchestrator
- `DataLoader` — historical data loading with caching
- `ReplayEngine` — speed-controlled candle iteration
- `PerformanceAnalytics` — metrics computation

## Key Design Decisions

1. **Each backtest run gets a unique user_id** (`backtest:{run_id}`) to isolate state from live paper trading
2. **PaperBroker is pre-configured** with the backtest capital before any orders flow through
3. **MAX speed** iterates candles without `asyncio.sleep()`, yielding every 100 candles
4. **Lower speeds** use `sleep(interval * candle_duration / multiplier)` for realistic time progression
5. **Risk rules apply** by default (configurable via `risk_enabled`) — same as live trading
6. **Remaining positions are squared off** at the end (configurable via `close_positions_on_end`)
7. **Legacy BacktestEngine** (`engine/backtest.py`) is kept unchanged for backward compatibility

## Performance Considerations

- MAX speed processes candles as fast as `asyncio` allows
- State snapshots are collected after every candle — for large datasets, consider downsampling
- PaperBroker operations are in-memory (no DB writes during replay)
- Event bus events are fire-and-forget (non-blocking)
