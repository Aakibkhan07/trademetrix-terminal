import time
from collections import defaultdict
from threading import Lock


class OMSMetrics:
    def __init__(self):
        self._lock = Lock()
        self._orders_submitted: int = 0
        self._orders_filled: int = 0
        self._orders_cancelled: int = 0
        self._orders_rejected: int = 0
        self._orders_expired: int = 0
        self._queue_depth: int = 0
        self._retry_count: int = 0
        self._fill_latencies: list[float] = []
        self._broker_latencies: dict[str, list[float]] = defaultdict(list)
        self._bracket_orders: int = 0
        self._oco_orders: int = 0
        self._errors: int = 0
        self._start_time: float = time.time()

    def record_submitted(self):
        with self._lock:
            self._orders_submitted += 1

    def record_filled(self, latency_ms: float):
        with self._lock:
            self._orders_filled += 1
            self._fill_latencies.append(latency_ms)

    def record_cancelled(self):
        with self._lock:
            self._orders_cancelled += 1

    def record_rejected(self):
        with self._lock:
            self._orders_rejected += 1

    def record_expired(self):
        with self._lock:
            self._orders_expired += 1

    def record_queue_depth(self, depth: int):
        with self._lock:
            self._queue_depth = depth

    def record_retry(self):
        with self._lock:
            self._retry_count += 1

    def record_broker_latency(self, broker: str, ms: float):
        with self._lock:
            self._broker_latencies[broker].append(ms)

    def record_bracket(self):
        with self._lock:
            self._bracket_orders += 1

    def record_oco(self):
        with self._lock:
            self._oco_orders += 1

    def record_error(self):
        with self._lock:
            self._errors += 1

    @property
    def stats(self) -> dict:
        with self._lock:
            avg_fill = sum(self._fill_latencies) / max(len(self._fill_latencies), 1)
            broker_lat = {}
            for b, l in self._broker_latencies.items():
                broker_lat[b] = {
                    "avg": round(sum(l) / len(l), 2),
                    "count": len(l),
                    "max": round(max(l), 2),
                }
            return {
                "orders_submitted": self._orders_submitted,
                "orders_filled": self._orders_filled,
                "orders_cancelled": self._orders_cancelled,
                "orders_rejected": self._orders_rejected,
                "orders_expired": self._orders_expired,
                "queue_depth": self._queue_depth,
                "retry_count": self._retry_count,
                "avg_fill_latency_ms": round(avg_fill, 2),
                "broker_latency": broker_lat,
                "bracket_orders": self._bracket_orders,
                "oco_orders": self._oco_orders,
                "errors": self._errors,
                "uptime_seconds": round(time.time() - self._start_time, 2),
            }


oms_metrics = OMSMetrics()
