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
api_health_status = Gauge("api_health_status", "API health check status (1=healthy, 0=unhealthy)")

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Supabase query duration in seconds",
    ["table", "operation"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

event_loop_blocked_seconds = Histogram(
    "event_loop_blocked_seconds",
    "Time event loop was blocked by sync calls",
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
)

market_ticks_total = Counter(
    "market_ticks_total", "Total market ticks processed", ["broker"]
)
market_ticks_errors_total = Counter(
    "market_ticks_errors_total", "Total market tick errors", ["error_type"]
)
market_ticks_reconnects_total = Counter(
    "market_ticks_reconnects_total", "Total broker reconnects", ["broker"]
)


broker_request_duration_seconds = Histogram(
    "broker_request_duration_seconds",
    "Broker API request duration in seconds",
    ["broker", "operation"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

broker_requests_success = Counter(
    "broker_requests_success_total", "Successful broker API calls", ["broker", "operation"]
)

broker_requests_failure = Counter(
    "broker_requests_failure_total", "Failed broker API calls", ["broker", "operation"]
)


def record_broker_metrics(broker: str, operation: str, duration_s: float, success: bool):
    broker_request_duration_seconds.labels(broker=broker, operation=operation).observe(duration_s)
    if success:
        broker_requests_success.labels(broker=broker, operation=operation).inc()
    else:
        broker_requests_failure.labels(broker=broker, operation=operation).inc()


def record_metrics(method: str, path: str, status_code: int, duration_s: float):
    http_requests_total.labels(method=method, path=path, status=str(status_code)).inc()
    http_request_duration_seconds.labels(method=method, path=path).observe(duration_s)


def record_db_metrics(table: str, operation: str, duration_s: float):
    db_query_duration_seconds.labels(table=table, operation=operation).observe(duration_s)


def update_process_metrics():
    proc = psutil.Process(os.getpid())
    mem = proc.memory_info()
    memory_bytes.labels(type="rss").set(mem.rss)
    memory_bytes.labels(type="vms").set(mem.vms)
    cpu_percent.set(proc.cpu_percent(interval=0))


def record_market_metrics():
    from market.observability import market_metrics
    m = market_metrics.get_metrics()
    for broker, count in m.get("ticks_per_broker", {}).items():
        market_ticks_total.labels(broker=broker).inc(count)
    for err_type, count in m.get("errors", {}).items():
        market_ticks_errors_total.labels(error_type=err_type).inc(count)
    for broker, count in m.get("reconnects", {}).items():
        market_ticks_reconnects_total.labels(broker=broker).inc(count)


@router.get("/metrics")
async def prometheus_metrics():
    update_process_metrics()
    record_market_metrics()
    api_health_status.set(1)
    from core.resilience import get_circuit_breaker_stats
    for name, stats in get_circuit_breaker_stats().items():
        state_val = {"closed": 0, "half_open": 1, "open": 2}.get(stats["state"], 0)
        circuit_breaker_state.labels(breaker=name).set(state_val)
    return Response(content=generate_latest(REGISTRY), media_type="text/plain; version=0.0.4")
