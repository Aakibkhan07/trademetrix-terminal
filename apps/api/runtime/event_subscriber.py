import logging

from execution.event_bus import execution_event_bus, ExecutionEvent
from market.data_socket import shared_socket
from runtime.scheduler import scheduler

logger = logging.getLogger(__name__)


class RuntimeEventSubscriber:
    def __init__(self):
        self._subscribed = False
        self._subscribed_symbols: set[str] = set()

    def subscribe(self):
        if self._subscribed:
            return
        shared_socket.subscribe("*", self._on_tick)
        self._subscribed = True
        self._subscribed_symbols.add("*")
        logger.info("RuntimeEventSubscriber subscribed to market ticks")

    def unsubscribe(self):
        if not self._subscribed:
            return
        for symbol in list(self._subscribed_symbols):
            shared_socket.unsubscribe(symbol, self._on_tick)
        self._subscribed_symbols.clear()
        self._subscribed = False
        logger.info("RuntimeEventSubscriber unsubscribed from market ticks")

    async def _on_tick(self, tick):
        try:
            await scheduler.on_tick(tick)
        except Exception as e:
            logger.error("Runtime tick handler error: %s", e)


runtime_event_subscriber = RuntimeEventSubscriber()
