import logging

from execution.event_bus import execution_event_bus, ExecutionEvent
from portfolio.manager import portfolio_manager

logger = logging.getLogger(__name__)


class PortfolioEventSubscriber:
    def __init__(self):
        self._subscribed = False

    def subscribe(self):
        if self._subscribed:
            return
        execution_event_bus.subscribe("OrderPlaced", self._on_order_placed)
        execution_event_bus.subscribe("OrderFilled", self._on_order_filled)
        execution_event_bus.subscribe("OrderCancelled", self._on_order_changed)
        execution_event_bus.subscribe("OrderRejected", self._on_order_changed)
        self._subscribed = True
        logger.info("PortfolioEventSubscriber subscribed to execution events")

    async def _on_order_placed(self, event: ExecutionEvent):
        if event.user_id and event.broker:
            await portfolio_manager.refresh(event.user_id, event.broker)

    async def _on_order_filled(self, event: ExecutionEvent):
        if event.user_id and event.broker:
            await portfolio_manager.refresh(event.user_id, event.broker)

    async def _on_order_changed(self, event: ExecutionEvent):
        if event.user_id and event.broker:
            portfolio_manager.invalidate_cache(event.user_id, event.broker)


portfolio_event_subscriber = PortfolioEventSubscriber()
