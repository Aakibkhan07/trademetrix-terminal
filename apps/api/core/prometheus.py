import os

import psutil
from fastapi import APIRouter, Response
from prometheus_client import REGISTRY, Counter, Gauge, Histogram, generate_latest

router = APIRouter(tags=["monitoring"])

http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

active_connections = Gauge("active_connections", "Number of active connections")
circuit_breaker_state = Gauge(
    "circuit_breaker_state", "Circuit breaker state (0=closed, 1=half, 2=open)", ["breaker"]
)
memory_bytes = Gauge("process_memory_bytes", "Process memory in bytes", ["type"])
cpu_percent = Gauge("process_cpu_percent", "Process CPU usage percent")


def record_metrics(method: str, path: str, status_code: int, duration_s: float):
    http_requests_total.labels(method=method, path=path, status=str(status_code)).inc()
    http_request_duration_seconds.labels(method=method, path=path).observe(duration_s)


def update_process_metrics():
    proc = psutil.Process(os.getpid())
    mem = proc.memory_info()
    memory_bytes.labels(type="rss").set(mem.rss)
    memory_bytes.labels(type="vms").set(mem.vms)
    cpu_percent.set(proc.cpu_percent(interval=0))


@router.get("/metrics/prometheus")
async def prometheus_metrics():
    update_process_metrics()
    from core.resilience import get_circuit_breaker_stats
    for name, stats in get_circuit_breaker_stats().items():
        state_val = {"closed": 0, "half_open": 1, "open": 2}.get(stats["state"], 0)
        circuit_breaker_state.labels(breaker=name).set(state_val)
    return Response(content=generate_latest(REGISTRY), media_type="text/plain; version=0.0.4")
