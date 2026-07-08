import time
import logging
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class MarketMetrics:
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
        self.reset()

    def reset(self) -> None:
        self._ticks_processed: dict[str, int] = defaultdict(int)
        self._total_ticks: int = 0
        self._errors: dict[str, int] = defaultdict(int)
        self._reconnects: dict[str, int] = defaultdict(int)
        self._latencies: deque = deque(maxlen=1000)
        self._active_connections: int = 0
        self._active_subscriptions: int = 0
        self._start_time: float = time.time()

    def increment_ticks_processed(self, broker: str) -> None:
        self._ticks_processed[broker] += 1
        self._total_ticks += 1

    def record_tick_latency(self, latency_ms: float) -> None:
        self._latencies.append(latency_ms)
        if len(self._latencies) > self._max_latency_samples:
            self._latencies.pop(0)

    def increment_errors(self, error_type: str) -> None:
        self._errors[error_type] += 1

    def increment_reconnects(self, broker: str) -> None:
        self._reconnects[broker] += 1

    def set_active_connections(self, count: int) -> None:
        self._active_connections = count

    def set_active_subscriptions(self, count: int) -> None:
        self._active_subscriptions = count

    def get_metrics(self) -> dict:
        avg_latency = 0.0
        p99_latency = 0.0
        if self._latencies:
            sorted_lats = sorted(self._latencies)
            avg_latency = round(sum(sorted_lats) / len(sorted_lats), 2)
            p99_idx = int(len(sorted_lats) * 0.99)
            p99_latency = round(sorted_lats[min(p99_idx, len(sorted_lats) - 1)], 2)

        return {
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "total_ticks": self._total_ticks,
            "ticks_per_broker": dict(self._ticks_processed),
            "active_connections": self._active_connections,
            "active_subscriptions": self._active_subscriptions,
            "errors": dict(self._errors),
            "reconnects": dict(self._reconnects),
            "latency_ms": {
                "avg": avg_latency,
                "p99": p99_latency,
                "samples": len(self._latencies),
            },
        }


market_metrics = MarketMetrics()
