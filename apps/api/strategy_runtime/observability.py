"""Runtime observability — metrics + structured lifecycle logs.

In-memory counters (health endpoint) plus best-effort Prometheus export
(metrics are only registered when ``core.prometheus`` is importable; tests and
bare imports stay side-effect free).
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


def _metrics() -> dict:
    try:
        from core import prometheus

        return prometheus
    except Exception:
        return None


class RuntimeObservability:
    def __init__(self) -> None:
        self._start = time.time()
        self.lifecycle_events: dict[str, int] = defaultdict(int)
        self.evaluations = 0
        self.signals = 0
        self.orders: dict[str, int] = defaultdict(int)
        self.errors = 0
        self.restarts = 0
        self.recovery_count = 0
        self.recovery_elapsed_ms = 0.0
        self.events: dict[str, int] = defaultdict(int)
        self._running: dict[str, float] = {}

    def set_running(self, strategy_id: str, running: bool) -> None:
        if running:
            self._running[strategy_id] = time.time()
        else:
            self._running.pop(strategy_id, None)
        prom = _metrics()
        if prom is not None and hasattr(prom, "strategy_runtime_running"):
            try:
                prom.strategy_runtime_running.set(len(self._running))
            except Exception:
                pass

    def record_lifecycle(self, state: str, strategy_id: str = "") -> None:
        self.lifecycle_events[state] += 1
        prom = _metrics()
        if prom is not None and hasattr(prom, "strategy_runtime_lifecycle_events_total"):
            try:
                prom.strategy_runtime_lifecycle_events_total.labels(state=state).inc()
            except Exception:
                pass
        logger.info("Runtime lifecycle: state=%s strategy_id=%s", state, strategy_id)

    def record_evaluation(self, latency_ms: float) -> None:
        self.evaluations += 1
        prom = _metrics()
        if prom is not None and hasattr(prom, "strategy_runtime_latency_seconds"):
            try:
                prom.strategy_runtime_latency_seconds.observe(latency_ms / 1000.0)
            except Exception:
                pass

    def record_signal(self) -> None:
        self.signals += 1

    def record_order(self, outcome: str) -> None:
        self.orders[outcome] += 1
        prom = _metrics()
        if prom is not None and hasattr(prom, "strategy_runtime_orders_total"):
            try:
                prom.strategy_runtime_orders_total.labels(outcome=outcome).inc()
            except Exception:
                pass

    def record_error(self) -> None:
        self.errors += 1
        prom = _metrics()
        if prom is not None and hasattr(prom, "strategy_runtime_errors_total"):
            try:
                prom.strategy_runtime_errors_total.inc()
            except Exception:
                pass

    def record_restart(self) -> None:
        self.restarts += 1
        prom = _metrics()
        if prom is not None and hasattr(prom, "strategy_runtime_restarts_total"):
            try:
                prom.strategy_runtime_restarts_total.inc()
            except Exception:
                pass

    def record_recovery(self, elapsed_ms: float) -> None:
        self.recovery_count += 1
        self.recovery_elapsed_ms = elapsed_ms
        prom = _metrics()
        if prom is not None and hasattr(prom, "strategy_runtime_recovery_seconds"):
            try:
                prom.strategy_runtime_recovery_seconds.observe(elapsed_ms / 1000.0)
            except Exception:
                pass

    def record_event(self, kind: str) -> None:
        self.events[kind] += 1

    def record_tick(self) -> None:
        prom = _metrics()
        if prom is not None and hasattr(prom, "strategy_runtime_ticks_total"):
            try:
                prom.strategy_runtime_ticks_total.inc()
            except Exception:
                pass

    def record_dropped(self) -> None:
        prom = _metrics()
        if prom is not None and hasattr(prom, "strategy_runtime_dropped_ticks_total"):
            try:
                prom.strategy_runtime_dropped_ticks_total.inc()
            except Exception:
                pass

    def snapshot(self) -> dict:
        return {
            "uptime_seconds": round(time.time() - self._start, 2),
            "running": sorted(self._running.keys()),
            "running_count": len(self._running),
            "lifecycle_events": dict(self.lifecycle_events),
            "evaluations": self.evaluations,
            "signals": self.signals,
            "orders": dict(self.orders),
            "errors": self.errors,
            "restarts": self.restarts,
            "recoveries": self.recovery_count,
            "last_recovery_elapsed_ms": self.recovery_elapsed_ms,
            "routed_events": dict(self.events),
        }


runtime_observability = RuntimeObservability()
