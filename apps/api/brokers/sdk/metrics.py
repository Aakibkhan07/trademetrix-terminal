"""Unified broker observability surface (SDK v2 Phase 4).

Exposes one broker-agnostic metrics contract as a flat, serialisable snapshot:

- request count / success rate / failure rate / retry count
- circuit breaker state, WebSocket status, auth state, token refresh count
- order / REST / WebSocket latency
- cache hit ratio / dedup hit ratio / rate-limit utilisation

Producers register ``MetricSource`` objects per broker-name — they live in broker
providers (never behind an ``if broker == ...`` here), so this module stays
purely generic and unit-testable with tiny fakes.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from brokers.sdk.health import BrokerHealthService, BrokerHealthState

# Well-known metric keys (single vocabulary shared by health endpoints & UI).
REQUESTS_TOTAL = "requests_total"
SUCCESS_RATE = "success_rate"
FAILURE_RATE = "failure_rate"
RETRY_TOTAL = "retry_total"
CIRCUIT_OPEN = "circuit_open"
WEBSOCKET_CONNECTED = "websocket_connected"
AUTH_OK = "auth_ok"
HEALTH_STATE = "health_state"
TOKEN_REFRESH_TOTAL = "token_refresh_total"
ORDER_LATENCY_MS = "order_latency_ms"
REST_LATENCY_MS = "rest_latency_ms"
WEBSOCKET_LATENCY_MS = "websocket_latency_ms"
CACHE_HIT_RATIO = "cache_hit_ratio"
DEDUP_HIT_RATIO = "dedup_hit_ratio"
RATE_LIMIT_UTILIZATION = "rate_limit_utilization"

METRIC_KEYS: tuple[str, ...] = (
    REQUESTS_TOTAL,
    SUCCESS_RATE,
    FAILURE_RATE,
    RETRY_TOTAL,
    TOKEN_REFRESH_TOTAL,
    ORDER_LATENCY_MS,
    REST_LATENCY_MS,
    WEBSOCKET_LATENCY_MS,
    CACHE_HIT_RATIO,
    DEDUP_HIT_RATIO,
    RATE_LIMIT_UTILIZATION,
)


def _ratio(hits: float, total: float) -> float:
    return round(hits / total, 4) if total else 0.0


class MetricSource:
    """One broker's provider of raw metric values.

    ``snapshot()`` returns a dict of raw counters/rates using the well-known
    keys above (fields present are overlaid onto defaults; absent fields keep
    their computed value). Implementations live in broker providers.
    """

    broker: str = ""

    def raw_values(self) -> dict[str, Any]:
        return {}


@dataclass
class BrokerMetricSnapshot:
    broker: str
    metrics: dict[str, Any]
    health_state: str = "disconnected"
    source_ok: bool = True
    registered: bool = False
    sampled_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "broker": self.broker,
            "health_state": self.health_state,
            "sampled_at": round(self.sampled_at, 3),
            "source_ok": self.source_ok,
            "registered": self.registered,
            "metrics": {k: round(float(v), 4) for k, v in self.metrics.items()},
        }


class BrokerMetrics:
    """Thread-safe registry of :class:`MetricSource` per broker + snapshot renderer.

    The renderer combines the broker health service state with the registered
    source's raw values; it never branches on broker identity.
    """

    def __init__(self, health_service: BrokerHealthService | None = None) -> None:
        self._health_service = health_service or BrokerHealthService()
        self._sources: dict[str, MetricSource] = {}
        self._token_refresh_counts: dict[str, int] = {}
        self._lock = threading.Lock()

    # -- registration -------------------------------------------------------

    def register(self, broker: str, source: MetricSource) -> None:
        with self._lock:
            self._sources[broker] = source

    def unregister(self, broker: str) -> None:
        with self._lock:
            self._sources.pop(broker, None)

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._sources)

    # -- event-driven counters ----------------------------------------------

    def record_event(self, broker: str, kind: str) -> None:
        if kind in ("token_refresh", "token_refreshed"):
            with self._lock:
                self._token_refresh_counts[broker] = self._token_refresh_counts.get(broker, 0) + 1

    def token_refresh_count(self, broker: str) -> int:
        with self._lock:
            return self._token_refresh_counts.get(broker, 0)

    # -- rendering ------------------------------------------------------------

    def _defaults(self) -> dict[str, float]:
        return {
            REQUESTS_TOTAL: 0.0,
            SUCCESS_RATE: 0.0,
            FAILURE_RATE: 0.0,
            RETRY_TOTAL: 0.0,
            TOKEN_REFRESH_TOTAL: 0.0,
            ORDER_LATENCY_MS: 0.0,
            REST_LATENCY_MS: 0.0,
            WEBSOCKET_LATENCY_MS: 0.0,
            CACHE_HIT_RATIO: 0.0,
            DEDUP_HIT_RATIO: 0.0,
            RATE_LIMIT_UTILIZATION: 0.0,
            "failure_total": 0.0,
        }

    def snapshot(self, broker: str) -> BrokerMetricSnapshot:
        health = self._health_service.get(broker)
        source = self._sources.get(broker)
        metrics = self._defaults()
        source_ok = True

        if source is not None:
            try:
                overlay = source.raw_values()
                for key, value in overlay.items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        metrics[key] = float(value)
            except Exception:
                source_ok = False

        if health is not None:
            metrics[CIRCUIT_OPEN] = 1.0 if health.circuit_open else 0.0
            metrics[WEBSOCKET_CONNECTED] = 1.0 if health.ws_healthy else 0.0
            metrics[AUTH_OK] = 1.0 if health.auth_ok else 0.0
            # success rate from live counters when a source reported totals
            total = metrics[REQUESTS_TOTAL]
            if total > 0 and source is not None:
                metrics[SUCCESS_RATE] = _ratio(total - metrics.get("failure_total", 0.0), total)
                metrics[FAILURE_RATE] = _ratio(metrics.get("failure_total", 0.0), total)

        metrics[TOKEN_REFRESH_TOTAL] = float(self.token_refresh_count(broker))
        # derive ws latency from health components when present
        if health is not None:
            detail = health.components.get("ws_latency_ms")
            if detail is not None:
                try:
                    metrics[WEBSOCKET_LATENCY_MS] = float(detail)
                except (TypeError, ValueError):
                    pass

        state = health.state if health else BrokerHealthState.DISCONNECTED
        return BrokerMetricSnapshot(
            broker=broker,
            metrics=metrics,
            health_state=state.value,
            source_ok=source_ok,
            registered=broker in self._sources,
            sampled_at=time.time(),
        )

    def snapshot_all(self) -> dict[str, dict[str, Any]]:
        return {name: self.snapshot(name).to_dict() for name in self.names()}

    @property
    def health_service(self) -> BrokerHealthService:
        return self._health_service

    def attach_health_listener(self) -> None:
        """Subscribe metrics to the audit event bus for token-refresh counting."""
        bus = getattr(self._health_service, "_event_bus", None)
        if bus is None:
            return
        bus.subscribe(self._on_event)

    def _on_event(self, event) -> None:
        if event.broker:
            self.record_event(event.broker, event.kind.value)


default_broker_metrics: BrokerMetrics = BrokerMetrics()