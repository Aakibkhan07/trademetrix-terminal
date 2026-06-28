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

    async def start_broker_feed(self, user_id: str, broker_type: str, symbols: list[str]) -> None:
        if broker_type in self._broker_feeds:
            logger.warning(f"Broker feed already running for {broker_type}")
            return

        from brokers import get_broker
        from brokers.token_manager import TokenManager

        token_manager = TokenManager(user_id, broker_type)
        session = await token_manager.get_session()

        adapter_cls = get_broker(broker_type)
        adapter = adapter_cls()
        await adapter.authenticate(session)

        async def feed_runner():
            try:
                await adapter.stream(symbols, self.broadcast_tick)
            except asyncio.CancelledError:
                logger.info(f"Broker feed {broker_type} cancelled")
            except Exception as e:
                logger.error(f"Broker feed {broker_type} failed: {e}")
            finally:
                await adapter.disconnect()

        task = asyncio.create_task(feed_runner())
        self._broker_feeds[broker_type] = task
        logger.info(f"Broker feed started for {broker_type} with {len(symbols)} symbols")

    async def stop_broker_feed(self, broker_type: str) -> None:
        task = self._broker_feeds.pop(broker_type, None)
        if task:
            task.cancel()
            logger.info(f"Broker feed stopped for {broker_type}")

    @property
    def subscribed_symbols(self) -> Set[str]:
        return set(self._subscribers.keys()) - {"*"}


shared_socket = SharedDataSocket()
