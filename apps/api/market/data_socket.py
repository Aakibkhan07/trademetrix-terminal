import asyncio
import json
import logging
from datetime import datetime
from typing import Callable, Dict, List, Set

from core.models import Tick, Exchange

logger = logging.getLogger(__name__)


class SharedDataSocket:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._subscribers: Dict[str, List[Callable]] = {}
        self._broker_feeds: Dict[str, asyncio.Task] = {}
        self._running = False

    async def start(self):
        self._running = True
        logger.info("SharedDataSocket started")

    async def stop(self):
        self._running = False
        for task in self._broker_feeds.values():
            task.cancel()
        self._broker_feeds.clear()
        logger.info("SharedDataSocket stopped")

    def subscribe(self, symbol: str, callback: Callable[[Tick], None]) -> None:
        if symbol not in self._subscribers:
            self._subscribers[symbol] = []
        self._subscribers[symbol].append(callback)

    def unsubscribe(self, symbol: str, callback: Callable) -> None:
        if symbol in self._subscribers:
            self._subscribers[symbol] = [cb for cb in self._subscribers[symbol] if cb is not callback]
            if not self._subscribers[symbol]:
                del self._subscribers[symbol]

    async def broadcast_tick(self, tick: Tick) -> None:
        callbacks = self._subscribers.get(tick.symbol, []) + self._subscribers.get("*", [])
        for cb in callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(tick)
                else:
                    cb(tick)
            except Exception as e:
                logger.error(f"Tick callback error: {e}", exc_info=True)

    @property
    def subscribed_symbols(self) -> Set[str]:
        return set(self._subscribers.keys()) - {"*"}


shared_socket = SharedDataSocket()
