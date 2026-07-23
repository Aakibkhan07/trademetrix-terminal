from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class OMSOrderState(StrEnum):
    NEW = "NEW"
    VALIDATED = "VALIDATED"
    QUEUED = "QUEUED"
    SENT = "SENT"
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


OMS_STATE_TRANSITIONS: dict[OMSOrderState, set[OMSOrderState]] = {
    OMSOrderState.NEW: {OMSOrderState.VALIDATED, OMSOrderState.QUEUED, OMSOrderState.REJECTED},
    OMSOrderState.VALIDATED: {OMSOrderState.QUEUED, OMSOrderState.REJECTED},
    OMSOrderState.QUEUED: {OMSOrderState.SENT, OMSOrderState.REJECTED, OMSOrderState.CANCELLED},
    OMSOrderState.SENT: {OMSOrderState.PENDING, OMSOrderState.PARTIAL, OMSOrderState.FILLED, OMSOrderState.REJECTED},
    OMSOrderState.PENDING: {OMSOrderState.PARTIAL, OMSOrderState.FILLED, OMSOrderState.CANCELLED, OMSOrderState.REJECTED, OMSOrderState.EXPIRED},
    OMSOrderState.PARTIAL: {OMSOrderState.PENDING, OMSOrderState.FILLED, OMSOrderState.CANCELLED, OMSOrderState.REJECTED},
    OMSOrderState.FILLED: set(),
    OMSOrderState.CANCELLED: set(),
    OMSOrderState.REJECTED: set(),
    OMSOrderState.EXPIRED: set(),
}


class OrderRelationType(StrEnum):
    NONE = "NONE"
    BRACKET = "BRACKET"
    OCO = "OCO"
    PARENT = "PARENT"
    CHILD = "CHILD"


class OmniOrder(BaseModel):
    oms_order_id: str = ""
    execution_request_id: str = ""
    client_order_id: str = ""
    broker_order_id: str = ""
    user_id: str = ""
    broker: str = ""
    symbol: str = ""
    exchange: str = "NSE"
    side: str = ""
    order_type: str = "MARKET"
    product: str = "INTRADAY"
    quantity: int = 0
    filled_quantity: int = 0
    average_price: float = 0.0
    price: float = 0.0
    trigger_price: float | None = None
    state: OMSOrderState = OMSOrderState.NEW
    prev_state: OMSOrderState | None = None
    relation_type: OrderRelationType = OrderRelationType.NONE
    parent_order_id: str = ""
    sibling_order_id: str = ""
    child_order_ids: list[str] = Field(default_factory=list)
    strategy_id: str = ""
    source: str = "manual"
    retry_count: int = 0
    max_retries: int = 3
    priority: int = 0
    is_paper: bool = False
    error_code: str = ""
    message: str = ""
    latency_ms: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    sent_at: datetime | None = None
    filled_at: datetime | None = None
    cancelled_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class BracketOrder(BaseModel):
    oms_order_id: str = ""
    parent_order_id: str = ""
    user_id: str = ""
    symbol: str = ""
    quantity: int = 0
    entry_price: float = 0.0
    stop_loss_price: float = 0.0
    target_price: float = 0.0
    trailing_sl_pct: float = 0.0
    entry_filled: bool = False
    sl_order_id: str = ""
    target_order_id: str = ""
    active: bool = True


class OCOOrder(BaseModel):
    oms_order_id: str = ""
    user_id: str = ""
    symbol: str = ""
    quantity: int = 0
    order_a_id: str = ""
    order_b_id: str = ""
    order_a_filled: bool = False
    order_b_filled: bool = False
    active: bool = True


class OrderQueueItem(BaseModel):
    oms_order_id: str = ""
    user_id: str = ""
    broker: str = ""
    priority: int = 0
    enqueued_at: datetime = Field(default_factory=datetime.utcnow)
    retry_count: int = 0
    next_retry_at: datetime | None = None


class OrderQueueStats(BaseModel):
    total_pending: int = 0
    total_queued: int = 0
    total_processing: int = 0
    queue_depth: int = 0
    retry_count: int = 0
    oldest_enqueued: datetime | None = None
