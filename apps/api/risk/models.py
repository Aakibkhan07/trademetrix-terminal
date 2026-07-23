from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RiskDecision(StrEnum):
    APPROVED = "APPROVED"
    WARNING = "WARNING"
    REJECTED = "REJECTED"


class RiskRuleType(StrEnum):
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    DAILY_PROFIT_TARGET = "DAILY_PROFIT_TARGET"
    MAX_TRADES_PER_DAY = "MAX_TRADES_PER_DAY"
    MAX_OPEN_POSITIONS = "MAX_OPEN_POSITIONS"
    MAX_LOTS = "MAX_LOTS"
    MAX_QUANTITY = "MAX_QUANTITY"
    MAX_EXPOSURE = "MAX_EXPOSURE"
    MAX_ORDERS_PER_MINUTE = "MAX_ORDERS_PER_MINUTE"
    MAX_SYMBOL_EXPOSURE = "MAX_SYMBOL_EXPOSURE"
    MAX_ACCOUNT_EXPOSURE = "MAX_ACCOUNT_EXPOSURE"
    TRADING_WINDOW = "TRADING_WINDOW"
    MARKET_CLOSED = "MARKET_CLOSED"
    BROKER_OFFLINE = "BROKER_OFFLINE"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    FREEZE_QUANTITY = "FREEZE_QUANTITY"
    MARGIN_VALIDATION = "MARGIN_VALIDATION"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    KILL_SWITCH = "KILL_SWITCH"
    MAX_CAPITAL = "MAX_CAPITAL"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"
    LIVE_MODE = "LIVE_MODE"


class RiskRuleResult(BaseModel):
    rule: RiskRuleType
    decision: RiskDecision = RiskDecision.APPROVED
    reason: str = ""
    details: dict = Field(default_factory=dict)
    latency_ms: float = 0.0


class RiskEvalResult(BaseModel):
    decision: RiskDecision = RiskDecision.APPROVED
    results: list[RiskRuleResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    message: str = ""


class AccountRisk(BaseModel):
    user_id: str = ""
    current_exposure: float = 0.0
    open_positions: int = 0
    daily_pnl: float = 0.0
    used_margin: float = 0.0
    available_margin: float = 0.0
    total_margin: float = 0.0
    trade_count: int = 0
    rejected_count: int = 0
    risk_score: int = 0
    max_exposure: float = 0.0
    daily_loss: float = 0.0
    daily_profit: float = 0.0


class PortfolioRisk(BaseModel):
    net_exposure: float = 0.0
    gross_exposure: float = 0.0
    instrument_exposure: dict[str, float] = Field(default_factory=dict)
    symbol_exposure: dict[str, float] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RiskConfig(BaseModel):
    user_id: str = ""
    daily_loss_limit: float = 0.0
    daily_profit_target: float = 0.0
    max_trades_per_day: int = 0
    max_open_positions: int = 10
    max_lots: int = 0
    max_quantity: int = 0
    max_exposure: float = 0.0
    max_orders_per_minute: int = 30
    max_symbol_exposure: float = 0.0
    max_account_exposure: float = 0.0
    max_drawdown_pct: float = 0.0
    max_capital: float = 0.0
    trading_start: str = "09:15"
    trading_end: str = "15:30"
    allow_warning: bool = True
    kill_switch_enabled: bool = False
    is_live: bool = False
    emergency_stop: bool = False
    broker_blocked: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
