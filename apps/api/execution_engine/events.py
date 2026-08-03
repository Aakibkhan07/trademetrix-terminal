"""Canonical typed execution domain event bus (Execution Engine v1.0).

The engine owns one typed, thread-safe, async-first domain bus that carries
every meaningful lifecycle event across the execution domains: order,
execution, trade, position, portfolio and risk. It is the spine of the engine —
consumers (Trade Manager, Position Manager, P&L Engine, Portfolio Engine,
metrics sink, structured logs) subscribe per domain and react without coupling
to producers.

Design notes:
- Thread-safe: producers may publish from broker websocket threads, paper
  paths and the API loop alike. When the bus is started on a loop, publishing
  from another thread is marshalled through ``call_soon_threadsafe``; before
  startup, events are dispatched inline (ordering preserved for sync
  handlers).
- Async-first: coroutine handlers are awaited in FIFO order by a single
  dispatcher task, so per-key ordering is deterministic.
- Sequence ids are assigned at publish time under a lock; every event carries
  a correlation id (inherited, else derived from ``client_order_id``, else a
  fresh uuid) so a trade can be traced end-to-end.
- Ring buffer of recent events for debugging/analytics.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ExecutionDomain(StrEnum):
    ORDER = "order"
    EXECUTION = "execution"
    TRADE = "trade"
    POSITION = "position"
    PORTFOLIO = "portfolio"
    RISK = "risk"


class ExecutionEventType(StrEnum):
    ORDER_SUBMITTED = "order.submitted"
    ORDER_VALIDATED = "order.validated"
    ORDER_QUEUED = "order.queued"
    ORDER_SENT = "order.sent"
    ORDER_ACCEPTED = "order.accepted"
    ORDER_PENDING = "order.pending"
    ORDER_PARTIALLY_FILLED = "order.partially_filled"
    ORDER_FILLED = "order.filled"
    ORDER_MODIFIED = "order.modified"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_REJECTED = "order.rejected"
    ORDER_EXPIRED = "order.expired"
    ORDER_FAILED = "order.failed"
    EXECUTION_VALIDATED = "execution.validated"
    EXECUTION_RETRY = "execution.retry"
    EXECUTION_RESULT = "execution.result"
    TRADE_EXECUTED = "trade.executed"
    POSITION_OPENED = "position.opened"
    POSITION_UPDATED = "position.updated"
    POSITION_CLOSED = "position.closed"
    PORTFOLIO_SNAPSHOT = "portfolio.snapshot"
    PORTFOLIO_REVALUED = "portfolio.revalued"
    RISK_DECISION = "risk.decision"


_EVENT_DOMAIN: dict[ExecutionEventType, ExecutionDomain] = {
    ExecutionEventType.ORDER_SUBMITTED: ExecutionDomain.ORDER,
    ExecutionEventType.ORDER_VALIDATED: ExecutionDomain.ORDER,
    ExecutionEventType.ORDER_QUEUED: ExecutionDomain.ORDER,
    ExecutionEventType.ORDER_SENT: ExecutionDomain.ORDER,
    ExecutionEventType.ORDER_ACCEPTED: ExecutionDomain.ORDER,
    ExecutionEventType.ORDER_PENDING: ExecutionDomain.ORDER,
    ExecutionEventType.ORDER_PARTIALLY_FILLED: ExecutionDomain.ORDER,
    ExecutionEventType.ORDER_FILLED: ExecutionDomain.ORDER,
    ExecutionEventType.ORDER_MODIFIED: ExecutionDomain.ORDER,
    ExecutionEventType.ORDER_CANCELLED: ExecutionDomain.ORDER,
    ExecutionEventType.ORDER_REJECTED: ExecutionDomain.ORDER,
    ExecutionEventType.ORDER_EXPIRED: ExecutionDomain.ORDER,
    ExecutionEventType.ORDER_FAILED: ExecutionDomain.ORDER,
    ExecutionEventType.EXECUTION_VALIDATED: ExecutionDomain.EXECUTION,
    ExecutionEventType.EXECUTION_RETRY: ExecutionDomain.EXECUTION,
    ExecutionEventType.EXECUTION_RESULT: ExecutionDomain.EXECUTION,
    ExecutionEventType.TRADE_EXECUTED: ExecutionDomain.TRADE,
    ExecutionEventType.POSITION_OPENED: ExecutionDomain.POSITION,
    ExecutionEventType.POSITION_UPDATED: ExecutionDomain.POSITION,
    ExecutionEventType.POSITION_CLOSED: ExecutionDomain.POSITION,
    ExecutionEventType.PORTFOLIO_SNAPSHOT: ExecutionDomain.PORTFOLIO,
    ExecutionEventType.PORTFOLIO_REVALUED: ExecutionDomain.PORTFOLIO,
    ExecutionEventType.RISK_DECISION: ExecutionDomain.RISK,
}


def domain_for(event_type: ExecutionEventType) -> ExecutionDomain:
    return _EVENT_DOMAIN[event_type]


class ExecutionEngineEvent(BaseModel):
    """One immutable typed execution-domain event."""

    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    domain: ExecutionDomain = ExecutionDomain.ORDER
    type: ExecutionEventType = ExecutionEventType.ORDER_SUBMITTED
    sequence: int = 0
    correlation_id: str = ""
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str = ""
    broker: str = ""
    account: str = ""
    order_id: str = ""
    client_order_id: str = ""
    broker_order_id: str = ""
    symbol: str = ""
    side: str = ""
    quantity: int = 0
    filled_quantity: int = 0
    price: float = 0.0
    avg_price: float = 0.0
    state: str = ""
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "sequence": self.sequence,
            "timestamp": self.occurred_at.isoformat(),
            "domain": self.domain.value,
            "event": self.type.value,
            "correlation_id": self.correlation_id,
            "user_id": self.user_id,
            "broker": self.broker,
            "account": self.account,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "broker_order_id": self.broker_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "filled_quantity": self.filled_quantity,
            "price": self.price,
            "avg_price": self.avg_price,
            "state": self.state,
            "message": self.message,
            "payload": self.payload,
        }


def order_event(
    event_type: ExecutionEventType,
    *,
    user_id: str = "",
    broker: str = "",
    order_id: str = "",
    client_order_id: str = "",
    broker_order_id: str = "",
    correlation_id: str = "",
    symbol: str = "",
    side: str = "",
    quantity: int = 0,
    filled_quantity: int = 0,
    price: float = 0.0,
    avg_price: float = 0.0,
    state: str = "",
    message: str = "",
    payload: dict[str, Any] | None = None,
) -> ExecutionEngineEvent:
    return ExecutionEngineEvent(
        domain=_EVENT_DOMAIN[event_type],
        type=event_type,
        correlation_id=correlation_id,
        user_id=user_id,
        broker=broker,
        order_id=order_id,
        client_order_id=client_order_id,
        broker_order_id=broker_order_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        filled_quantity=filled_quantity,
        price=price,
        avg_price=avg_price,
        state=state,
        message=message,
        payload=payload or {},
    )


def trade_event(
    *,
    user_id: str = "",
    broker: str = "",
    order_id: str = "",
    client_order_id: str = "",
    broker_order_id: str = "",
    correlation_id: str = "",
    symbol: str = "",
    side: str = "",
    quantity: int = 0,
    price: float = 0.0,
    message: str = "",
    payload: dict[str, Any] | None = None,
) -> ExecutionEngineEvent:
    return ExecutionEngineEvent(
        domain=ExecutionDomain.TRADE,
        type=ExecutionEventType.TRADE_EXECUTED,
        correlation_id=correlation_id,
        user_id=user_id,
        broker=broker,
        order_id=order_id,
        client_order_id=client_order_id,
        broker_order_id=broker_order_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        avg_price=price,
        message=message,
        payload=payload or {},
    )


def position_event(
    event_type: ExecutionEventType,
    *,
    user_id: str = "",
    broker: str = "",
    symbol: str = "",
    side: str = "",
    quantity: int = 0,
    avg_price: float = 0.0,
    correlation_id: str = "",
    message: str = "",
    payload: dict[str, Any] | None = None,
) -> ExecutionEngineEvent:
    return ExecutionEngineEvent(
        domain=ExecutionDomain.POSITION,
        type=event_type,
        correlation_id=correlation_id,
        user_id=user_id,
        broker=broker,
        symbol=symbol,
        side=side,
        quantity=quantity,
        avg_price=avg_price,
        message=message,
        payload=payload or {},
    )


def portfolio_event(
    event_type: ExecutionEventType,
    *,
    user_id: str = "",
    broker: str = "",
    correlation_id: str = "",
    message: str = "",
    payload: dict[str, Any] | None = None,
) -> ExecutionEngineEvent:
    return ExecutionEngineEvent(
        domain=ExecutionDomain.PORTFOLIO,
        type=event_type,
        correlation_id=correlation_id,
        user_id=user_id,
        broker=broker,
        message=message,
        payload=payload or {},
    )


def risk_event(
    *,
    user_id: str = "",
    broker: str = "",
    correlation_id: str = "",
    decision: str = "",
    message: str = "",
    payload: dict[str, Any] | None = None,
) -> ExecutionEngineEvent:
    return ExecutionEngineEvent(
        domain=ExecutionDomain.RISK,
        type=ExecutionEventType.RISK_DECISION,
        correlation_id=correlation_id,
        user_id=user_id,
        broker=broker,
        state=decision,
        message=message,
        payload=payload or {},
    )


Handler = Callable[[ExecutionEngineEvent], Any]


class ExecutionEngineBus:
    """Fan-out bus with per-domain subscribers, ordered dispatch and a ring buffer."""

    def __init__(self, max_buffered: int = 2000):
        self._subscribers: dict[ExecutionDomain, list[Handler]] = {
            d: [] for d in ExecutionDomain
        }
        self._lock = threading.RLock()
        self._seq = itertools.count(1)
        self._last_seq = 0
        self._buffer: deque[ExecutionEngineEvent] = deque(maxlen=max_buffered)
        self._inline_tasks: set[asyncio.Task] = set()
        self._queue: asyncio.Queue[ExecutionEngineEvent] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: int | None = None
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind the bus to a running loop and start the dispatcher task."""
        with self._lock:
            if self._task is not None and not self._task.done():
                return
            self._loop = loop
            self._loop_thread = threading.get_ident()
            self._queue = asyncio.Queue()
            self._task = loop.create_task(self._dispatcher())

    async def stop(self) -> None:
        """Cancel the dispatcher and drain anything already queued."""
        with self._lock:
            task, self._task = self._task, None
            queue = self._queue
            loop = self._loop
            self._loop = None
            self._loop_thread = None
            self._queue = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if queue is not None and not queue.empty():
            pending: list[ExecutionEngineEvent] = []
            while not queue.empty():
                pending.append(queue.get_nowait())
            for event in pending:
                await self._dispatch(event)

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------
    def subscribe(self, domain: ExecutionDomain | ExecutionEventType, handler: Handler) -> None:
        d = domain_for(domain) if isinstance(domain, ExecutionEventType) else domain
        with self._lock:
            if handler not in self._subscribers[d]:
                self._subscribers[d].append(handler)

    def unsubscribe(self, domain: ExecutionDomain | ExecutionEventType, handler: Handler) -> None:
        d = domain_for(domain) if isinstance(domain, ExecutionEventType) else domain
        with self._lock:
            if handler in self._subscribers[d]:
                self._subscribers[d].remove(handler)

    def subscriber_count(self, domain: ExecutionDomain | None = None) -> int:
        with self._lock:
            if domain is None:
                return sum(len(v) for v in self._subscribers.values())
            d = domain_for(domain) if isinstance(domain, ExecutionEventType) else domain
            return len(self._subscribers[d])

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------
    def publish(self, event: ExecutionEngineEvent) -> ExecutionEngineEvent:
        """Thread-safe publish. Dispatches inline pre-startup, otherwise enqueues."""
        self._finalize(event)
        queue = self._queue
        loop = self._loop
        if queue is not None and loop is not None and not loop.is_closed():
            if threading.get_ident() == self._loop_thread:
                queue.put_nowait(event)
            else:
                loop.call_soon_threadsafe(queue.put_nowait, event)
        else:
            self._dispatch_inline(event)
        return event

    async def apublish(self, event: ExecutionEngineEvent) -> ExecutionEngineEvent:
        """Publish and await dispatch when the bus is not started (tests, scripts)."""
        self._finalize(event)
        if self._queue is not None and self._task is not None and not self._task.done():
            self.publish(event)
            return event
        await self._dispatch(event)
        await self._drain_inline()
        return event

    def _finalize(self, event: ExecutionEngineEvent) -> bool:
        """Assign sequence/correlation and buffer the event.

        Returns True when the event was newly finalized (first call); publish
        paths call this defensively, so repeated calls must be no-ops.
        """
        if event.sequence > 0 and event.correlation_id:
            return False
        with self._lock:
            if event.sequence <= 0:
                event.sequence = next(self._seq)
                self._last_seq = event.sequence
            if not event.correlation_id:
                event.correlation_id = event.client_order_id or uuid.uuid4().hex
            self._buffer.append(event)
        return True

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    async def _dispatcher(self) -> None:
        queue = self._queue
        if queue is None:
            return
        try:
            while True:
                event = await queue.get()
                try:
                    await self._dispatch(event)
                except Exception:
                    logger.exception("Execution event dispatch failed: %s", event.type)
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            raise

    async def _dispatch(self, event: ExecutionEngineEvent) -> None:
        with self._lock:
            handlers = list(self._subscribers.get(event.domain, []))
        for handler in handlers:
            result = handler(event)
            if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
                try:
                    await result
                except Exception:
                    logger.exception(
                        "Async execution event handler %s failed for %s",
                        getattr(handler, "__name__", handler),
                        event.type,
                    )
            elif isinstance(result, BaseException):
                logger.error(
                    "Execution event handler %s raised for %s: %r",
                    getattr(handler, "__name__", handler),
                    event.type,
                    result,
                )

    def _dispatch_inline(self, event: ExecutionEngineEvent) -> None:
        with self._lock:
            handlers = list(self._subscribers.get(event.domain, []))
        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
                    try:
                        task = asyncio.get_running_loop().create_task(_consume(result))
                        with self._lock:
                            self._inline_tasks.add(task)
                        task.add_done_callback(self._inline_tasks.discard)
                    except RuntimeError:
                        logger.warning(
                            "Dropping async handler %s for %s: bus not started",
                            getattr(handler, "__name__", handler),
                            event.type,
                        )
            except Exception:
                logger.exception(
                    "Execution event handler %s failed for %s",
                    getattr(handler, "__name__", handler),
                    event.type,
                )

    async def _drain_inline(self) -> None:
        """Await any fire-and-forget cascade spawned by inline dispatch."""
        while True:
            with self._lock:
                pending = list(self._inline_tasks)
            if not pending:
                return
            await asyncio.gather(*pending, return_exceptions=True)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._buffer)[-limit:]
        return [e.to_dict() for e in events]

    @property
    def buffered(self) -> int:
        with self._lock:
            return len(self._buffer)

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()

    def reset_subscribers(self) -> None:
        """Test hook: drop every subscriber (incl. the default LoggingSink)."""
        with self._lock:
            for d in self._subscribers:
                self._subscribers[d] = []
            self._inline_tasks.clear()

    @property
    def last_sequence(self) -> int:
        with self._lock:
            return self._last_seq


async def _consume(awaitable: Any) -> None:
    try:
        await awaitable
    except Exception:
        logger.exception("Execution event async task failed")


_LOG_RECORD = (
    "execution.event event=%s domain=%s severity=%s user=%s broker=%s msg=%s corr=%s"
)


class LoggingSink:
    """Structured one-line log per domain event."""

    def __init__(self, logger_: logging.Logger | None = None):
        self.logger = logger_ or logging.getLogger("execution_engine.events")

    def __call__(self, event: ExecutionEngineEvent) -> None:
        severity = "warning" if event.type.value.endswith((".rejected", ".failed", ".cancelled", ".expired")) else "info"
        self.logger.log(
            getattr(logging, severity.upper(), logging.INFO),
            _LOG_RECORD,
            event.type.value,
            event.domain.value,
            severity,
            event.user_id or "-",
            event.broker or "-",
            event.message or "-",
            event.correlation_id or "-",
        )


execution_bus = ExecutionEngineBus()
execution_bus.subscribe(ExecutionDomain.ORDER, LoggingSink())

_LEGACY_BRIDGE_WIRED = False
_ENGINE_BRIDGE_WIRED = False


def bridge_engine_events() -> None:
    """Publish engine TRADE/POSITION/PORTFOLIO events onto the legacy bus.

    The per-user HTTP SSE endpoint (``/api/v1/events/stream``) subscribes to
    the legacy ``execution_event_bus``, so this bridge carries the canonical
    engine events (trade.executed, position.*, portfolio.*) to the live UI
    without any new streaming infrastructure. Loop-safe: these engine event
    names are not keys of the legacy ``_TYPE_MAP``, so the legacy→engine
    forward bridge drops them on the way back. Idempotent.
    """
    global _ENGINE_BRIDGE_WIRED
    if _ENGINE_BRIDGE_WIRED:
        return
    try:
        from execution.event_bus import execution_event_bus
    except Exception as e:  # pragma: no cover
        logger.warning("Legacy execution bus unavailable, engine bridge skipped: %s", e)
        return

    _UI_DOMAINS = {ExecutionDomain.TRADE, ExecutionDomain.POSITION, ExecutionDomain.PORTFOLIO}

    def _back_forward(event: "ExecutionEngineEvent") -> None:
        if event.domain not in _UI_DOMAINS or not event.user_id:
            return
        try:
            from execution.event_bus import ExecutionEvent, fire_and_forget
            from execution.models import ExecutionState

            try:
                state = ExecutionState(event.state)
            except Exception:
                state = ExecutionState.NEW

            legacy = ExecutionEvent(
                event_type=event.type.value,
                execution_request_id=event.client_order_id or event.correlation_id or "",
                user_id=event.user_id,
                broker=event.broker,
                symbol=event.symbol,
                side=event.side,
                state=state,
                message=event.message,
                payload={"engine_event": event.to_dict()},
            )
            fire_and_forget(execution_event_bus.publish(legacy))
        except Exception:  # pragma: no cover
            logger.warning("Engine event bridge publish failed for %s", event.domain, exc_info=True)

    try:
        execution_bus.subscribe(ExecutionDomain.TRADE, _back_forward)
        execution_bus.subscribe(ExecutionDomain.POSITION, _back_forward)
        execution_bus.subscribe(ExecutionDomain.PORTFOLIO, _back_forward)
    except Exception:  # pragma: no cover
        logger.warning("Engine event bridge subscription failed", exc_info=True)
        return
    _ENGINE_BRIDGE_WIRED = True


def bridge_legacy_events() -> None:
    """Forward the legacy string-typed execution bus into the typed domain bus.

    Wired once at engine init so existing producers (risk/manager.py, OMS)
    emit canonical events without any change to their code. Idempotent: the
    legacy bus dedupes subscribers by callback identity, and a module flag
    prevents double-wiring after an init/shutdown/init cycle.
    """
    global _LEGACY_BRIDGE_WIRED
    if _LEGACY_BRIDGE_WIRED:
        return
    try:
        from execution.event_bus import execution_event_bus
    except Exception as e:  # pragma: no cover
        logger.warning("Legacy execution bus unavailable, bridge skipped: %s", e)
        return

    _TYPE_MAP: dict[str, tuple[ExecutionEventType, ExecutionDomain]] = {
        "RiskDecision": (ExecutionEventType.RISK_DECISION, ExecutionDomain.RISK),
        "OrderRejected": (ExecutionEventType.ORDER_REJECTED, ExecutionDomain.ORDER),
        "OrderPending": (ExecutionEventType.ORDER_PENDING, ExecutionDomain.ORDER),
        "OrderCancelled": (ExecutionEventType.ORDER_CANCELLED, ExecutionDomain.ORDER),
        "OrderExpired": (ExecutionEventType.ORDER_EXPIRED, ExecutionDomain.ORDER),
        # OMS fills publish "OrderCompleted" (direct + reconciled paths)
        "OrderCompleted": (ExecutionEventType.ORDER_FILLED, ExecutionDomain.ORDER),
        # paper broker fill events
        "PaperOrderFilled": (ExecutionEventType.ORDER_FILLED, ExecutionDomain.ORDER),
        "PaperOrderPartiallyFilled": (ExecutionEventType.ORDER_PARTIALLY_FILLED, ExecutionDomain.ORDER),
        "PaperOrderPending": (ExecutionEventType.ORDER_PENDING, ExecutionDomain.ORDER),
    }

    def _forward(legacy_event) -> None:
        event_type = getattr(legacy_event, "event_type", "")
        mapped = _TYPE_MAP.get(event_type)
        if mapped is None:
            return
        etype, domain = mapped
        payload = dict(getattr(legacy_event, "payload", None) or {})
        payload.setdefault("source", "legacy_execution_bus")
        data: dict[str, Any] = {
            "domain": domain,
            "type": etype,
            "correlation_id": payload.get("correlation_id", ""),
            "user_id": getattr(legacy_event, "user_id", "") or "",
            "broker": getattr(legacy_event, "broker", "") or "",
            "symbol": getattr(legacy_event, "symbol", "") or payload.get("symbol", "") or "",
            "side": getattr(legacy_event, "side", "") or payload.get("side", "") or "",
            "quantity": int(payload.get("quantity") or 0),
            "client_order_id": getattr(legacy_event, "execution_request_id", "") or "",
            "message": getattr(legacy_event, "message", "") or "",
            "payload": payload,
        }
        if etype in (ExecutionEventType.ORDER_FILLED, ExecutionEventType.ORDER_PARTIALLY_FILLED):
            fill = payload.get("fill") or {}
            data["order_id"] = str(payload.get("order_id") or payload.get("oms_order_id") or "")
            data["broker_order_id"] = str(payload.get("broker_order_id") or payload.get("order_id") or "")
            data["filled_quantity"] = int(payload.get("filled_quantity") or fill.get("filled_quantity") or 0)
            data["avg_price"] = float(payload.get("average_price") or fill.get("filled_price") or payload.get("price") or 0.0)
        execution_bus.publish(ExecutionEngineEvent(**data))

    try:
        execution_event_bus.subscribe("*", _forward)
    except Exception as e:  # pragma: no cover
        logger.warning("Legacy event bridge subscription failed: %s", e)
        return
    _LEGACY_BRIDGE_WIRED = True
