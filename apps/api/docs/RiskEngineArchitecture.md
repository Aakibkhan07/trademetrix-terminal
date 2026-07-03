# Risk Engine Architecture

## Overview

The Risk Engine is a mandatory approval layer between every execution request and every broker adapter. No order reaches a broker unless explicitly approved by the Risk Engine.

## Architecture

```
ExecutionRequest
    │
    ▼
ExecutionManager.place_order()
    │
    ├── 1. Duplicate check
    ├── 2. Order normalization
    ├── 3. Validation (order integrity)
    ├── 4. RiskManager.evaluate()  ←── NEW
    │       │
    │       ├── Load RiskConfig (cached per user)
    │       ├── Iterate all risk rules
    │       ├── Short-circuit on first REJECTED
    │       └── Publish RiskDecision event
    │
    ├── 5. Get broker adapter
    ├── 6. Execute with retry
    └── 7. Post-execution (audit, event)
```

## Three-Tier Decision Model

| Decision   | Meaning                                  | Proceeds to Broker? |
|------------|------------------------------------------|---------------------|
| APPROVED   | All rules passed                         | Yes                 |
| WARNING    | Non-fatal limit reached (e.g. profit target) | Configurable    |
| REJECTED   | Fatal limit breached                     | No                  |

## Rule Engine

Rules are pluggable classes in `risk/rules.py`. Each implements:

```python
class RiskRule(ABC):
    rule_type: RiskRuleType

    @abstractmethod
    async def evaluate(self, req: ExecutionRequest, config: RiskConfig) -> RiskRuleResult:
        ...
```

Rules are evaluated in order. First REJECTED short-circuits the pipeline.

### Active Rules (16)

1. **KillSwitchRule** — Global kill switch check from `risk_settings` table
2. **EmergencyStopRule** — In-memory emergency stop flag
3. **BrokerOfflineRule** — Per-broker block list
4. **MarketClosedRule** — Market status check via `market_status_service`
5. **TradingWindowRule** — Configurable trading hours (IST)
6. **DailyLossLimitRule** — Max daily loss from filled orders
7. **DailyProfitTargetRule** — Profit target reached (WARNING only)
8. **MaxTradesPerDayRule** — Max trades per day
9. **MaxOpenPositionsRule** — Max concurrent open positions
10. **MaxQuantityRule** — Max order quantity
11. **MaxExposureRule** — Max total portfolio exposure
12. **MaxSymbolExposureRule** — Max per-symbol exposure
13. **MaxCapitalRule** — Max capital usage
14. **MaxDrawdownRule** — Drawdown % from peak
15. **MaxOrdersPerMinuteRule** — Rate limiter (in-memory sliding window)
16. **DuplicateOrderRule** — Same user/broker/symbol/side/quantity dedup

## Components

### `risk/models.py`
- `RiskDecision` — APPROVED / WARNING / REJECTED
- `RiskRuleType` — Enum of all rule types
- `RiskRuleResult` — Per-rule evaluation result with latency
- `RiskEvalResult` — Aggregated evaluation result
- `RiskConfig` — Per-user config (loaded from `risk_settings` table)

### `risk/rules.py`
- 16 risk rule classes
- Each rule is self-contained with its own DB query logic

### `risk/manager.py`
- `RiskManager` singleton (same pattern as `ExecutionManager`)
- `evaluate(req)` — Main entry point called by `ExecutionManager`
- Caches `RiskConfig` per user_id
- Publishes events to `ExecutionEventBus` for every decision

### `risk/kill_switch.py`
- `KillSwitch` class with `trigger_emergency_stop()` and `release_emergency_stop()`
- In-memory state + audit log to `risk_audit_log` table
- Global kill switch check via `risk_settings` table

### `risk/observability.py`
- `RiskMetrics` singleton tracks: evaluations, approvals, warnings, rejections, per-rule latency
- Exposed via `stats` property

### `risk/event_subscriber.py`
- Listens to `OrderPlaced`, `OrderRejected`, `RiskSettingsChanged` events
- Invalidates cached RiskConfig so fresh settings are loaded on next request

## Integration Points

| Layer | Integration |
|-------|-------------|
| `execution/manager.py:place_order()` | Calls `risk_manager.evaluate(req)` after validation, before broker send |
| `execution/event_bus.py` | RiskManager publishes decisions; RiskEventSubscriber listens for config changes |
| `routes/v1_risk.py` | Existing routes for GET/POST `/risk/settings` (no changes needed) |

## Existing RiskGuard

The existing `RiskGuard` in `risk/riskguard.py` continues to be used by `gate.py` for:
- Paper mode routing decisions
- Pre-ExecutionManager checks

The Risk Engine runs inside `ExecutionManager` and is a separate, additive layer. No duplicate risk logic.

## Configuration

Risk limits are configured per user in the `risk_settings` table:

| Field | Maps To |
|-------|---------|
| `kill_switch_enabled` | KillSwitchRule |
| `max_daily_loss` | DailyLossLimitRule |
| `max_position_size` | MaxQuantityRule |
| `max_open_positions` | MaxOpenPositionsRule |
| `max_capital` | MaxCapitalRule, MaxExposureRule |
| `max_drawdown_pct` | MaxDrawdownRule |
| `trading_start`, `trading_end` | TradingWindowRule |
| `allow_warning` | Controls whether WARNING proceeds |

## Observability

Risk metrics exposed via `RiskMetrics.stats`:

```json
{
  "total_evaluations": 1000,
  "approved": 950,
  "warning": 30,
  "rejected": 20,
  "avg_latency_ms": 2.5,
  "rule_stats": {
    "KILL_SWITCH": { "count": 1000, "avg_latency_ms": 0.1, "max_latency_ms": 0.5 }
  }
}
```
