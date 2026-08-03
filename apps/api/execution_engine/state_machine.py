"""Canonical order state machine (Execution Engine v1.0).

Merges the two legacy transition tables — ``OMS_STATE_TRANSITIONS``
(oms/models.py) and ``EXECUTION_STATE_TRANSITIONS`` (execution/models.py) —
into one authoritative superset that also covers infrastructure-lifetime
states (``FAILED``) so a single machine governs every layer.

Naming: canonical uses ``PARTIALLY_FILLED``; ``PARTIAL`` is accepted as a
legacy alias on input (both resolve to the same canonical member), so OMS
orders, execution results and broker feeds all normalize cleanly.
"""
from __future__ import annotations

import logging
from enum import StrEnum

logger = logging.getLogger(__name__)


class OrderState(StrEnum):
    NEW = "NEW"
    VALIDATED = "VALIDATED"
    QUEUED = "QUEUED"
    SENT = "SENT"
    PENDING = "PENDING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    PARTIAL = "PARTIALLY_FILLED"  # legacy alias
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


STATE_TRANSITIONS: dict[OrderState, set[OrderState]] = {
    OrderState.NEW: {OrderState.VALIDATED, OrderState.QUEUED, OrderState.REJECTED, OrderState.FAILED},
    OrderState.VALIDATED: {OrderState.QUEUED, OrderState.SENT, OrderState.REJECTED, OrderState.FAILED},
    OrderState.QUEUED: {OrderState.SENT, OrderState.CANCELLED, OrderState.REJECTED, OrderState.FAILED},
    OrderState.SENT: {OrderState.PENDING, OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.REJECTED, OrderState.FAILED},
    OrderState.PENDING: {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED, OrderState.EXPIRED, OrderState.FAILED},
    OrderState.PARTIALLY_FILLED: {OrderState.PENDING, OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED, OrderState.FAILED},
    OrderState.FILLED: set(),
    OrderState.CANCELLED: set(),
    OrderState.REJECTED: set(),
    OrderState.EXPIRED: set(),
    OrderState.FAILED: set(),
}

TERMINAL_STATES: frozenset[OrderState] = frozenset(
    {OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED, OrderState.EXPIRED, OrderState.FAILED}
)

ACTIVE_STATES: frozenset[OrderState] = frozenset(
    {OrderState.NEW, OrderState.VALIDATED, OrderState.QUEUED, OrderState.SENT, OrderState.PENDING, OrderState.PARTIALLY_FILLED}
)


_STATE_ALIASES: dict[str, OrderState] = {
    "PARTIAL": OrderState.PARTIALLY_FILLED,
}


def normalize(state: str | OrderState | None) -> OrderState | None:
    """Resolve a legacy/string state name to a canonical OrderState.

    Accepts ``PARTIAL`` → ``PARTIALLY_FILLED`` and any known enum value or
    member name; unknown values are rejected (returns None).
    """
    if state is None:
        return None
    if isinstance(state, OrderState):
        return OrderState(state.value)  # canonicalize alias members
    text = str(state).strip().upper()
    if text in _STATE_ALIASES:
        return _STATE_ALIASES[text]
    try:
        return OrderState(text)
    except ValueError:
        try:
            return OrderState[text]
        except KeyError:
            return None


class OrderStateMachine:
    def transition(self, current: OrderState, target: OrderState) -> OrderState:
        allowed = STATE_TRANSITIONS.get(current, set())
        if target not in allowed:
            logger.warning("Invalid state transition: %s -> %s", current, target)
            return current
        return target

    def can_transition(self, current: OrderState, target: OrderState) -> bool:
        return target in STATE_TRANSITIONS.get(current, set())

    def is_terminal(self, state: str | OrderState | None) -> bool:
        norm = normalize(state)
        return norm in TERMINAL_STATES if norm is not None else False

    def is_active(self, state: str | OrderState | None) -> bool:
        norm = normalize(state)
        return norm in ACTIVE_STATES if norm is not None else False

    def next_valid(self, current: OrderState) -> list[OrderState]:
        return sorted(STATE_TRANSITIONS.get(current, set()), key=lambda s: s.value)


state_machine = OrderStateMachine()