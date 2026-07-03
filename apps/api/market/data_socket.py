import asyncio
import inspect
import logging
from collections.abc import Callable

from core.models import Tick
from market.observability import market_metrics

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
        self._subscribers: dict[str, list[Callable]] = {}
        self._broker_feeds: dict[str, asyncio.Task] = {}
        self._running = False
        self._active_connections = 0
        self._heartbeat_task: asyncio.Task | None = None

    @property
    def active_connections(self) -> int:
        return self._active_connections

    def increment_connections(self) -> None:
        self._active_connections += 1
        market_metrics.set_active_connections(self._active_connections)

    def decrement_connections(self) -> None:
        self._active_connections = max(0, self._active_connections - 1)
        market_metrics.set_active_connections(self._active_connections)

    async def start(self):
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("SharedDataSocket started")

    async def stop(self):
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        for task in self._broker_feeds.values():
            task.cancel()
        self._broker_feeds.clear()
        logger.info("SharedDataSocket stopped")

    async def _heartbeat_loop(self):
        while self._running:
            await asyncio.sleep(30)
            logger.debug("DataSocket heartbeat: %d active connections, %d subscribed symbols",
                         self._active_connections, len(self._subscribers))

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
        from market.cache import market_cache
        from market.observability import market_metrics

        market_cache.put_tick(tick)
        market_metrics.increment_ticks_processed(tick.broker or "unknown")

        callbacks = self._subscribers.get(tick.symbol, []) + self._subscribers.get("*", [])
        for cb in callbacks:
            try:
                if inspect.iscoroutinefunction(cb):
                    await cb(tick)
                else:
                    cb(tick)
            except Exception as e:
                logger.error(f"Tick callback error: {e}", exc_info=True)

    async def start_broker_feed(self, user_id: str, broker_type: str, symbols: list[str]) -> None:
        if broker_type in self._broker_feeds:
            logger.warning(f"Broker feed already running for {broker_type}")
            raise RuntimeError(f"Broker feed already running for {broker_type}")

        from brokers import get_broker
        from core.db import async_supabase, get_supabase
        from core.security import decrypt_broker_credentials

        supabase = get_supabase()
        cred = await async_supabase(lambda: supabase.table("broker_credentials").select("*").eq("user_id", user_id).eq("broker", broker_type).single().execute())
        if not cred.data:
            raise RuntimeError(f"No broker credentials found for {broker_type}")

        row = cred.data
        raw_token = decrypt_broker_credentials(row["encrypted_access_token"]) if row.get("encrypted_access_token") else ""
        if not raw_token:
            raise RuntimeError(f"No access_token stored for {broker_type} — user must re-authenticate via OAuth")

        adapter_cls = get_broker(broker_type)
        adapter = adapter_cls()
        await adapter.authenticate({
            "client_id": decrypt_broker_credentials(row["encrypted_api_key"]),
            "secret_key": decrypt_broker_credentials(row["encrypted_secret_key"]),
            "access_token": raw_token,
        })

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
        task.add_done_callback(lambda _: self._broker_feeds.pop(broker_type, None))
        self._broker_feeds[broker_type] = task
        logger.info(f"Broker feed started for {broker_type} with {len(symbols)} symbols")

    async def stop_broker_feed(self, broker_type: str) -> None:
        task = self._broker_feeds.pop(broker_type, None)
        if task:
            task.cancel()
            logger.info(f"Broker feed stopped for {broker_type}")

    async def stop_all_feeds(self) -> None:
        for broker_type in list(self._broker_feeds.keys()):
            await self.stop_broker_feed(broker_type)

    @property
    def subscribed_symbols(self) -> set[str]:
        return set(self._subscribers.keys()) - {"*"}

    def get_stats(self) -> dict:
        return {
            "active_connections": self._active_connections,
            "subscribed_symbols": len(self._subscribers),
            "running_feeds": list(self._broker_feeds.keys()),
            "heartbeat_running": self._heartbeat_task is not None and not self._heartbeat_task.done(),
        }


shared_socket = SharedDataSocket()
