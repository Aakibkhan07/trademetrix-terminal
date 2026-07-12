import time
from collections import defaultdict
from threading import Lock

from risk.models import RiskDecision


class RiskMetrics:
    def __init__(self):
        self._lock = Lock()
        self._total_evaluations: int = 0
        self._approved_count: int = 0
        self._warning_count: int = 0
        self._rejected_count: int = 0
        self._rule_counts: dict[str, int] = defaultdict(int)
        self._rule_latencies: dict[str, list[float]] = defaultdict(list)
        self._total_latency_ms: float = 0.0
        self._last_eval_time: float = 0.0

    def record_evaluation(self, decision: RiskDecision, results: list, total_latency_ms: float):
        with self._lock:
            self._total_evaluations += 1
            self._total_latency_ms += total_latency_ms
            self._last_eval_time = time.time()
            if decision == RiskDecision.APPROVED:
                self._approved_count += 1
            elif decision == RiskDecision.WARNING:
                self._warning_count += 1
            else:
                self._rejected_count += 1
            for r in results:
                self._rule_counts[r.rule] += 1
                self._rule_latencies[r.rule].append(r.latency_ms)

    @property
    def stats(self) -> dict:
        with self._lock:
            avg_latency = self._total_latency_ms / max(self._total_evaluations, 1)
            rule_stats = {}
            for rule, latencies in self._rule_latencies.items():
                rule_stats[rule] = {
                    "count": len(latencies),
                    "avg_latency_ms": sum(latencies) / len(latencies),
                    "max_latency_ms": max(latencies),
                }
            return {
                "total_evaluations": self._total_evaluations,
                "approved": self._approved_count,
                "warning": self._warning_count,
                "rejected": self._rejected_count,
                "avg_latency_ms": round(avg_latency, 2),
                "rule_stats": rule_stats,
                "last_eval_time": self._last_eval_time,
            }


risk_metrics = RiskMetrics()
