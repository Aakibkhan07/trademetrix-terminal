"""Unified broker WebSocket layer (SDK v2 Phase 3).

One reusable, back end-agnostic WebSocket manager that every broker plugs into:
auto-reconnect with exponential backoff, heartbeats + latency monitoring,
subscription deduplication and resubscription, message routing and event
dispatch.  The shared module imports no websocket library — brokers supply a
``WebSocketBackend`` factory (e.g. wrapping ``websockets`` for Fyers), so this
stays fully generic and unit-testable with in-memory fakes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from brokers.sdk.events import AuditEventBus, BrokerEventKind

logger = logging.getLogger("brokers.sdk.websocket")

DEFAULT_HEARTBEAT_INTERVAL = 15.0
DEFAULT_HEARTBEAT_TIMEOUT = 10.0
DEFAULT_BACKOFF_BASE = 1.0
DEFAULT_BACKOFF_MAX = 60.0
DEFAULT_CONNECT_TIMEOUT = 10.0


@dataclass
class WSConfig:
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT
    heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL
    heartbeat_timeout: float = DEFAULT_HEARTBEAT_TIMEOUT
    backoff_base: float = DEFAULT_BACKOFF_BASE
    backoff_max: float = DEFAULT_BACKOFF_MAX
    backoff_factor: float = 2.0
    jitter: float = 0.25
    max_reconnects: int = 0        # 0 = retry forever
    read_poll_seconds: float = 0.5


@dataclass
class WSConnectionStats:
    """Rolling stats for one connection lifecycle of the manager."""

    connected_at: float = 0.0
    last_message_at: float = 0.0
    last_pong_at: float = 0.0
    messages_in: int = 0
    messages_out: int = 0
    reconnects: int = 0
    resubscribes: int = 0
    heartbeat_timeouts: int = 0
    latency_ms: float = 0.0          # EMA of ping->pong RTT
    last_error: str = ""
    _rtt_samples: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected_at > 0,
            "uptime_seconds": round(max(0.0, time.time() - self.connected_at), 1) if self.connected_at else 0.0,
            "messages_in": self.messages_in,
            "messages_out": self.messages_out,
            "reconnects": self.reconnects,
            "resubscribes": self.resubscribes,
            "heartbeat_timeouts": self.heartbeat_timeouts,
            "latency_ms": round(self.latency_ms, 2),
            "last_message_age_seconds": round(time.time() - self.last_message_at, 1) if self.last_message_at else 0.0,
            "last_error": self.last_error,
        }


class WebSocketBackend(Protocol):
    """What a broker must implement to plug into the manager (see fyers_ws.py)."""

    async def connect(self) -> None: ...

    async def send(self, data: str | bytes) -> None: ...

    async def recv(self) -> str | bytes | None: ...

    async def close(self) -> None: ...


class WebSocketManager:
    """Reconnecting, heartbeating, resubscribing WebSocket manager.

    ``backend_factory`` returns a fresh :class:`WebSocketBackend` per attempt.
    ``subscribe_payload(topics)`` returns the bytes to (re)send on connect.
    ``on_message`` is the dispatch entry; optional ``handlers`` route parsed
    JSON messages by their ``type`` field.
    """

    def __init__(
        self,
        backend_factory: Callable[[], WebSocketBackend],
        *,
        broker: str = "",
        account: str = "",
        subscribe_payload: Callable[[list[str]], Any] | None = None,
        on_message: Callable[[Any], Any] | None = None,
        handlers: dict[str, Callable[[dict], Any]] | None = None,
        on_state_change: Callable[[str], None] | None = None,
        event_bus: AuditEventBus | None = None,
        config: "WSConfig | None" = None,
    ) -> None:
        self.broker = broker
        self.account = account
        self._factory = backend_factory
        self._subscribe_payload = subscribe_payload
        self._on_message = on_message
        self._handlers = handlers or {}
        self._on_state_change = on_state_change
        self._event_bus = event_bus
        self.config = config or _DEFAULT_CONFIG

        self._topics: set[str] = set()
        self._backend: WebSocketBackend | None = None
        self._connected = False
        self._running = False
        self._task: asyncio.Task | None = None
        self.stats = WSConnectionStats()
        self._ping_seq = 0
        self._pending_ping_ts = 0.0

    # -- subscription (idempotent, deduplicated) ----------------------------

    def subscribe(self, topic: str) -> bool:
        """Add a subscription. Returns True only when newly subscribed."""
        if topic in self._topics:
            return False
        self._topics.add(topic)
        return True

    def unsubscribe(self, topic: str) -> bool:
        if topic in self._topics:
            self._topics.discard(topic)
            return True
        return False

    def topics(self) -> list[str]:
        return sorted(self._topics)

    def subscribed_count(self) -> int:
        return len(self._topics)

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        if self._backend is not None:
            try:
                await self._backend.close()
            except Exception:
                pass
        self._connected = False
        self._emit(BrokerEventKind.WEBSOCKET_DISCONNECTED, "manager stopped")

    async def _run(self) -> None:
        backoff = self.config.backoff_base
        while self._running:
            try:
                await self._connect_once()
                backoff = self.config.backoff_base
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if not self._running:
                    break
                self._connected = False
                logger.warning(
                    "WebSocket[%s] connection/lifecycle error: %s (reconnecting)", self.broker or "?", e
                )
                self._emit(
                    BrokerEventKind.WEBSOCKET_ERROR,
                    f"WebSocket {self.broker}: {e}",
                    severity="warning",
                )
                await self._retry_delay(backoff)
                backoff = min(backoff * self.config.backoff_factor, self.config.backoff_max)

    async def _retry_delay(self, backoff: float) -> None:
        jitter = random.uniform(-self.config.jitter, self.config.jitter)
        delay = max(0.1, backoff * (1 + jitter))
        await asyncio.sleep(delay)

    async def _connect_once(self) -> None:
        if self.config.max_reconnects and self.stats.reconnects >= self.config.max_reconnects:
            logger.error("WebSocket[%s] max reconnects reached, giving up", self.broker or "default")
            self._running = False
            return
        backend = self._factory()
        await asyncio.wait_for(backend.connect(), timeout=self.config.connect_timeout)
        self._backend = backend
        self._connected = True
        if self.stats.connected_at == 0:
            self.stats.connected_at = time.time()
        self.stats.reconnects += 1
        self._emit(BrokerEventKind.WEBSOCKET_CONNECTED, f"websocket {self.broker}:connected")
        self._state("connected")
        await self._resubscribe()
        await self._read_loop(backend)

    async def _resubscribe(self) -> None:
        if not self._topics:
            return
        if self._subscribe_payload is None:
            return
        payload = self._subscribe_payload(sorted(self._topics))
        await self._backend.send(payload if isinstance(payload, (str, bytes)) else str(payload))
        self.stats.messages_out += 1
        self.stats.resubscribes += 1
        logger.info("WebSocket[%s] resubscribed %d topics", self.broker or "default", len(self._topics))

    async def _read_loop(self, backend: WebSocketBackend) -> None:
        while self._running:
            try:
                msg = await asyncio.wait_for(backend.recv(), timeout=self.config.read_poll_seconds)
            except asyncio.TimeoutError:
                # No traffic: heartbeat management
                if self._heartbeat_due():
                    await self._send_ping()
                    if self._heartbeat_expired():
                        self.stats.heartbeat_timeouts += 1
                        raise ConnectionError("heartbeat timeout")
                continue
            except (ConnectionError, OSError, asyncio.CancelledError) as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                raise ConnectionError(f"recv failed: {e}") from e

            if msg is None:  # clean close from peer
                raise ConnectionError("peer closed")

            self.stats.last_message_at = time.time()
            self.stats.messages_in += 1
            self._dispatch(msg)

    def _heartbeat_due(self) -> bool:
        if self.config.heartbeat_interval <= 0 or self._pending_ping_ts:
            return False
        return (time.time() - self.stats.last_message_at) >= self.config.heartbeat_interval

    def _heartbeat_expired(self) -> bool:
        if not self._pending_ping_ts:
            return False
        return (time.time() - self._pending_ping_ts) >= self.config.heartbeat_timeout

    async def _send_ping(self) -> None:
        self._ping_seq += 1
        payload = {"type": "ping", "seq": self._ping_seq} if self.config.heartbeat_timeout else {"type": "ping", "seq": self._ping_seq}
        await self._backend.send(json_dumps(payload))
        self.stats.messages_out += 1
        self._pending_ping_ts = time.time()

    def _dispatch(self, msg: str | bytes) -> None:
        text = msg.decode("utf-8", "replace") if isinstance(msg, bytes) else msg
        try:
            data = json_loads(text)
        except (ValueError, TypeError):
            data = text
        if isinstance(data, dict) and data.get("type") == "pong":
            self._record_pong(data)
            return
        handler = self._handlers.get(msg_type(data)) if isinstance(data, dict) else None
        if handler is not None:
            try:
                handler(data)
            except Exception:
                logger.exception("WebSocket[%s] handler error", self.broker or "default")
            return
        if self._on_message is not None:
            try:
                self._on_message(data)
            except Exception:
                logger.exception("WebSocket[%s] on_message error", self.broker or "default")

    def _record_pong(self, data: dict) -> None:
        self.stats.last_pong_at = time.time()
        if self._pending_ping_ts:
            rtt = (time.time() - self._pending_ping_ts) * 1000
            self.stats.latency_ms = self._ema(rtt)
            self._pending_ping_ts = 0.0

    def _ema(self, rtt_ms: float) -> float:
        if self.stats._rtt_samples == 0:
            self.stats._rtt_samples = 1
            return rtt_ms
        self.stats._rtt_samples += 1
        alpha = 0.1
        return (alpha * rtt_ms) + ((1 - alpha) * self.stats.latency_ms)

    # -- health --------------------------------------------------------------

    def _state(self, state: str) -> None:
        if self._on_state_change is not None:
            try:
                self._on_state_change(state)
            except Exception:
                pass

    def _emit(self, kind: BrokerEventKind, message: str, severity: str = "info") -> None:
        if self._on_message is None and kind in (BrokerEventKind.WEBSOCKET_CONNECTED,):
            pass
        if self._event_bus is not None:
            self._event_bus.emit(
                kind,
                broker=self.broker,
                account=self.account,
                message=message,
                severity=severity,
            )

    def is_connected(self) -> bool:
        return self._connected

    def health(self) -> dict[str, Any]:
        return {
            "broker": self.broker,
            "account": self.account,
            "connected": self._connected,
            "running": self._running,
            "topics": len(self._topics),
            **self.stats.to_dict(),
        }


def json_dumps(obj: Any) -> str:
    return json.dumps(obj)


def json_loads(text: str) -> Any:
    return json.loads(text)


def msg_type(data: dict) -> str:
    return str(data.get("type", ""))


_DEFAULT_CONFIG = WSConfig()