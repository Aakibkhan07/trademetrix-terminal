"""Unified broker health service (SDK v2 Phase 3).

Tracks the logical health of every broker through a small set of component
signals (REST, WebSocket, auth, rate-limit, circuit) and derives one of the
canonical ``BrokerHealthState`` values.  The service is broker-agnostic — it
never branches on broker name; brokers plug in by supplying component signals.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from brokers.sdk.events import AuditEventBus, BrokerEventKind


class BrokerHealthState(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    DEGRADED = "degraded"
    AUTHENTICATION_FAILED = "authentication_failed"
    RATE_LIMITED = "rate_limited"
    CIRCUIT_OPEN = "circuit_open"
    WEBSOCKET_HEALTHY = "websocket_healthy"
    REST_HEALTHY = "rest_healthy"


@dataclass
class BrokerHealth:
    broker: str
    state: BrokerHealthState = BrokerHealthState.DISCONNECTED
    rest_healthy: bool = False
    ws_healthy: bool = False
    auth_ok: bool = True
    rate_limited: bool = False
    circuit_open: bool = False
    degraded: bool = False
    last_error: str = ""
    updated_at: float = 0.0
    components: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "broker": self.broker,
            "state": self.state.value,
            "rest_healthy": self.rest_healthy,
            "ws_healthy": self.ws_healthy,
            "auth_ok": self.auth_ok,
            "rate_limited": self.rate_limited,
            "circuit_open": self.circuit_open,
            "degraded": self.degraded,
            "last_error": self.last_error,
            "updated_at": round(self.updated_at, 3),
            "components": self.components,
            "healthy": self.state in (BrokerHealthState.CONNECTED, BrokerHealthState.WEBSOCKET_HEALTHY, BrokerHealthState.REST_HEALTHY),
        }


def derive_health(
    *,
    rest_healthy: bool = False,
    ws_healthy: bool = False,
    auth_ok: bool = True,
    rate_limited: bool = False,
    circuit_open: bool = False,
    degraded: bool = False,
    auth_failed: bool = False,
) -> BrokerHealthState:
    """Derive a canonical state from component signals (priority order)."""
    if auth_failed:
        return BrokerHealthState.AUTHENTICATION_FAILED
    if circuit_open:
        return BrokerHealthState.CIRCUIT_OPEN
    if rate_limited:
        return BrokerHealthState.RATE_LIMITED
    if not auth_ok:
        return BrokerHealthState.AUTHENTICATION_FAILED
    if degraded:
        return BrokerHealthState.DEGRADED
    if ws_healthy and rest_healthy:
        return BrokerHealthState.CONNECTED
    if ws_healthy:
        return BrokerHealthState.WEBSOCKET_HEALTHY
    if rest_healthy:
        return BrokerHealthState.REST_HEALTHY
    return BrokerHealthState.DISCONNECTED


class BrokerHealthService:
    """Tracks and serves unified health for all registered brokers.

    Thread-safe: component signals may arrive from asyncio tasks, background
    loops, or sync callbacks (e.g. a circuit-breaker state callback).
    """

    def __init__(self, event_bus: AuditEventBus | None = None, max_components: int = 12) -> None:
        self._event_bus = event_bus
        self._max_components = max_components
        self._lock = threading.Lock()
        self._states: dict[str, BrokerHealth] = {}

    # -- component signal entry points ---------------------------------------

    def report_rest_health(self, broker: str, healthy: bool, *, account: str = "", detail: Any = None) -> BrokerHealth:
        return self._update(broker, rest_healthy=healthy, account=account, detail=detail)

    def report_ws_health(self, broker: str, healthy: bool, *, account: str = "", detail: Any = None) -> BrokerHealth:
        return self._update(broker, ws_healthy=healthy, account=account, detail=detail)

    def report_auth(self, broker: str, ok: bool, *, account: str = "", error: str = "") -> BrokerHealth:
        return self._update(broker, auth_ok=ok, error=error, account=account)

    def report_rate_limited(self, broker: str, limited: bool, *, account: str = "", error: str = "") -> BrokerHealth:
        return self._update(broker, rate_limited=limited, error=error, account=account)

    def report_circuit(self, broker: str, is_open: bool, *, account: str = "", error: str = "") -> BrokerHealth:
        return self._update(broker, circuit_open=is_open, error=error, account=account)

    def report_degraded(self, broker: str, degraded: bool, *, account: str = "", error: str = "") -> BrokerHealth:
        return self._update(broker, degraded=degraded, error=error, account=account)

    # -- internals -----------------------------------------------------------

    def _update(
        self,
        broker: str,
        *,
        rest_healthy: bool | None = None,
        ws_healthy: bool | None = None,
        auth_ok: bool | None = None,
        rate_limited: bool | None = None,
        circuit_open: bool | None = None,
        degraded: bool | None = None,
        account: str = "",
        error: str = "",
        detail: Any = None,
    ) -> BrokerHealth:
        with self._lock:
            current = self._states.get(broker)
            if current is None:
                current = BrokerHealth(broker=broker, state=BrokerHealthState.DISCONNECTED, updated_at=time.time())
            if rest_healthy is not None:
                current.rest_healthy = rest_healthy
            if ws_healthy is not None:
                current.ws_healthy = ws_healthy
            if auth_ok is not None:
                current.auth_ok = auth_ok
            if rate_limited is not None:
                current.rate_limited = rate_limited
            if circuit_open is not None:
                current.circuit_open = circuit_open
            if degraded is not None:
                current.degraded = degraded
            if account:
                current.components["account"] = account
            if detail is not None:
                current.components["detail"] = detail
            if error:
                current.last_error = error
            current.updated_at = time.time()
            current.components = dict(list(current.components.items())[: self._max_components])
            previous_state = current.state
            current.state = derive_health(
                rest_healthy=current.rest_healthy,
                ws_healthy=current.ws_healthy,
                auth_ok=current.auth_ok,
                rate_limited=current.rate_limited,
                circuit_open=current.circuit_open,
                degraded=current.degraded,
                auth_failed=not current.auth_ok,
            )
            if current.state != previous_state:
                self._emit_state_change(broker, previous_state, current.state, error)
            self._states[broker] = current
            return current

    def _emit_state_change(self, broker: str, previous: BrokerHealthState, new: BrokerHealthState, error: str) -> None:
        if self._event_bus is not None:
            self._event_bus.emit(
                BrokerEventKind.HEALTH_CHANGED,
                message=f"{broker} health: {previous.value} -> {new.value}",
                broker=broker,
                payload={"from": previous.value, "to": new.value, "error": error},
                severity="warning"
                if new in (BrokerHealthState.AUTHENTICATION_FAILED, BrokerHealthState.CIRCUIT_OPEN)
                else "info",
            )

    # -- query / snapshot ----------------------------------------------------

    def get(self, broker: str) -> BrokerHealth | None:
        with self._lock:
            return self._states.get(broker)

    def states(self) -> dict[str, BrokerHealthState]:
        with self._lock:
            return {k: v.state for k, v in self._states.items()}

    def count(self) -> int:
        with self._lock:
            return len(self._states)

    def snapshot_all(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {k: v.to_dict() for k, v in sorted(self._states.items())}

    def summary(self) -> dict[str, dict[str, Any]]:
        """Per-broker summary dict for the unified ``/brokers/health`` endpoint."""
        return self.snapshot_all()

    # -- event-bus wiring (optional) -----------------------------------------

    def attach_event_listener(self) -> None:
        """Subscribe this service to the broker event bus (idempotent)."""
        if self._event_bus is None:
            return
        self._event_bus.subscribe(self._on_event)

    def _on_event(self, event) -> None:
        kind = event.kind
        broker = event.broker or ""
        if not broker:
            return
        if kind == BrokerEventKind.AUTH_FAILED:
            self.report_auth(broker, ok=False, error=event.message)
        elif kind == BrokerEventKind.TOKEN_REFRESH:
            self.report_auth(broker, ok=True)
        elif kind == BrokerEventKind.RATE_LIMITED:
            self.report_rate_limited(broker, True, error=event.message)
        elif kind == BrokerEventKind.CIRCUIT_OPEN:
            self.report_circuit(broker, True, error=event.message)
        elif kind == BrokerEventKind.CIRCUIT_CLOSED:
            self.report_circuit(broker, False)
        elif kind == BrokerEventKind.WEBSOCKET_CONNECTED:
            self.report_ws_health(broker, True)
        elif kind == BrokerEventKind.WEBSOCKET_DISCONNECTED:
            self.report_ws_health(broker, False, error=event.message)


default_health_service = BrokerHealthService()