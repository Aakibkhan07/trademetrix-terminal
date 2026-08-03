"""Strategy Runtime v1.0 — data models.

Runtime lifecycle states (all eight), execution specs, per-strategy status and
durable checkpoint payloads. Pure data models — no engine imports — so this
module stays a stable contract for the runtime layer and its persistence.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RuntimeState(StrEnum):
    """Lifecycle states supported by Strategy Runtime v1.0.

    CREATED/STARTING/RUNNING/PAUSED/STOPPED/FAILED are per-strategy;
    RECOVERING/RECOVERED describe the whole runtime during/after startup
    recovery (exposed via the manager health surface).
    """

    CREATED = "CREATED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"
    RECOVERED = "RECOVERED"


class StrategyTrigger(StrEnum):
    EVERY_TICK = "EVERY_TICK"
    CANDLE_CLOSE = "CANDLE_CLOSE"
    EVERY_MINUTE = "EVERY_MINUTE"
    EVERY_5_MINUTES = "EVERY_5_MINUTES"
    MARKET_OPEN = "MARKET_OPEN"
    MARKET_CLOSE = "MARKET_CLOSE"
    CRON = "CRON"


class StrategySpec(BaseModel):
    """Everything needed to (re)start a strategy deterministically.

    The spec is fully JSON-serializable and is the durable checkpoint body
    written to the ``execution_checkpoints`` store (kind ``strategy_runtime``).
    """

    strategy_id: str
    user_id: str
    symbol: str = "NIFTY"
    exchange: str = "NSE"
    interval: str = "15m"
    timeframes: list[str] = Field(default_factory=lambda: ["15m"])
    mode: str = "paper"  # paper | live
    is_paper: bool = True
    broker: str = ""
    account: str = ""
    trigger: StrategyTrigger = StrategyTrigger.CANDLE_CLOSE
    cron_expression: str = ""
    warmup: bool = True
    quantity: int = 75
    max_positions: int = 1
    max_risk_per_trade: float = 0.0
    max_daily_trades: int = 0
    variables: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def checkpoint(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class StrategyRuntimeStatus(BaseModel):
    strategy_id: str = ""
    user_id: str = ""
    state: RuntimeState = RuntimeState.CREATED
    symbol: str = ""
    exchange: str = "NSE"
    interval: str = "15m"
    timeframes: list[str] = Field(default_factory=list)
    mode: str = "paper"
    broker: str = ""
    account: str = ""
    trigger: str = "CANDLE_CLOSE"
    started_at: str = ""
    stopped_at: str = ""
    restart_count: int = 0
    worker_active: bool = False
    last_error: str = ""
    last_activity: str = ""
    paused_reason: str = ""
    last_price: float = 0.0
    stats: dict[str, Any] = Field(default_factory=dict)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()
