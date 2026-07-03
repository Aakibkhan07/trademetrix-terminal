# Strategy Runtime Engine Architecture — Phase 6

## Overview

The Strategy Runtime is the intelligence layer. It evaluates strategies continuously and produces trading signals. It NEVER places orders directly. Every signal passes through: Runtime → Portfolio Engine → Risk Engine → Execution Manager → Broker.

## Architecture

```
Market Data Feed (SharedDataSocket)
        │
        ▼
  RuntimeEventSubscriber
        │
        ▼
  RuntimeScheduler
    ├── EVERY_TICK → on_tick()
    ├── CANDLE_CLOSE → on_candle()
    ├── EVERY_MINUTE → minute loop
    ├── MARKET_OPEN → start strategies
    └── MARKET_CLOSE → stop strategies
        │
        ▼
  RuntimeManager.evaluate()
    ├── Load RuntimeContext
    │   ├── Tick / Candle
    │   ├── Indicators (market_cache)
    │   ├── Portfolio (portfolio_manager)
    │   └── Config / Variables
    │
    ├── Strategy Plugin Instance
    │   └── on_tick() / on_candle()
    │       └── Returns SignalResult
    │
    ├── Build RuntimeSignal
    │   └── SignalGenerated event
    │
    └── submit_signal()
        └── ExecutionRequest → ExecutionManager
```

## Components

### `runtime/models.py`
- `SignalSide` — BUY, SELL, EXIT, REVERSE, HOLD, IGNORE
- `StrategyState` — DRAFT → READY → RUNNING ↔ PAUSED → STOPPED → ARCHIVED
- `TriggerType` — EVERY_TICK, CANDLE_CLOSE, EVERY_MINUTE, EVERY_5_MINUTES, MARKET_OPEN, MARKET_CLOSE, CRON
- `RuntimeSignal` — Signal with strategy_id, signal_id, side, confidence, reason, order details
- `RuntimeConfig` — Per-strategy configuration
- `RuntimeMetrics` — Per-strategy evaluation statistics
- `StrategyPlugin` — Plugin metadata

### `runtime/manager.py`
- `RuntimeManager` singleton
- `register_strategy(config)` — Register a new strategy instance
- `start_strategy(id)` / `stop_strategy(id)` / `pause_strategy(id)` / `resume_strategy(id)` — Lifecycle
- `reload_strategy(id)` — Hot-reload strategy module
- `evaluate(id, tick, candle)` — Core evaluation pipeline
- `submit_signal(signal)` — Convert signal → ExecutionRequest → ExecutionManager

### `runtime/registry.py`
- `StrategyRegistry` singleton
- Auto-discovers strategies from `strategies/` directory
- `register()` / `unregister()` / `enable()` / `disable()` / `reload()` / `discover()`
- Plugin metadata management

### `runtime/context.py`
- `RuntimeContext` builds evaluation context per strategy
- Includes: tick data, candle data, indicator values (from market_cache), portfolio state (from portfolio_manager), trading session, strategy variables
- All data is read-only for strategy evaluation

### `runtime/expression.py`
- `Expr` abstract base with implementations: ValueExpr, VariableExpr, BinaryExpr, UnaryExpr, IfElseExpr, FunctionExpr, GroupExpr
- Operators: AND, OR, NOT, IF, ELSE, >, <, >=, <=, ==, !=, +, -, *, /, %, POW
- Built-in functions: abs, min, max, sum, round, sqrt, floor, ceil, crosses_above, crosses_below, between, percent_change
- `parse_expression(dict)` — Parse JSON expression definition

### `runtime/scheduler.py`
- `RuntimeScheduler` with trigger-based scheduling
- Supports: every tick, candle close, every minute, every 5 minutes, market open, market close, cron
- Registers/triggers callbacks based on strategy config

### `runtime/observability.py`
- `RuntimeMetrics` singleton
- Tracks: evaluation count, signals generated/rejected, errors, per-strategy latency, active strategies

### `runtime/event_subscriber.py`
- Subscribes to `SharedDataSocket` for tick events
- Forwards ticks to `RuntimeScheduler.on_tick()`

## Strategy Lifecycle

```
DRAFT ──→ READY ──→ RUNNING ──→ STOPPED ──→ ARCHIVED
           │          │  ↑          │
           │          ↓  │          │
           │        PAUSED          │
           │                       │
           └────────── FAILED ──────┘
```

## Signal Flow

```
Strategy Instance
    │
    ▼
SignalResult (orders + reason)
    │
    ▼
RuntimeSignal (signal_id, side, confidence, quantity, price, etc.)
    │
    ├── SignalGenerated event published
    │
    ▼
submit_signal() → ExecutionRequest
    │
    ▼
ExecutionManager.place_order()
    ├── RiskManager.evaluate()
    └── BrokerExecutionAdapter.place_order()
```

## Trigger Types

| Trigger | When | Use Case |
|---------|------|----------|
| EVERY_TICK | Every market data tick | VWAP, scalping |
| CANDLE_CLOSE | Each candle close | EMA/MACD crossover, pattern detection |
| EVERY_MINUTE | Once per minute | Position monitoring |
| EVERY_5_MINUTES | Every 5 minutes | Trend analysis |
| MARKET_OPEN | Once at market open | Gap/ORB strategies |
| MARKET_CLOSE | Once at market close | EOD square-off |
| CRON | Cron expression | Custom schedules |

## Plugin Architecture

Strategies auto-discover from `strategies/` directory. Each strategy module exports a class extending `BaseStrategy`:

```python
class MyStrategy(BaseStrategy):
    name = "my_strategy"
    description = "Description"

    async def on_tick(self, tick: Tick) -> SignalResult | None: ...
    async def on_candle(self, candle: Candle) -> SignalResult | None: ...
    async def on_start(self) -> None: ...
    async def on_stop(self) -> None: ...
```

Extension points for future: `indicators/`, `conditions/`, `operators/`, `functions/`.

## Files

```
apps/api/runtime/
├── __init__.py              # Public API exports
├── models.py                # Signal, context, state models
├── manager.py               # RuntimeManager singleton
├── registry.py              # Strategy Registry
├── context.py               # Runtime Context builder
├── expression.py            # Expression Engine
├── scheduler.py             # Runtime Scheduler
├── observability.py         # Runtime metrics
└── event_subscriber.py      # Market feed subscription

apps/api/docs/StrategyRuntimeArchitecture.md
```

## Future Builder Integration

The Runtime is designed to support a future Strategy Builder/Visual Editor:
- Expression engine parsed from JSON → UI can render condition trees
- StrategyPlugin config_schema → UI can generate parameter forms
- Strategy lifecycle → UI can show start/stop/pause controls
- Runtime metrics → UI dashboards

## Rollback Strategy

```bash
cd /Users/aakib/trademetrix-terminal
rm -rf apps/api/runtime/
rm apps/api/docs/StrategyRuntimeArchitecture.md
# No existing files modified — nothing to revert
```

## Key Decisions

1. **No direct order placement** — Runtime produces signals, never calls broker APIs
2. **Consumes only Event Bus events** — Subscribes to SharedDataSocket for ticks, never broker feeds directly
3. **Singleton manager** — Same pattern as ExecutionManager, RiskManager, PortfolioManager
4. **Plugin-based** — Auto-discovers strategies from `strategies/` directory
5. **No DB schema changes** — Tracks state in-memory, logs to events
6. **No existing code changes** — All additive
7. **Expression engine** — JSON-parsable expressions for future UI integration
8. **Existing BaseStrategy preserved** — New Runtime wraps existing strategy classes, does not modify them
