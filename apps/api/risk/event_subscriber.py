import logging

from execution.event_bus import execution_event_bus, ExecutionEvent
from risk.manager import risk_manager

logger = logging.getLogger(__name__)


class RiskEventSubscriber:
    def __init__(self):
        self._subscribed = False

    def subscribe(self):
        if self._subscribed:
            return
        execution_event_bus.subscribe("OrderPlaced", self._on_order_placed)
        execution_event_bus.subscribe("OrderRejected", self._on_order_rejected)
        execution_event_bus.subscribe("RiskSettingsChanged", self._on_settings_changed)
        self._subscribed = True
        logger.info("RiskEventSubscriber subscribed to execution events")

    async def _on_order_placed(self, event: ExecutionEvent):
        risk_manager.invalidate_cache(event.user_id)

    async def _on_order_rejected(self, event: ExecutionEvent):
        risk_manager.invalidate_cache(event.user_id)

    async def _on_settings_changed(self, event: ExecutionEvent):
        risk_manager.invalidate_cache(event.user_id)


risk_event_subscriber = RiskEventSubscriber()
