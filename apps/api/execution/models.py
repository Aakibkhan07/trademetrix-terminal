from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ExecutionState(StrEnum):
    NEW = "NEW"
    VALIDATED = "VALIDATED"
    SENT = "SENT"
    PENDING = "PENDING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


EXECUTION_STATE_TRANSITIONS: dict[ExecutionState, set[ExecutionState]] = {
    ExecutionState.NEW: {ExecutionState.VALIDATED, ExecutionState.REJECTED, ExecutionState.FAILED},
    ExecutionState.VALIDATED: {ExecutionState.SENT, ExecutionState.REJECTED, ExecutionState.FAILED},
    ExecutionState.SENT: {ExecutionState.PENDING, ExecutionState.PARTIALLY_FILLED, ExecutionState.FILLED, ExecutionState.REJECTED, ExecutionState.FAILED},
    ExecutionState.PENDING: {ExecutionState.PARTIALLY_FILLED, ExecutionState.FILLED, ExecutionState.CANCELLED, ExecutionState.REJECTED, ExecutionState.EXPIRED},
    ExecutionState.PARTIALLY_FILLED: {ExecutionState.PENDING, ExecutionState.FILLED, ExecutionState.CANCELLED, ExecutionState.REJECTED},
    ExecutionState.FILLED: set(),
    ExecutionState.REJECTED: set(),
    ExecutionState.CANCELLED: set(),
    ExecutionState.FAILED: set(),
    ExecutionState.EXPIRED: set(),
}


class BrokerCapabilities(BaseModel):
    broker: str = ""
    supports_orders: bool = True
    supports_modify: bool = True
    supports_cancel: bool = True
    supports_bracket: bool = False
    supports_cover: bool = False
    supports_gtt: bool = False
    supports_websocket: bool = False
    supports_option_chain: bool = False
    supports_positions: bool = True
    supports_holdings: bool = True


class ValidationResult(BaseModel):
    valid: bool = True
    errors: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OrderLifecycle(BaseModel):
    execution_request_id: str = ""
    client_order_id: str = ""
    broker_order_id: str = ""
    user_id: str = ""
    broker: str = ""
    symbol: str = ""
    side: str = ""
    quantity: int = 0
    price: float = 0.0
    state: ExecutionState = ExecutionState.NEW
    previous_state: ExecutionState | None = None
    message: str = ""
    error_code: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    latency_ms: float = 0.0
    retry_count: int = 0
    payload_hash: str = ""


class ExecutionRequest(BaseModel):
    user_id: str
    broker: str
    symbol: str
    exchange: str = "NSE"
    side: str
    order_type: str = "MARKET"
    product: str = "INTRADAY"
    quantity: int
    price: float = 0.0
    trigger_price: float | None = None
    disclosed_quantity: int = 0
    validity: str = "DAY"
    instrument_type: str = "EQ"
    strike_price: float | None = None
    expiry_date: str | None = None
    option_type: str | None = None
    strategy_id: str | None = None
    source: str = "manual"
    execution_request_id: str = ""


class ExecutionResult(BaseModel):
    success: bool = False
    execution_request_id: str = ""
    broker_order_id: str = ""
    state: ExecutionState = ExecutionState.NEW
    message: str = ""
    error_code: str = ""
    latency_ms: float = 0.0
    lifecycle: OrderLifecycle | None = None


class ExecutionEvent(BaseModel):
    event_type: str
    execution_request_id: str = ""
    user_id: str = ""
    broker: str = ""
    symbol: str = ""
    side: str = ""
    state: ExecutionState = ExecutionState.NEW
    message: str = ""
    payload: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ExecutionMetrics(BaseModel):
    orders_placed: int = 0
    orders_failed: int = 0
    orders_rejected: int = 0
    orders_cancelled: int = 0
    orders_filled: int = 0
    average_latency_ms: float = 0.0
    broker_latency_ms: dict[str, float] = Field(default_factory=dict)
    total_retries: int = 0
    duplicate_requests_prevented: int = 0
    validation_failures: int = 0
    broker_errors: dict[str, int] = Field(default_factory=dict)
