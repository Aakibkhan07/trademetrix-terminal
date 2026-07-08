import time
import asyncio
from collections import defaultdict, deque


class RuntimeMetrics:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._evaluation_count: int = 0
        self._signals_generated: int = 0
        self._signals_rejected: int = 0
        self._errors: int = 0
        self._latencies: deque = deque(maxlen=10000)
        self._errors_by_strategy: dict[str, int] = defaultdict(int)
        self._signals_by_strategy: dict[str, int] = defaultdict(int)
        self._strategy_states: dict[str, str] = {}
        self._start_time: float = time.time()

    def record_evaluation(self, strategy_id: str, latency_ms: float):
        with self._lock:
            self._evaluation_count += 1
            self._latencies.append(latency_ms)

    def record_signal(self, strategy_id: str):
        with self._lock:
            self._signals_generated += 1
            self._signals_by_strategy[strategy_id] += 1

    def record_signal_rejected(self, strategy_id: str):
        with self._lock:
            self._signals_rejected += 1

    def record_error(self, strategy_id: str):
        with self._lock:
            self._errors += 1
            self._errors_by_strategy[strategy_id] += 1

    def set_strategy_state(self, strategy_id: str, state: str):
        with self._lock:
            self._strategy_states[strategy_id] = state

    @property
    def stats(self) -> dict:
        with self._lock:
            avg_latency = sum(self._latencies) / max(len(self._latencies), 1)
            return {
                "total_evaluations": self._evaluation_count,
                "signals_generated": self._signals_generated,
                "signals_rejected": self._signals_rejected,
                "signals_by_strategy": dict(self._signals_by_strategy),
                "errors": self._errors,
                "errors_by_strategy": dict(self._errors_by_strategy),
                "avg_evaluation_latency_ms": round(avg_latency, 2),
                "max_latency_ms": round(max(self._latencies), 2) if self._latencies else 0,
                "active_strategies": sum(1 for s in self._strategy_states.values() if s == "RUNNING"),
                "strategy_states": dict(self._strategy_states),
                "uptime_seconds": round(time.time() - self._start_time, 2),
            }


runtime_metrics = RuntimeMetrics()
