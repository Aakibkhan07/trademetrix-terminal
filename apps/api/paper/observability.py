import time
from threading import Lock


class PaperMetrics:
    def __init__(self):
        self._lock = Lock()
        self._orders: int = 0
        self._fills: int = 0
        self._rejected: int = 0
        self._cancelled: int = 0
        self._total_pnl: float = 0.0
        self._total_commission: float = 0.0
        self._latencies: list[float] = []
        self._errors: int = 0
        self._start_time: float = time.time()

    def record_order(self):
        with self._lock:
            self._orders += 1

    def record_fill(self):
        with self._lock:
            self._fills += 1

    def record_rejected(self):
        with self._lock:
            self._rejected += 1

    def record_cancelled(self):
        with self._lock:
            self._cancelled += 1

    def record_pnl(self, pnl: float):
        with self._lock:
            self._total_pnl += pnl

    def record_commission(self, commission: float):
        with self._lock:
            self._total_commission += commission

    def record_latency(self, ms: float):
        with self._lock:
            self._latencies.append(ms)

    def record_error(self):
        with self._lock:
            self._errors += 1

    @property
    def stats(self) -> dict:
        with self._lock:
            avg_latency = sum(self._latencies) / max(len(self._latencies), 1)
            return {
                "total_orders": self._orders,
                "filled_orders": self._fills,
                "rejected_orders": self._rejected,
                "cancelled_orders": self._cancelled,
                "total_pnl": round(self._total_pnl, 2),
                "total_commission": round(self._total_commission, 2),
                "avg_latency_ms": round(avg_latency, 2),
                "errors": self._errors,
                "uptime_seconds": round(time.time() - self._start_time, 2),
            }


paper_metrics = PaperMetrics()
