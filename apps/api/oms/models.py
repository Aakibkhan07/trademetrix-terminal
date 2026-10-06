from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class OMSOrderState(StrEnum):
    NEW = "NEW"
    VALIDATED = "VALIDATED"
    QUEUED = "QUEUED"
    SENT = "SENT"
    #: The request left us and the broker never answered. Nobody knows whether it exists.
    #: `SENT` used to be stretched to cover this, and a failure beneath it was read as a
    #: rejection -- so a lost response produced a retry, and the retry a duplicate order.
    UNKNOWN = "UNKNOWN"
    #: A reconciliation attempt is in flight. Never retried from here.
    RECONCILING = "RECONCILING"
    #: More than one broker order matches, or matching cannot be narrowed. Requires a human.
    #: Never auto-resolved: picking one would risk duplicating or cancelling a real order.
    AMBIGUOUS = "AMBIGUOUS"
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
    OMSOrderState.SENT: {
        OMSOrderState.UNKNOWN, OMSOrderState.RECONCILING,
        OMSOrderState.PENDING, OMSOrderState.PARTIAL,
        OMSOrderState.FILLED, OMSOrderState.REJECTED,
    },
    #: An unknown result may only be resolved by asking the broker. Retrying from here
    #: without asking is what produced duplicate orders at the broker.
    OMSOrderState.UNKNOWN: {
        OMSOrderState.RECONCILING, OMSOrderState.PENDING, OMSOrderState.PARTIAL,
        OMSOrderState.FILLED, OMSOrderState.REJECTED, OMSOrderState.AMBIGUOUS,
        OMSOrderState.CANCELLED, OMSOrderState.EXPIRED,
    },
    OMSOrderState.RECONCILING: {
        OMSOrderState.UNKNOWN, OMSOrderState.PENDING, OMSOrderState.PARTIAL,
        OMSOrderState.FILLED, OMSOrderState.REJECTED, OMSOrderState.AMBIGUOUS,
        OMSOrderState.CANCELLED, OMSOrderState.EXPIRED,
    },
    #: Terminal, deliberately. An ambiguous order is a human decision.
    OMSOrderState.AMBIGUOUS: set(),
    OMSOrderState.PENDING: {OMSOrderState.PARTIAL, OMSOrderState.FILLED, OMSOrderState.CANCELLED, OMSOrderState.REJECTED, OMSOrderState.EXPIRED},
    OMSOrderState.PARTIAL: {OMSOrderState.QUEUED, OMSOrderState.PENDING, OMSOrderState.FILLED, OMSOrderState.CANCELLED, OMSOrderState.REJECTED},
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
    #: The derivative identity of the contract.
    #:
    #: These were absent, and their absence was invisible until the *queue* path was
    #: exercised end to end. `place_order` accepts them on `ExecutionRequest` and
    #: `_process_queue` rebuilds the request from this model, so anything not stored here is
    #: gone by the time the broker adapter sees the order. The measured effect: an option
    #: order placed through the real OMS queue reached Dhan with the correct `securityId`
    #: and `exchangeSegment` but **no expiry, no strike and no option type** -- because
    #: `DhanAdapter.place_order` only emits `drvExpiryDate` / `drvStrikePrice` /
    #: `drvOptionType` when `instrument_type` is FUT or OPT. A direct
    #: `ExecutionManager.place_order` call carried all of them, so the two paths disagreed
    #: about which contract was being traded.
    #:
    #: Defaults are empty rather than required so an equity order, and every row written
    #: before this existed, still loads.
    instrument_type: str = ""
    expiry_date: str = ""
    strike_price: float | None = None
    option_type: str = ""
    validity: str = ""
    disclosed_quantity: int = 0
    #: Reconciliation bookkeeping. Needed because an order whose response was lost has no
    #: `broker_order_id`, so the existing loop -- which matches on `broker_order_id` alone --
    #: could not see it at all, and the order sat in whatever state it failed in forever.
    reconcile_attempts: int = 0
    #: Consecutive "the broker does not have it" observations. A single absence is not proof.
    not_found_observations: int = 0
    #: Deterministic fingerprint of the material order attributes, used to tell a retry of
    #: the same intent from a genuinely new order. Excludes price and any timestamp: a
    #: MARKET order is legitimately re-priced between attempts, and a timestamp alone would
    #: make every retry look like a new order.
    intent_fingerprint: str = ""
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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
    side: str = "BUY"
    broker: str = "fyers"


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
    enqueued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    retry_count: int = 0
    next_retry_at: datetime | None = None


class OrderQueueStats(BaseModel):
    total_pending: int = 0
    total_queued: int = 0
    total_processing: int = 0
    queue_depth: int = 0
    retry_count: int = 0
    oldest_enqueued: datetime | None = None
