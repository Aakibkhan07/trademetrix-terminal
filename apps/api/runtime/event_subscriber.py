import logging

from execution.event_bus import execution_event_bus, ExecutionEvent
from market.data_socket import shared_socket
from runtime.scheduler import scheduler

logger = logging.getLogger(__name__)


class RuntimeEventSubscriber:
    def __init__(self):
        self._subscribed = False

    def subscribe(self):
        if self._subscribed:
            return
        shared_socket.subscribe("*", self._on_tick)
        self._subscribed = True
        logger.info("RuntimeEventSubscriber subscribed to market ticks")

    async def _on_tick(self, tick):
        try:
            await scheduler.on_tick(tick)
        except Exception as e:
            logger.error("Runtime tick handler error: %s", e)

    async def _on_execution_event(self, event: ExecutionEvent):
        pass


runtime_event_subscriber = RuntimeEventSubscriber()
