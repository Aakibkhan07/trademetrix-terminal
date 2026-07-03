from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class FillType(StrEnum):
    INSTANT = "INSTANT"
    NEXT_TICK = "NEXT_TICK"
    PRICE_BASED = "PRICE_BASED"
    VOLUME_BASED = "VOLUME_BASED"


class PaperOrderStatus(StrEnum):
    PENDING = "PENDING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class PaperConfig(BaseModel):
    initial_capital: float = 500000.0
    broker_delay_ms: float = 50.0
    slippage_pct: float = 0.01
    commission_pct: float = 0.0
    exchange_charges_pct: float = 0.0
    stt_pct: float = 0.0
    stamp_duty_pct: float = 0.0
    enable_partial_fill: bool = False
    fill_type: FillType = FillType.INSTANT
    min_fill_probability: float = 0.95


class PaperPosition(BaseModel):
    symbol: str = ""
    exchange: str = "NSE"
    quantity: int = 0
    buy_quantity: int = 0
    sell_quantity: int = 0
    average_buy_price: float = 0.0
    average_sell_price: float = 0.0
    realised_pnl: float = 0.0
    unrealised_pnl: float = 0.0
    m2m: float = 0.0
    product: str = "INTRADAY"
    multiplier: float = 1.0
    last_price: float = 0.0


class PaperAccount(BaseModel):
    user_id: str = ""
    total_margin: float = 0.0
    used_margin: float = 0.0
    available_margin: float = 0.0
    payin: float = 0.0
    payout: float = 0.0
    collateral: float = 0.0
    m2m_unrealised: float = 0.0
    initial_capital: float = 500000.0
    current_value: float = 500000.0


class PaperFill(BaseModel):
    order_id: str = ""
    symbol: str = ""
    side: str = ""
    filled_quantity: int = 0
    filled_price: float = 0.0
    fill_timestamp: datetime = Field(default_factory=datetime.utcnow)
    commission: float = 0.0
    exchange_charges: float = 0.0
    stt: float = 0.0
    stamp_duty: float = 0.0
    net_amount: float = 0.0


class PaperMetrics(BaseModel):
    total_orders: int = 0
    filled_orders: int = 0
    rejected_orders: int = 0
    cancelled_orders: int = 0
    partial_fills: int = 0
    total_pnl: float = 0.0
    total_commission: float = 0.0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
