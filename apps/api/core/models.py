from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class OptionType(StrEnum):
    CE = "CE"
    PE = "PE"


class InstrumentType(StrEnum):
    EQ = "EQ"
    FUT = "FUT"
    OPT = "OPT"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SLM = "SLM"


class ProductType(StrEnum):
    DELIVERY = "DELIVERY"
    INTRADAY = "INTRADAY"
    MIS = "MIS"
    NRML = "NRML"


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class Exchange(StrEnum):
    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"
    CDS = "CDS"
    MCX = "MCX"


class NormalizedOrder(BaseModel):
    id: str = ""
    broker_order_id: str = ""
    client_order_id: str = ""
    source: str = "manual"
    reason: str = ""
    symbol: str
    exchange: Exchange
    side: OrderSide
    order_type: OrderType
    product: ProductType
    quantity: int
    price: float = 0.0
    trigger_price: float | None = None
    disclosed_quantity: int = 0
    validity: str = "DAY"
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    average_price: float = 0.0
    total_value: float = 0.0
    message: str = ""
    signal_at: datetime | None = None
    risk_checked_at: datetime | None = None
    sent_at: datetime | None = None
    filled_at: datetime | None = None
    latency_ms: float | None = None
    slippage: float | None = None
    strategy_id: str | None = None
    user_id: str | None = None
    broker: str = ""
    instrument_type: InstrumentType = InstrumentType.EQ
    strike_price: float | None = None
    expiry_date: str | None = None
    option_type: OptionType | None = None
    is_paper: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class OrderResult(BaseModel):
    success: bool
    broker_order_id: str = ""
    order: NormalizedOrder | None = None
    message: str = ""
    status: str = ""
    filled_qty: int = 0
    avg_price: float = 0.0


class Position(BaseModel):
    symbol: str
    exchange: Exchange
    quantity: int
    buy_quantity: int = 0
    sell_quantity: int = 0
    average_buy_price: float = 0.0
    average_sell_price: float = 0.0
    unrealised_pnl: float = 0.0
    realised_pnl: float = 0.0
    m2m: float = 0.0
    product: ProductType
    multiplier: float = 1.0
    broker: str = ""
    instrument_type: InstrumentType = InstrumentType.EQ
    strike_price: float | None = None
    expiry_date: str | None = None
    option_type: OptionType | None = None


class Holding(BaseModel):
    symbol: str
    exchange: Exchange
    quantity: int
    t1_quantity: int = 0
    average_price: float = 0.0
    current_price: float = 0.0
    pnl: float = 0.0
    broker: str = ""


class Funds(BaseModel):
    total_margin: float = 0.0
    used_margin: float = 0.0
    available_margin: float = 0.0
    payin: float = 0.0
    payout: float = 0.0
    broker: str = ""


class Quote(BaseModel):
    symbol: str
    exchange: Exchange
    last_price: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    bid: float = 0.0
    ask: float = 0.0
    bid_qty: int = 0
    ask_qty: int = 0
    oi: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    broker: str = ""
    instrument_type: InstrumentType = InstrumentType.EQ
    strike_price: float | None = None
    expiry_date: str | None = None
    option_type: OptionType | None = None


class Candle(BaseModel):
    symbol: str
    exchange: Exchange
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: datetime
    oi: int = 0
    instrument_type: InstrumentType = InstrumentType.EQ


class Tick(BaseModel):
    symbol: str
    exchange: Exchange
    last_price: float
    bid: float = 0.0
    ask: float = 0.0
    bid_qty: int = 0
    ask_qty: int = 0
    volume: int = 0
    oi: int = 0
    change: float = 0.0
    change_pct: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    broker: str = ""
    instrument_type: InstrumentType = InstrumentType.EQ
    strike_price: float | None = None
    expiry_date: str | None = None
    option_type: OptionType | None = None


class Session(BaseModel):
    access_token: str
    user_id: str
    broker: str
    expires_at: datetime | None = None
    authenticated: bool = True


class AuditLogEntry(BaseModel):
    user_id: str
    action: str
    resource: str
    resource_id: str = ""
    details: dict | None = None
    ip_address: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RiskSettings(BaseModel):
    user_id: str
    strategy_id: str | None = None
    max_capital: float = 0.0
    max_position_size: float = 0.0
    max_open_positions: int = 10
    max_daily_loss: float = 0.0
    max_drawdown_pct: float = 0.0
    kill_switch_enabled: bool = False
    is_live: bool = False
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class StrategyAssignment(BaseModel):
    id: str = ""
    user_id: str
    strategy_key: str
    required_tier: str = "free"
    mirror_enabled: bool = True
    active: bool = True
    assigned_by: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


TIER_ORDER: dict[str, int] = {
    "free": 0,
    "starter": 1,
    "pro": 2,
    "enterprise": 3,
}

TIER_LIMITS: dict[str, int] = {
    "free": 1,
    "starter": 2,
    "pro": 8,
    "enterprise": 15,
}

TIER_DAILY_LOSS: dict[str, float] = {
    "free": 2000.0,
    "starter": 3000.0,
    "pro": 5000.0,
    "enterprise": 10000.0,
}


def tier_satisfies(user_tier: str, required_tier: str) -> bool:
    return TIER_ORDER.get(user_tier, -1) >= TIER_ORDER.get(required_tier, 99)


ADMIN_ROLES = ["super_admin", "admin", "support", "analyst"]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "super_admin": ["*"],
    "admin": [
        "users:read", "users:write",
        "trades:read", "trades:write",
        "brokers:read", "brokers:write",
        "broadcast", "audit:read",
        "risk:read", "strategies:read", "strategies:write",
    ],
    "support": ["users:read", "audit:read", "trades:read"],
    "analyst": ["dashboard:read", "trades:read", "analytics:read"],
}

ROLE_HIERARCHY: dict[str, int] = {
    "super_admin": 100,
    "admin": 80,
    "support": 40,
    "analyst": 20,
}


def role_has_permission(role: str, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, [])
    return "*" in perms or permission in perms


def role_satisfies(role: str, min_role: str) -> bool:
    return ROLE_HIERARCHY.get(role, 0) >= ROLE_HIERARCHY.get(min_role, 0)


class UserProfile(BaseModel):
    id: str
    email: str
    full_name: str = ""
    phone: str | None = None
    is_admin: bool = False
    role: str = ""
    subscription_tier: str = "free"
    created_at: datetime | None = None


# ── User-Created Visual Strategy Builder Models ──

class UserStrategyStatus(StrEnum):
    draft = "draft"
    active = "active"
    paused = "paused"

class StrategyType(StrEnum):
    intraday = "intraday"
    positional = "positional"

class UnderlyingFrom(StrEnum):
    cash = "cash"
    futures = "futures"

class LegSegment(StrEnum):
    options = "options"
    futures = "futures"

class LegPosition(StrEnum):
    buy = "buy"
    sell = "sell"

class LegOptionType(StrEnum):
    ce = "CE"
    pe = "PE"

class LegExpiry(StrEnum):
    weekly = "weekly"
    next_weekly = "next_weekly"
    monthly = "monthly"

class StrikeCriteria(StrEnum):
    atm_offset = "atm_offset"
    premium_closest = "premium_closest"
    premium_range = "premium_range"
    delta = "delta"

class SLTargetType(StrEnum):
    percent = "percent"
    points = "points"
    premium = "premium"


class UserStrategyLeg(BaseModel):
    id: str = ""
    strategy_id: str = ""
    leg_order: int
    segment: LegSegment
    position: LegPosition
    option_type: LegOptionType | None = None
    lots: int = 1
    expiry: LegExpiry
    strike_criteria: StrikeCriteria
    strike_value: float
    leg_sl_type: SLTargetType | None = None
    leg_sl_value: float | None = None
    leg_target_type: SLTargetType | None = None
    leg_target_value: float | None = None
    trailing_sl_type: SLTargetType | None = None
    trailing_sl_value: float | None = None
    trailing_activation: float | None = None


class UserStrategy(BaseModel):
    id: str = ""
    user_id: str = ""
    name: str
    status: UserStrategyStatus = UserStrategyStatus.draft
    strategy_type: StrategyType = StrategyType.intraday
    index_symbol: str
    underlying_from: UnderlyingFrom = UnderlyingFrom.cash
    entry_time: str  # HH:MM format
    exit_time: str   # HH:MM format
    days_of_week: list[int] = [1, 2, 3, 4, 5]
    overall_sl_type: SLTargetType | None = None
    overall_sl_value: float | None = None
    overall_target_type: SLTargetType | None = None
    overall_target_value: float | None = None
    legs: list[UserStrategyLeg] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreateUserStrategyRequest(BaseModel):
    name: str
    strategy_type: StrategyType = StrategyType.intraday
    index_symbol: str
    underlying_from: UnderlyingFrom = UnderlyingFrom.cash
    entry_time: str
    exit_time: str
    days_of_week: list[int] = [1, 2, 3, 4, 5]
    overall_sl_type: SLTargetType | None = None
    overall_sl_value: float | None = None
    overall_target_type: SLTargetType | None = None
    overall_target_value: float | None = None
    legs: list[UserStrategyLeg]


class UpdateUserStrategyRequest(BaseModel):
    name: str | None = None
    status: UserStrategyStatus | None = None
    strategy_type: StrategyType | None = None
    index_symbol: str | None = None
    underlying_from: UnderlyingFrom | None = None
    entry_time: str | None = None
    exit_time: str | None = None
    days_of_week: list[int] | None = None
    overall_sl_type: SLTargetType | None = None
    overall_sl_value: float | None = None
    overall_target_type: SLTargetType | None = None
    overall_target_value: float | None = None
    legs: list[UserStrategyLeg] | None = None


class DeployStrategyRequest(BaseModel):
    mode: str  # "PAPER" or "LIVE"


class ExecutionPlan(BaseModel):
    orders: list[NormalizedOrder]
    legs: list[UserStrategyLeg]
    strategy_id: str
    total_lots: int
    is_simulated: bool = False

    @property
    def total_quantity(self) -> int:
        return sum(o.quantity for o in self.orders)
