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


class UserProfile(BaseModel):
    id: str
    email: str
    full_name: str = ""
    phone: str = ""
    is_admin: bool = False
    subscription_tier: str = "free"
    created_at: datetime = Field(default_factory=datetime.utcnow)
