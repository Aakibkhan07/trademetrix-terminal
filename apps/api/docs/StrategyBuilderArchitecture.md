# Strategy Builder Architecture (Phase 10)

## Overview

The Visual Strategy Builder provides a professional drag-and-drop strategy development environment. It produces a **Strategy DSL** that compiles into an **Execution Graph** executable by the `GraphStrategy` runtime — reusing the entire existing trading pipeline.

## Architecture

```
Visual Builder (canvas UI)
       │
       ▼
   Strategy DSL (JSON)
    ├── version: "1.0"
    ├── nodes: [{ block_type, params, position }]
    ├── edges: [{ source, target, ports }]
    └── settings: { symbol, interval, trigger }
       │
       ▼
   Compiler
    ├── Topological Sort
    ├── Cycle Detection
    ├── Type Checking
    └── Missing Input Validation
       │
       ▼
   Execution Graph
    ├── Ordered node list
    ├── Entry / exit points
    ├── Estimated latency
    └── Max depth
       │
       ▼
   GraphStrategy (BaseStrategy)
    ├── on_start() → reset memory
    ├── on_candle() → execute graph nodes in order
    │   ├── source.candle → extract OHLCV
    │   ├── indicator.ema → compute EMA
    │   ├── logic.gt → compare values
    │   ├── signal.cross_above → detect cross
    │   └── order.buy → generate SignalResult
    └── on_stop() → cleanup
       │
       ▼
   RuntimeManager.evaluate()
       │
       ▼
   ExecutionManager.place_order()  ◄── REUSED
       │
       ▼
   RiskManager → PaperBroker → PortfolioManager  ◄── REUSED
```

## Key Design Decisions

### 1. DSL is the Source of Truth
- Human-readable JSON, versioned (`"1.0"`)
- Serializable — import/export as JSON or `.dsl` text format
- Version-tracked per strategy (draft → published → archived)
- Clone and rollback supported

### 2. Compiler Produces Execution Graph
- Directed Acyclic Graph (DAG) — cycles detected and rejected
- Topological sort determines execution order
- Each node carries: `id`, `block_type`, `inputs` (ordered upstream IDs), `params`, `estimated_latency_us`
- Output: flat ordered list + entry/exit points + depth/latency metadata

### 3. GraphStrategy is a BaseStrategy
- Implements the same `on_candle()` interface as all existing strategies
- Registered with the strategy registry as `"graph_strategy"`
- Receives the compiled graph via `config["_dsl"]`
- Per-candle: executes nodes in topological order, resolves inputs from upstream results
- Series accumulated per run (OHLCV buffers up to 500 bars)

### 4. Zero Changes to Existing Code
- `engine/backtest.py` — untouched
- `runtime/manager.py` — untouched
- `execution/manager.py` — untouched
- `risk/manager.py` — untouched
- `oms/manager.py` — untouched
- `strategies/base.py` — untouched
- `strategies/__init__.py` — untouched (registration is additive via `register_strategy()`)

## Block Library

### Block Categories

| Category | Count | Examples |
|----------|-------|---------|
| `input` | 6 | Candle, Tick, Price History, Position, Portfolio, Market Time |
| `indicator` | 18 | SMA, EMA, RSI, MACD, Bollinger, VWAP, ATR, SuperTrend, Stoch, ADX, Ichimoku, PSAR, Heikin Ashi, Pivot, Linear Reg, Z-Score, Kalman |
| `pattern` | 15 | Bullish, Bearish, Doji, Hammer, Shooting Star, Engulfing, Morning/Evening Star, Pin Bar, Inside/Outside Bar, Range, Body, Wick |
| `math` | 20 | Add, Sub, Mul, Div, Min, Max, Avg, Abs, Round, Sqrt, Pct Change, Scale, Sum, Highest, Lowest, Sign, Pow, Log, Mod, Clamp |
| `logic` | 13 | AND, OR, NOT, GT, LT, GTE, LTE, EQ, NEQ, If/Else, Switch |
| `smc` | 8 | Order Block, Liquidity Grab, Fair Value Gap, Breaker Block, MSS, BOS, Discount/Premium |
| `ict` | 6 | ICT FVG, Order Block, Liquidity, Killzone, Silver Bullet, OTE |
| `greek` | 6 | Delta, Gamma, Theta, Vega, IV, Premium |
| `oi` | 4 | OI Change, OI Trend, PCR, COI |
| `signal` | 5 | Cross Above, Cross Below, Threshold, Breakout, Divergence, Confirmation |
| `order` | 7 | BUY, SELL, EXIT, REVERSE, Stop Loss, Take Profit, Trailing SL |
| `portfolio` | 4 | Position Size, Open Positions, Position PnL, Daily PnL |
| `risk` | 3 | Drawdown Check, Max Loss Check, Max Trades Check |
| `time` | 7 | Market Hour, Market Session, Day of Week, Time Range, Bar Index, Bars Since, Days to Expiry |
| `variable` | 5 | Number Constant, String Constant, Boolean Constant, Set Variable, Get Variable |
| `group` | 1 | Nested Group |

**Total: ~130+ block types across 16 categories**

### Block Definition Schema
```python
BlockDef {
    type: str              # "indicator.ema"
    name: str              # "EMA"
    category: BlockCategory # INDICATOR
    description: str
    inputs: [PortDef]      # data flow inputs
    outputs: [PortDef]     # data flow outputs
    params: [ParamDef]     # configuration parameters
}
```

## Template Library (10 templates)

| Template | Description | Blocks |
|----------|-------------|--------|
| EMA Crossover | Fast/slow EMA crossover | 8 blocks |
| ORB | Opening Range Breakout | 5 blocks |
| VWAP Mean Reversion | VWAP deviation mean reversion | 6 blocks |
| RSI Mean Reversion | RSI oversold/overbought | 5 blocks |
| Bollinger Bandit | Bollinger Band bounce mean reversion | 7 blocks |
| SMC Order Block | Order block + liquidity grab | 5 blocks |
| MACD Cross | MACD line/signal crossover | 7 blocks |
| Scalping | Fast EMA scalping on 1min | 10 blocks |
| ICT Silver Bullet | ICT 10-11am NY window | 8 blocks |
| Expiry Hunter | Expiry day short strangle | 8 blocks |

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/builder/blocks` | List all block types |
| GET | `/builder/blocks/categories` | List block categories |
| GET | `/builder/blocks/{type}` | Get specific block definition |
| POST | `/builder/strategies` | Create new strategy (optional template) |
| GET | `/builder/strategies` | List strategies (filter by status) |
| GET | `/builder/strategies/{id}` | Get strategy DSL |
| PUT | `/builder/strategies/{id}` | Update strategy (nodes, edges, settings) |
| DELETE | `/builder/strategies/{id}` | Delete strategy |
| POST | `/builder/strategies/{id}/compile` | Compile DSL → Execution Graph |
| POST | `/builder/strategies/{id}/validate` | Validate DSL |
| GET | `/builder/strategies/{id}/preview` | Preview execution order/latency |
| POST | `/builder/strategies/{id}/publish` | Publish strategy |
| POST | `/builder/strategies/{id}/archive` | Archive strategy |
| POST | `/builder/strategies/{id}/clone` | Clone strategy |
| POST | `/builder/strategies/{id}/rollback/{v}` | Rollback to version |
| GET | `/builder/strategies/{id}/versions` | List versions |
| GET | `/builder/templates` | List templates |
| GET | `/builder/templates/{key}` | Get template DSL |
| POST | `/builder/import` | Import strategy JSON |
| GET | `/builder/strategies/{id}/export` | Export strategy (json/dsl) |

## Abacus

### Files Created (11 files)

| File | Lines | Purpose |
|------|-------|---------|
| `builder/__init__.py` | ~40 | Package exports, registers GraphStrategy |
| `builder/models.py` | ~180 | All data models (DSL, graph, blocks, validation) |
| `builder/blocks.py` | ~600 | Block registry with 130+ block definitions |
| `builder/compiler.py` | ~220 | DSL → ExecutionGraph with topological sort |
| `builder/validation.py` | (inlined in compiler) | Cycle detection, type checking, validation |
| `builder/strategy.py` | ~380 | GraphStrategy runtime — executes graph per candle |
| `builder/manager.py` | ~200 | CRUD, versioning, clone, rollback, templates |
| `builder/templates.py` | ~200 | 10 pre-built strategy templates |
| `builder/io.py` | ~100 | JSON/DSL import/export |
| `builder/preview.py` | ~100 | Execution order, latency, warnings |
| `routes/v1_builder.py` | ~240 | All API endpoints |

### Files Modified (0)

No existing files were modified. The `register_strategy("graph_strategy", GraphStrategy)` call in `builder/__init__.py` is additive — it calls the existing `register_strategy()` function without touching `strategies/__init__.py`.

### Breaking Changes: 0

- `engine/backtest.py` — unchanged
- `runtime/` — unchanged  
- `execution/` — unchanged
- `risk/` — unchanged
- `oms/` — unchanged
- `strategies/` — unchanged
- `routes/` — only new file `v1_builder.py` added; existing `v1_backtest.py` untouched

## Remaining Work

- [ ] Frontend canvas UI (React Flow / similar)
- [ ] Live strategy execution monitoring
- [ ] Supabase persistence layer (currently in-memory)
- [ ] Performance benchmarks for complex graphs
- [ ] Additional compute functions for SMC/ICT blocks
