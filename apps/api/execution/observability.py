import threading
import time
from collections import defaultdict

from execution.models import ExecutionMetrics


class ExecutionObservability:
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
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._metrics = ExecutionMetrics()
        self._latency_samples: list[float] = []
        self._broker_latency_samples: dict[str, list[float]] = defaultdict(list)

    def record_order_placed(self):
        with self._lock:
            self._metrics.orders_placed += 1

    def record_order_failed(self):
        with self._lock:
            self._metrics.orders_failed += 1

    def record_order_rejected(self):
        with self._lock:
            self._metrics.orders_rejected += 1

    def record_order_cancelled(self):
        with self._lock:
            self._metrics.orders_cancelled += 1

    def record_order_filled(self):
        with self._lock:
            self._metrics.orders_filled += 1

    def record_latency(self, latency_ms: float, broker: str = ""):
        with self._lock:
            self._latency_samples.append(latency_ms)
            if len(self._latency_samples) > 1000:
                self._latency_samples.pop(0)
            if broker:
                self._broker_latency_samples[broker].append(latency_ms)
                if len(self._broker_latency_samples[broker]) > 1000:
                    self._broker_latency_samples[broker].pop(0)
            avg = sum(self._latency_samples) / max(len(self._latency_samples), 1)
            self._metrics.average_latency_ms = round(avg, 2)
            for b, samples in self._broker_latency_samples.items():
                self._metrics.broker_latency_ms[b] = round(sum(samples) / max(len(samples), 1), 2)

    def record_retry(self):
        with self._lock:
            self._metrics.total_retries += 1

    def record_duplicate_prevented(self):
        with self._lock:
            self._metrics.duplicate_requests_prevented += 1

    def record_validation_failure(self):
        with self._lock:
            self._metrics.validation_failures += 1

    def record_broker_error(self, broker: str):
        with self._lock:
            self._metrics.broker_errors[broker] = self._metrics.broker_errors.get(broker, 0) + 1

    def get_metrics(self) -> ExecutionMetrics:
        return self._metrics

    def get_metrics_dict(self) -> dict:
        m = self._metrics
        return {
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "orders_placed": m.orders_placed,
            "orders_failed": m.orders_failed,
            "orders_rejected": m.orders_rejected,
            "orders_cancelled": m.orders_cancelled,
            "orders_filled": m.orders_filled,
            "average_latency_ms": m.average_latency_ms,
            "broker_latency_ms": m.broker_latency_ms,
            "total_retries": m.total_retries,
            "duplicate_requests_prevented": m.duplicate_requests_prevented,
            "validation_failures": m.validation_failures,
            "broker_errors": m.broker_errors,
        }


execution_observability = ExecutionObservability()
