import os
import time
from typing import Any

from core.resilience import get_circuit_breaker_stats
from core.logging import get_request_stats

_start_time = time.time()


def get_uptime() -> float:
    return time.time() - _start_time


def get_system_metrics() -> dict[str, Any]:
    import psutil
    proc = psutil.Process(os.getpid())
    mem = proc.memory_info()
    return {
        "uptime_seconds": round(get_uptime(), 2),
        "cpu_percent": proc.cpu_percent(interval=0.1),
        "memory_rss_bytes": mem.rss,
        "memory_vms_bytes": mem.vms,
        "open_fds": proc.num_fds(),
        "threads": proc.num_threads(),
    }


def get_metrics() -> dict[str, Any]:
    return {
        "system": get_system_metrics(),
        "requests": get_request_stats(),
        "circuit_breakers": get_circuit_breaker_stats(),
        "status": "healthy",
    }
