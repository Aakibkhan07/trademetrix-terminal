import time
from collections import defaultdict
from threading import Lock


class PortfolioMetrics:
    def __init__(self):
        self._lock = Lock()
        self._sync_count: int = 0
        self._sync_failures: int = 0
        self._reconciliation_count: int = 0
        self._reconciliation_drifts: int = 0
        self._sync_latencies: list[float] = []
        self._pnl_latencies: list[float] = []
        self._broker_sync_count: dict[str, int] = defaultdict(int)
        self._last_sync_time: float = 0.0

    def record_sync(self, broker: str, latency_ms: float, success: bool):
        with self._lock:
            self._sync_count += 1
            self._broker_sync_count[broker] += 1
            self._sync_latencies.append(latency_ms)
            self._last_sync_time = time.time()
            if not success:
                self._sync_failures += 1

    def record_reconciliation(self, drift_detected: bool):
        with self._lock:
            self._reconciliation_count += 1
            if drift_detected:
                self._reconciliation_drifts += 1

    def record_pnl_update(self, latency_ms: float):
        with self._lock:
            self._pnl_latencies.append(latency_ms)

    @property
    def stats(self) -> dict:
        with self._lock:
            avg_sync = sum(self._sync_latencies) / max(len(self._sync_latencies), 1)
            avg_pnl = sum(self._pnl_latencies) / max(len(self._pnl_latencies), 1)
            return {
                "total_syncs": self._sync_count,
                "sync_failures": self._sync_failures,
                "sync_success_rate": (
                    round((self._sync_count - self._sync_failures) / max(self._sync_count, 1) * 100, 2)
                ),
                "avg_sync_latency_ms": round(avg_sync, 2),
                "total_reconciliations": self._reconciliation_count,
                "drifts_detected": self._reconciliation_drifts,
                "avg_pnl_update_latency_ms": round(avg_pnl, 2),
                "broker_sync_counts": dict(self._broker_sync_count),
                "last_sync_time": self._last_sync_time,
            }


portfolio_metrics = PortfolioMetrics()
