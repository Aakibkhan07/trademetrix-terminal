from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SignalSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    EXIT = "EXIT"
    REVERSE = "REVERSE"
    HOLD = "HOLD"
    IGNORE = "IGNORE"


class StrategyState(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class TriggerType(StrEnum):
    EVERY_TICK = "EVERY_TICK"
    CANDLE_CLOSE = "CANDLE_CLOSE"
    EVERY_MINUTE = "EVERY_MINUTE"
    EVERY_5_MINUTES = "EVERY_5_MINUTES"
    MARKET_OPEN = "MARKET_OPEN"
    MARKET_CLOSE = "MARKET_CLOSE"
    CRON = "CRON"


class RuntimeSignal(BaseModel):
    strategy_id: str = ""
    signal_id: str = ""
    side: SignalSide = SignalSide.HOLD
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    confidence: float = 0.0
    reason: str = ""
    symbol: str = ""
    exchange: str = "NSE"
    quantity: int = 0
    price: float = 0.0
    sl_price: float = 0.0
    target_price: float = 0.0
    product: str = "INTRADAY"
    metadata: dict = Field(default_factory=dict)


class RuntimeConfig(BaseModel):
    user_id: str = ""
    strategy_id: str = ""
    strategy_key: str = ""
    symbol: str = ""
    exchange: str = "NSE"
    interval: str = "1m"
    trigger: TriggerType = TriggerType.CANDLE_CLOSE
    cron_expression: str = ""
    max_positions: int = 1
    max_risk_per_trade: float = 0.0
    max_daily_trades: int = 0
    variables: dict = Field(default_factory=dict)
    enabled: bool = True
    broker: str = ""


class RuntimeMetrics(BaseModel):
    strategy_id: str = ""
    evaluation_count: int = 0
    signals_generated: int = 0
    signals_rejected: int = 0
    errors: int = 0
    avg_evaluation_latency_ms: float = 0.0
    last_evaluation_at: datetime | None = None
    last_signal_at: datetime | None = None
    uptime_seconds: float = 0.0


class StrategyPlugin(BaseModel):
    key: str = ""
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    triggers: list[TriggerType] = Field(default_factory=list)
    required_indicators: list[str] = Field(default_factory=list)
    config_schema: dict = Field(default_factory=dict)
    path: str = ""
    enabled: bool = True
    health: bool = True
