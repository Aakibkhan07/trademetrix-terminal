"""Typed broker audit event bus (SDK v2 Phase 3).

Every meaningful broker event becomes a typed :class:`BrokerAuditEvent` that
feeds logging, Prometheus metrics, the health service and a ring buffer for
future analytics.  This module is pure infrastructure — it never branches on
broker identity and imports nothing broker-specific.
"""
from __future__ import annotations

import itertools
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("brokers.sdk.events")


class BrokerEventKind(Enum):
    """Canonical broker lifecycle events (lower-case machine strings)."""

    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    TOKEN_REFRESH = "token_refresh"
    TOKEN_EXPIRED = "token_expired"
    AUTH_FAILED = "auth_failed"
    REAUTH_REQUIRED = "reauth_required"
    ORDER_SENT = "order_sent"
    ORDER_ACCEPTED = "order_accepted"
    ORDER_REJECTED = "order_rejected"
    ORDER_FILLED = "order_filled"
    ORDER_MODIFIED = "order_modified"
    ORDER_CANCELLED = "order_cancelled"
    POSITION_UPDATED = "position_updated"
    WEBSOCKET_CONNECTED = "websocket_connected"
    WEBSOCKET_DISCONNECTED = "websocket_disconnected"
    WEBSOCKET_ERROR = "websocket_error"
    WEBSOCKET_HEARTBEAT_TIMEOUT = "websocket_heartbeat_timeout"
    RATE_LIMITED = "rate_limited"
    WAF_BLOCKED = "waf_blocked"
    RETRY_EXHAUSTED = "retry_exhausted"
    CIRCUIT_OPEN = "circuit_open"
    CIRCUIT_CLOSED = "circuit_closed"
    HEALTH_CHANGED = "health_changed"


_SEVERITIES = {"info", "warning", "error"}


@dataclass(frozen=True)
class BrokerAuditEvent:
    """One immutable typed broker event."""

    kind: BrokerEventKind
    broker: str
    account: str = ""
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    severity: str = "info"
    timestamp: float = field(default_factory=time.time)
    sequence: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "event": self.kind.value,
            "broker": self.broker,
            "account": self.account,
            "severity": self.severity,
            "message": self.message,
            "correlation_id": self.correlation_id,
            "payload": self.payload,
        }


class AuditEventBus:
    """Fan-out event bus with optional ring buffer + ordered sequence ids.

    Synchronous by design so it can be driven from sync callbacks (e.g. the
    circuit-breaker state hook); async callers just ``await`` nothing extra.
    """

    def __init__(self, max_buffered: int = 0):
        self._subscribers: list[Callable[[BrokerAuditEvent], None]] = []
        self._buffer: deque[BrokerAuditEvent] = deque(maxlen=max_buffered or 0)
        self._seq = itertools.count(1)
        self._lock = threading.Lock()

    def subscribe(self, fn: Callable[[BrokerAuditEvent], None]) -> None:
        with self._lock:
            if fn not in self._subscribers:
                self._subscribers.append(fn)

    def unsubscribe(self, fn: Callable[[BrokerAuditEvent], None]) -> None:
        with self._lock:
            if fn in self._subscribers:
                self._subscribers.remove(fn)

    def emit(
        self,
        kind: BrokerEventKind,
        *,
        broker: str = "",
        account: str = "",
        message: str = "",
        payload: dict | None = None,
        correlation_id: str = "",
        severity: str = "info",
    ) -> BrokerAuditEvent:
        event = BrokerAuditEvent(
            kind=kind,
            broker=broker,
            account=account,
            message=message,
            payload=payload or {},
            correlation_id=correlation_id,
            severity=severity if severity in _SEVERITIES else "info",
            sequence=next(self._seq),
        )
        self.emit_event(event)
        return event

    def emit_event(self, event: BrokerAuditEvent) -> None:
        with self._lock:
            if self._buffer.maxlen:
                self._buffer.append(event)
            subscribers = list(self._subscribers)
        for fn in subscribers:
            try:
                fn(event)
            except Exception:
                logger.exception("Broker audit event sink %s failed", getattr(fn, "__name__", fn))

    def remove_buffer(self) -> None:
        with self._lock:
            self._buffer.clear()

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._buffer)[-limit:]
        return [e.to_dict() for e in events]

    @property
    def buffered(self) -> int:
        with self._lock:
            return len(self._buffer) if self._buffer.maxlen else 0

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()


# ---------------------------------------------------------------------------
# Built-in sinks
# ---------------------------------------------------------------------------

_LOG_RECORD = (
    "%s.event event=%s severity=%s broker=%s account=%s msg=%s corr=%s payload=%s"
)


class LoggingSink:
    """Structured one-line log per event at severity-mapped level."""

    def __init__(self, logger: logging.Logger | None = None, logger_name: str = ""):
        self.logger = logger or logging.getLogger(logger_name or "brokers.sdk.events")

    def __call__(self, event: BrokerAuditEvent) -> None:
        level = getattr(self.logger, event.severity, self.logger.info)
        level(
            _LOG_RECORD,
            event.broker or "broker",
            event.kind.value,
            event.severity,
            event.broker or "-",
            event.account or "-",
            event.message or "-",
            event.correlation_id or "-",
            event.payload,
        )


class MetricsSink:
    """Increments Prometheus counters (lazy import keeps deps optional)."""

    def __call__(self, event: BrokerAuditEvent) -> None:
        try:
            from core.prometheus import record_broker_event

            record_broker_event(event.broker or "unknown", event.kind.value)
        except Exception:
            pass


class BufferSink:
    """Wraps a bus's ring buffer for consumers that only want recent events."""

    def __init__(self, bus: AuditEventBus):
        self._bus = bus

    def __call__(self, event: BrokerAuditEvent) -> None:
        pass  # the bus already buffers; registered so consumers can rely on it


# ---------------------------------------------------------------------------
# Module-level default bus (wired once per process)
# ---------------------------------------------------------------------------

audit_bus = AuditEventBus(max_buffered=2000)


def install_default_sinks() -> None:
    """Attach logging + metrics sinks to the shared bus, idempotently."""
    audit_bus.subscribe(LoggingSink())
    audit_bus.subscribe(MetricsSink())


install_default_sinks()