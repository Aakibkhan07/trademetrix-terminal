import asyncio
import logging
import random
from collections.abc import Callable
from typing import Any

from core.models import Tick
from market.data_socket import shared_socket
from market.observability import market_metrics

logger = logging.getLogger(__name__)


class SubscriptionManager:
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
        self._subscriptions: dict[str, set[Callable]] = {}
        self._active_feeds: dict[str, asyncio.Task] = {}
        self._reconnect_backoff: dict[str, int] = {}
        self._health_task: asyncio.Task | None = None
        self._running = False
        self._max_backoff = 60

    async def start(self):
        self._running = True
        self._health_task = asyncio.create_task(self._health_loop())
        logger.info("SubscriptionManager started")

    async def stop(self):
        self._running = False
        if self._health_task:
            self._health_task.cancel()
            self._health_task = None
        await self.stop_all_feeds()
        self._subscriptions.clear()
        logger.info("SubscriptionManager stopped")

    def subscribe(self, symbol: str, callback: Callable[[Tick], Any]) -> None:
        if symbol not in self._subscriptions:
            self._subscriptions[symbol] = set()
        self._subscriptions[symbol].add(callback)
        shared_socket.subscribe(symbol, callback)

    def unsubscribe(self, symbol: str, callback: Callable) -> None:
        if symbol in self._subscriptions:
            self._subscriptions[symbol].discard(callback)
            if not self._subscriptions[symbol]:
                del self._subscriptions[symbol]
        shared_socket.unsubscribe(symbol, callback)

    async def start_feed(self, user_id: str, broker_type: str, symbols: list[str]) -> None:
        if broker_type in self._active_feeds:
            logger.warning("Feed already running for %s, restarting", broker_type)
            await self.stop_feed(broker_type)

        self._reconnect_backoff[broker_type] = 0

        async def feed_runner():
            while self._running:
                try:
                    await shared_socket.start_broker_feed(user_id, broker_type, symbols)
                    self._reconnect_backoff[broker_type] = 0
                except RuntimeError as e:
                    if "already running" in str(e):
                        logger.info("Feed %s already running via direct call", broker_type)
                        return
                    logger.warning("Feed %s failed: %s, will retry", broker_type, e)
                except Exception as e:
                    logger.error("Feed %s error: %s", broker_type, e)

                if not self._running:
                    break

                backoff = self._reconnect_backoff.get(broker_type, 0)
                delay = min(2 ** backoff, self._max_backoff)
                delay = random.uniform(delay * 0.5, delay * 1.5)
                self._reconnect_backoff[broker_type] = backoff + 1
                logger.info("Reconnecting feed %s in %ds (attempt %d)", broker_type, delay, backoff + 1)
                market_metrics.increment_reconnects(broker_type)
                await asyncio.sleep(delay)

        task = asyncio.create_task(feed_runner())
        self._active_feeds[broker_type] = task
        logger.info("Feed manager started for %s with %d symbols", broker_type, len(symbols))

    async def stop_feed(self, broker_type: str) -> None:
        task = self._active_feeds.pop(broker_type, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await shared_socket.stop_broker_feed(broker_type)
        self._reconnect_backoff.pop(broker_type, None)
        logger.info("Feed stopped for %s", broker_type)

    async def stop_all_feeds(self) -> None:
        for broker_type in list(self._active_feeds.keys()):
            await self.stop_feed(broker_type)
        await shared_socket.stop_all_feeds()

    def get_active_symbols(self) -> set[str]:
        return set(self._subscriptions.keys())

    def get_feed_status(self) -> dict:
        return {
            "active_feeds": list(self._active_feeds.keys()),
            "subscriptions": {sym: len(cbs) for sym, cbs in self._subscriptions.items()},
            "reconnect_backoffs": dict(self._reconnect_backoff),
        }

    async def _health_loop(self):
        while self._running:
            await asyncio.sleep(30)
            dead_feeds = []
            for broker_type, task in self._active_feeds.items():
                if task.done():
                    dead_feeds.append(broker_type)
                    logger.warning("Feed task dead for %s, awaiting reconnect", broker_type)
            if dead_feeds:
                logger.warning("Dead feeds detected: %s", dead_feeds)
            market_metrics.set_active_subscriptions(len(self._subscriptions))


subscription_manager = SubscriptionManager()
