"""
Execution engine data models.

Signal        = what an admin-assigned strategy emits (one per market event).
OrderIntent   = the concrete order we intend to place for ONE user.
ExecutionResult / ExecutionBatch = outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Action(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class OrderType(str, Enum):
    MKT = "MKT"
    LMT = "LMT"
    SL = "SL"
    SL_M = "SL-M"


class Product(str, Enum):
    INTRADAY = "INTRADAY"   # MIS
    MARGIN = "MARGIN"       # NRML
    CNC = "CNC"             # delivery


class Segment(str, Enum):
    INDEX = "INDEX"         # -> ATM option
    EQUITY = "EQUITY"       # -> stock
    COMMODITY = "COMMODITY" # -> future
    CURRENCY = "CURRENCY"   # -> future
    CRYPTO = "CRYPTO"       # -> spot


class Mode(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class ResultStatus(str, Enum):
    PLACED = "placed"
    REJECTED = "rejected"
    SKIPPED_NO_CONN = "skipped_no_conn"
    SKIPPED_EXPIRED = "skipped_expired"
    SKIPPED_KILLED = "skipped_killed"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    RISK_BLOCKED = "risk_blocked"
    SIZED_ZERO = "sized_zero"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Signal — API input from the admin/strategy layer
# ---------------------------------------------------------------------------
class Signal(BaseModel):
    """One trading signal for a strategy. Fanned out to all live subscribers."""
    signal_id: str = Field(..., description="Unique per emission; used for idempotency.")
    strategy_id: str
    algo_id: str | None = Field(None, description="Exchange-assigned Algo ID (SEBI 2026).")

    action: Action = Action.ENTRY
    segment: Segment
    # Canonical instrument. Adapters format this to each broker's symbol syntax.
    symbol: str = Field(..., description="Canonical symbol, e.g. 'NIFTY' or 'RELIANCE'.")
    exchange: str | None = Field(None, description="e.g. NSE / NFO / MCX / CDS.")
    option_meta: dict | None = Field(
        None, description="For INDEX/option strategies: {strike, opt_type, expiry}."
    )

    side: Side
    order_type: OrderType = OrderType.MKT
    limit_price: float | None = None
    trigger_price: float | None = None
    product: Product = Product.INTRADAY

    # for bracket-style protective orders
    target: float | None = None
    stoploss: float | None = None

    # reference price + lot size so sizing can run without a live quote
    ref_price: float = Field(..., gt=0, description="Reference LTP for sizing.")
    lot_size: int = Field(1, ge=1)

    emitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Internal dataclasses
# ---------------------------------------------------------------------------
@dataclass
class Subscriber:
    user_id: str
    broker: str
    broker_user_id: str | None = None


@dataclass
class UserTradingProfile:
    user_id: str
    mode: Mode = Mode.PAPER          # safety default
    capital: float = 0.0             # deployable capital for sizing
    risk_fraction: float = 0.01      # 1% of capital per trade
    max_lots: int = 10               # hard cap
    tier: str | None = None


@dataclass
class OrderIntent:
    user_id: str
    broker: str
    broker_symbol: str               # broker-formatted symbol
    side: Side
    qty: int
    order_type: OrderType
    product: Product
    est_price: float = 0.0           # limit price, else signal ref_price (for risk/notional + orders.price)
    limit_price: float | None = None
    trigger_price: float | None = None
    target: float | None = None
    stoploss: float | None = None


@dataclass
class ExecutionResult:
    user_id: str
    broker: str
    status: ResultStatus
    broker_order_id: str | None = None
    qty: int = 0
    reason: str | None = None


@dataclass
class ExecutionBatch:
    signal_id: str
    strategy_id: str
    dispatched: int = 0
    placed: int = 0
    skipped: int = 0
    blocked: int = 0
    errors: int = 0
    results: list[ExecutionResult] = field(default_factory=list)

    def add(self, r: ExecutionResult) -> None:
        self.results.append(r)
        if r.status == ResultStatus.PLACED:
            self.placed += 1
        elif r.status in (ResultStatus.RISK_BLOCKED,):
            self.blocked += 1
        elif r.status == ResultStatus.ERROR:
            self.errors += 1
        else:
            self.skipped += 1
