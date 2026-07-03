import logging

from oms.models import OMSOrderState, OMS_STATE_TRANSITIONS

logger = logging.getLogger(__name__)


class OMSStateMachine:
    def transition(self, current: OMSOrderState, target: OMSOrderState) -> OMSOrderState:
        allowed = OMS_STATE_TRANSITIONS.get(current, set())
        if target not in allowed:
            logger.warning("Invalid state transition: %s -> %s", current, target)
            return current
        return target

    def can_transition(self, current: OMSOrderState, target: OMSOrderState) -> bool:
        return target in OMS_STATE_TRANSITIONS.get(current, set())

    def is_terminal(self, state: OMSOrderState) -> bool:
        return state in (OMSOrderState.FILLED, OMSOrderState.CANCELLED, OMSOrderState.REJECTED, OMSOrderState.EXPIRED)

    def is_active(self, state: OMSOrderState) -> bool:
        return state in (OMSOrderState.NEW, OMSOrderState.VALIDATED, OMSOrderState.QUEUED, OMSOrderState.SENT, OMSOrderState.PENDING, OMSOrderState.PARTIAL)


state_machine = OMSStateMachine()
