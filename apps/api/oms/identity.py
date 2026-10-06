"""Deterministic identity for one logical order, and for its material attributes.

Two separate questions, kept separate because conflating them is what produced duplicate
orders:

  * **Which logical order is this?** The client order id, minted once when the intent first
    enters the OMS and carried unchanged through every retry. It is sent to Dhan as the
    ``correlationId`` header, so it is the one identifier a lost response can be
    reconciled against.

  * **Is a retry still the same order?** The intent fingerprint, a hash of the attributes
    that would make it a *different* trade: account, broker, contract, side, quantity, order
    type, product, expiry, strike, option type. If any of those change, the "retry" is a new
    order and must go through complete risk evaluation.

Price is deliberately excluded. A MARKET order is legitimately re-priced on every attempt
because the market moved, and treating that as a changed intent would classify ordinary
retries as new orders -- which is how a naive "did anything change?" check ends up
re-running duplicate protection on the same order forever.

Timestamps are excluded for the same reason in reverse: `sent_at` differs on every attempt,
so including it would make identity unfalsifiable.
"""
from __future__ import annotations

import hashlib

#: Fields whose change makes a "retry" a different trade.
MATERIAL_ATTRIBUTES = (
    "user_id", "broker", "symbol", "side", "quantity", "order_type", "product",
    "instrument_type", "expiry_date", "strike_price", "option_type",
)


def _norm(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return f"{value:g}"
    return str(getattr(value, "value", value)).strip()


def intent_fingerprint(order) -> str:
    """A stable hash of the attributes that define the trade.

    Accepts an `OmniOrder` or an `ExecutionRequest`; both expose the same names.
    """
    parts = [_norm(getattr(order, field, None)) for field in MATERIAL_ATTRIBUTES]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def material_attributes(order) -> dict:
    """The material attributes as a plain dict, for diffing and for audit output."""
    return {field: _norm(getattr(order, field, None)) for field in MATERIAL_ATTRIBUTES}


def same_intent(stored_fingerprint: str, order) -> bool:
    """Whether ``order`` is still the intent that ``stored_fingerprint`` describes."""
    if not stored_fingerprint:
        # Nothing was recorded, so this cannot be claimed to be a retry. Fail closed: treat
        # it as a new order so full risk evaluation runs.
        return False
    return stored_fingerprint == intent_fingerprint(order)
