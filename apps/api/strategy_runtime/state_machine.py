"""Runtime state machine — deterministic lifecycle transitions.

Every transition is validated against an explicit transition table before the
manager mutates a record, so an illegal call can never leave a strategy in an
inconsistent state. All eight Strategy Runtime states are covered (the runtime
manager uses RECOVERING/RECOVERED; per-strategy lifecycle uses the rest).
"""
from __future__ import annotations

from strategy_runtime.models import RuntimeState

TRANSITIONS: dict[RuntimeState, set[RuntimeState]] = {
    RuntimeState.CREATED: {RuntimeState.STARTING, RuntimeState.STOPPED},
    RuntimeState.STARTING: {RuntimeState.RUNNING, RuntimeState.FAILED, RuntimeState.STOPPED},
    RuntimeState.RUNNING: {RuntimeState.PAUSED, RuntimeState.STOPPED, RuntimeState.FAILED},
    RuntimeState.PAUSED: {RuntimeState.RUNNING, RuntimeState.STOPPED, RuntimeState.FAILED},
    RuntimeState.STOPPED: {RuntimeState.STARTING, RuntimeState.FAILED},
    RuntimeState.FAILED: {RuntimeState.STARTING, RuntimeState.STOPPED},
    RuntimeState.RECOVERING: {RuntimeState.RECOVERED},
    RuntimeState.RECOVERED: set(),
}

# States from which a strategy may be (re)started by name.
RESTARTABLE = frozenset({RuntimeState.CREATED, RuntimeState.STOPPED, RuntimeState.FAILED})


class IllegalTransition(Exception):
    def __init__(self, current: RuntimeState, target: RuntimeState):
        self.current = current
        self.target = target
        super().__init__(f"Illegal state transition {current.value} -> {target.value}")


def can_transition(current: RuntimeState, target: RuntimeState) -> bool:
    return target in TRANSITIONS.get(current, set())


def require_transition(current: RuntimeState, target: RuntimeState) -> RuntimeState:
    if not can_transition(current, target):
        raise IllegalTransition(current, target)
    return target
