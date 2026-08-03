"""Generic observability wiring glue (SDK v2 Phase 4).

This module composes the Phase 3 building blocks (event bus, health service,
metrics registry) into a live observability surface without ever embedding a
broker name.  Broker-specific pieces (a transport snapshot for Fyers, an auth
provider) register into these generic containers from their provider modules:
    - :class:`TransportMetricSource` — generic adapter over ``HttpTransport``.
    - :func:`breaker_state_bridge` — turns circuit-breaker callbacks into
      health reports + typed audit events (and still drives the prometheus
      gauge).
    - :func:`wire_default_observability` one-call composition for app startup.
"""
from __future__ import annotations

from typing import Any, Callable

from brokers.sdk.events import AuditEventBus, BrokerEventKind
from brokers.sdk.health import BrokerHealthService
from brokers.sdk.metrics import BrokerMetrics, MetricSource
from brokers.sdk.transport import HttpTransport

from brokers.sdk.metrics import (
    CACHE_HIT_RATIO,
    DEDUP_HIT_RATIO,
    RATE_LIMIT_UTILIZATION,
    REQUESTS_TOTAL,
    REST_LATENCY_MS,
    RETRY_TOTAL,
    WEBSOCKET_LATENCY_MS,
)

_CIRCUIT_STATE_EVENT = {
    "open": BrokerEventKind.CIRCUIT_OPEN,
    "closed": BrokerEventKind.CIRCUIT_CLOSED,
    "half_open": None,
}


class TransportMetricSource(MetricSource):
    """Metric source backed by any :class:`HttpTransport` (generic, no broker branch).

    ``transport`` may be an instance or a zero-arg callable returning one —
    the latter lets the source track the live transport for a broker.
    """

    def __init__(self, broker: str, transport) -> None:
        self.broker = broker
        self._transport = transport

    def _resolve(self):
        if callable(self._transport) and not isinstance(self._transport, HttpTransport):
            return self._transport()
        return self._transport

    def raw_values(self) -> dict[str, Any]:
        raw: dict[str, Any] = {}
        try:
            transport = self._resolve()
            if transport is None:
                return raw
            snap = transport.snapshot()
            endpoints = snap.get("endpoints", []) or []
            raw[REQUESTS_TOTAL] = float(sum(e.get("calls", 0) or 0 for e in endpoints))
            raw["failure_total"] = float(
                sum(
                    (e.get("failures", 0) or 0) + (e.get("waf_blocked", 0) or 0)
                    for e in endpoints
                )
            )
            raw[RETRY_TOTAL] = float(sum(e.get("retries", 0) or 0 for e in endpoints))
            cache_hits = float(sum(e.get("cache_hits", 0) or 0 for e in endpoints))
            dedup_hits = float(sum(e.get("dedup_hits", 0) or 0 for e in endpoints))
            calls = float(sum(e.get("calls", 0) or 0 for e in endpoints))
            raw[CACHE_HIT_RATIO] = round(cache_hits / calls, 4) if calls else 0.0
            raw[DEDUP_HIT_RATIO] = round(dedup_hits / calls, 4) if calls else 0.0
            used = float(snap.get("used_last_minute", 0) or 0)
            budget = float(snap.get("budget_rpm", 0) or 0)
            raw[RATE_LIMIT_UTILIZATION] = (
                round(100.0 * used / budget, 2) if budget else 0.0
            )
        except Exception:
            pass
        # transport.health() adds rest latency + rate limit detail when available
        try:
            transport = self._resolve()
            if transport is None:
                return raw
            health = transport.health()
            if isinstance(health, dict):
                avg = health.get("avg_latency_ms")
                if avg:
                    raw[REST_LATENCY_MS] = float(avg)
                rl = health.get("rate_limit")
                if isinstance(rl, dict):
                    used = float(rl.get("used_last_minute", 0) or 0)
                    budget = float(rl.get("budget_rpm", 0) or 0)
                    if budget:
                        raw[RATE_LIMIT_UTILIZATION] = round(100.0 * used / budget, 2)
        except Exception:
            pass
        return raw


def breaker_state_bridge(
    event_bus: AuditEventBus | None = None,
    health_service: BrokerHealthService | None = None,
    metrics: BrokerMetrics | None = None,
) -> Callable[[str, str], None]:
    """Return a ``(name, state)`` callback for ``set_breaker_state_callback``.

    Composes: prometheus gauge (existing behavior preserved) + optional health
    report + optional bus events. When a subscription is created on the metrics
    registry inside a health service the returned callback reuses them.
    """

    def bridge(name: str, state: str) -> None:
        # 1) existing prometheus gauge behaviour (kept intact)
        try:
            from core.prometheus import on_breaker_state_change

            on_breaker_state_change(name, state)
        except Exception:
            pass
        broker = name[len("broker_"):] if name.startswith("broker_") else name
        if not broker:
            return
        # 2) health report
        if health_service is not None:
            try:
                health_service.report_circuit(broker, is_open=(state == "open"))
            except Exception:
                pass
        # 3) bus events (CIRCUIT_OPEN / CIRCUIT_CLOSED)
        kind = _CIRCUIT_STATE_EVENT.get(state)
        if event_bus is not None and kind is not None:
            try:
                event_bus.emit(
                    kind,
                    broker=broker,
                    message=f"Circuit breaker {name} -> {state}",
                    severity="error" if state == "open" else "info",
                )
            except Exception:
                pass

    return bridge


def wire_default_observability() -> BrokerMetrics:
    """One-call setup: attach default sinks, bridge breakers, bind metrics.

    Idempotent enough for app startup + tests. Returns the module-level
    ``default_broker_metrics`` after wiring it to the default health service.
    """
    from brokers.sdk.events import audit_bus, install_default_sinks
    from brokers.sdk.health import default_health_service
    from brokers.sdk.metrics import default_broker_metrics

    install_default_sinks()
    default_health_service.attach_event_listener()
    # Provider glue: brokers register their live sources here (additive).
    for _broker_module in ("fyers_provider",):
        try:
            if _broker_module == "fyers_provider":
                from brokers.fyers_provider import register_fyers_observability

                register_fyers_observability()
        except Exception:
            pass
    try:
        from core.resilience import set_breaker_state_callback

        set_breaker_state_callback(
            breaker_state_bridge(
                event_bus=audit_bus,
                health_service=default_health_service,
                metrics=default_broker_metrics,
            )
        )
    except Exception:
        pass
    return default_broker_metrics