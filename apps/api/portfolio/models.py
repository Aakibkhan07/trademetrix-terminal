from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class SyncStatus(StrEnum):
    SYNCED = "SYNCED"
    PENDING = "PENDING"
    FAILED = "FAILED"
    DRIFTED = "DRIFTED"


class PortfolioPosition(BaseModel):
    user_id: str = ""
    broker: str = ""
    symbol: str = ""
    exchange: str = "NSE"
    quantity: int = 0
    buy_quantity: int = 0
    sell_quantity: int = 0
    average_buy_price: float = 0.0
    average_sell_price: float = 0.0
    last_price: float = 0.0
    unrealised_pnl: float = 0.0
    realised_pnl: float = 0.0
    m2m: float = 0.0
    product: str = "INTRADAY"
    instrument_type: str = "EQ"
    strike_price: float | None = None
    expiry_date: str | None = None
    option_type: str | None = None
    lot_size: int = 1
    multiplier: float = 1.0
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PortfolioHolding(BaseModel):
    user_id: str = ""
    broker: str = ""
    symbol: str = ""
    exchange: str = "NSE"
    quantity: int = 0
    t1_quantity: int = 0
    available_quantity: int = 0
    average_price: float = 0.0
    current_price: float = 0.0
    pnl: float = 0.0
    cost_price: float = 0.0
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PortfolioFunds(BaseModel):
    user_id: str = ""
    broker: str = ""
    total_margin: float = 0.0
    used_margin: float = 0.0
    available_margin: float = 0.0
    payin: float = 0.0
    payout: float = 0.0
    collateral: float = 0.0
    m2m_unrealised: float = 0.0
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PortfolioPnL(BaseModel):
    user_id: str = ""
    broker: str = ""
    realised_pnl: float = 0.0
    unrealised_pnl: float = 0.0
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    monthly_pnl: float = 0.0
    overall_pnl: float = 0.0
    day_start_equity: float = 0.0
    current_equity: float = 0.0
    peak_equity: float = 0.0
    drawdown_pct: float = 0.0
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class BrokerSyncStatus(BaseModel):
    user_id: str = ""
    broker: str = ""
    last_positions_sync: datetime | None = None
    last_holdings_sync: datetime | None = None
    last_funds_sync: datetime | None = None
    last_orders_sync: datetime | None = None
    positions_sync_status: SyncStatus = SyncStatus.PENDING
    holdings_sync_status: SyncStatus = SyncStatus.PENDING
    funds_sync_status: SyncStatus = SyncStatus.PENDING
    orders_sync_status: SyncStatus = SyncStatus.PENDING
    retry_count: int = 0
    error_message: str = ""


class ReconciliationResult(BaseModel):
    user_id: str = ""
    broker: str = ""
    synced_at: datetime = Field(default_factory=datetime.utcnow)
    local_positions: int = 0
    broker_positions: int = 0
    missing_orders: list[str] = Field(default_factory=list)
    ghost_positions: list[str] = Field(default_factory=list)
    duplicate_positions: list[str] = Field(default_factory=list)
    out_of_sync_quantities: list[dict] = Field(default_factory=list)
    drift_detected: bool = False
    drift_details: str = ""


class PortfolioState(BaseModel):
    user_id: str = ""
    broker: str = ""
    positions: dict[str, PortfolioPosition] = Field(default_factory=dict)
    holdings: dict[str, PortfolioHolding] = Field(default_factory=dict)
    funds: PortfolioFunds = Field(default_factory=lambda: PortfolioFunds())
    pnl: PortfolioPnL = Field(default_factory=lambda: PortfolioPnL())
    orders: list[dict] = Field(default_factory=list)
    sync_status: BrokerSyncStatus = Field(default_factory=lambda: BrokerSyncStatus())
    reconciliation: ReconciliationResult = Field(default_factory=lambda: ReconciliationResult())
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class PortfolioSummary(BaseModel):
    user_id: str = ""
    total_positions: int = 0
    open_positions: int = 0
    total_holdings: int = 0
    total_margin: float = 0.0
    used_margin: float = 0.0
    available_margin: float = 0.0
    unrealised_pnl: float = 0.0
    realised_pnl: float = 0.0
    daily_pnl: float = 0.0
    total_invested: float = 0.0
    total_exposure: float = 0.0
    drawdown_pct: float = 0.0
    last_synced: datetime | None = None
    brokers: list[str] = Field(default_factory=list)
