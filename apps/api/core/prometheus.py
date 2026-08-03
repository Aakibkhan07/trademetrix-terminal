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

broadcast_total = Counter(
    "broadcast_total", "Admin broadcast operations", ["strategy_key", "paper"]
)

broadcast_recipients = Histogram(
    "broadcast_recipients", "Number of recipients per broadcast", ["strategy_key"],
    buckets=(1, 5, 10, 25, 50, 100),
)

rate_limit_breaches = Counter(
    "rate_limit_breaches_total", "Rate limit breaches", ["broker"]
)

# ── Generic broker transport metrics (brokers/sdk/transport.py) ──
broker_transport_calls = Counter(
    "broker_http_calls_total", "Logical broker transport calls", ["broker", "endpoint"]
)
broker_transport_wire_calls = Counter(
    "broker_http_wire_calls_total", "Actual broker HTTP round-trips", ["broker", "endpoint"]
)
broker_transport_cache_hits = Counter(
    "broker_http_cache_hits_total", "Broker transport cache hits", ["broker", "endpoint"]
)
broker_transport_dedup_hits = Counter(
    "broker_http_dedup_hits_total", "Broker transport dedup hits", ["broker", "endpoint"]
)
broker_transport_retries = Counter(
    "broker_http_retries_total", "Broker transport retry attempts", ["broker", "endpoint"]
)
broker_transport_rate_limited = Counter(
    "broker_http_rate_limited_total", "Broker 429/1015 responses seen", ["broker", "endpoint"]
)
broker_transport_waf_blocks = Counter(
    "broker_http_waf_blocks_total", "Broker WAF blocks seen", ["broker", "endpoint"]
)
broker_transport_failures = Counter(
    "broker_http_failures_total", "Broker transport final failures", ["broker", "endpoint"]
)
broker_http_latency_seconds = Histogram(
    "broker_http_latency_seconds",
    "Broker transport retry-wait latency in seconds",
    ["broker", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

_TRANSPORT_METRICS = {
    "calls": broker_transport_calls,
    "wire_calls": broker_transport_wire_calls,
    "cache_hits": broker_transport_cache_hits,
    "dedup_hits": broker_transport_dedup_hits,
    "retries": broker_transport_retries,
    "rate_limited": broker_transport_rate_limited,
    "waf_blocks": broker_transport_waf_blocks,
    "failures": broker_transport_failures,
}

# ── System / Domain metrics ──
active_strategies = Gauge("active_strategies", "Number of running strategy engines")
active_broker_sessions = Gauge("active_broker_sessions", "Number of active broker sessions")
orders_failed_total = Counter("orders_failed_total", "Failed/cancelled/rejected orders", ["status"])
exceptions_total = Counter("exceptions_total", "Unhandled exceptions caught by global handler", ["type"])

# ── Strategy Runtime v1.0 metrics (strategy_runtime/observability.py) ──
strategy_runtime_running = Gauge(
    "strategy_runtime_running", "Strategies currently RUNNING in the strategy runtime"
)
strategy_runtime_lifecycle_events_total = Counter(
    "strategy_runtime_lifecycle_events_total",
    "Strategy runtime lifecycle events (STARTING/RUNNING/PAUSED/STOPPED/FAILED/RECOVERED/...)",
    ["state"],
)
strategy_runtime_latency_seconds = Histogram(
    "strategy_runtime_latency_seconds",
    "Strategy evaluation latency in seconds",
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)
strategy_runtime_orders_total = Counter(
    "strategy_runtime_orders_total", "Orders generated by strategy runtime", ["outcome"]
)
strategy_runtime_errors_total = Counter(
    "strategy_runtime_errors_total", "Strategy runtime errors"
)
strategy_runtime_restarts_total = Counter(
    "strategy_runtime_restarts_total", "Strategy runtime strategy restarts"
)
strategy_runtime_recovery_seconds = Histogram(
    "strategy_runtime_recovery_seconds",
    "Runtime recovery duration in seconds",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)
strategy_runtime_ticks_total = Counter(
    "strategy_runtime_ticks_total", "Ticks dispatched to strategy workers"
)
strategy_runtime_dropped_ticks_total = Counter(
    "strategy_runtime_dropped_ticks_total", "Ticks dropped by full strategy worker queues"
)

# ── Broker audit events (brokers/sdk/events.py MetricsSink) ──
broker_events_total = Counter(
    "broker_events_total", "Broker audit events by kind", ["broker", "kind"]
)
broker_health_state = Gauge(
    "broker_health_state",
    "Derived broker health (1=connected, 2=websocket_healthy, 3=rest_healthy, 4=degraded, 5=rate_limited, 6=circuit_open, 7=auth_failed, 8=disconnected)",
    ["broker"],
)
broker_auth_state = Gauge(
    "broker_auth_state", "Broker auth state (0=anonymous,1=authenticating,2=authenticated,3=expired,4=reauth_required,5=refresh_failed)",
    ["broker"],
)


def record_broker_metrics(broker: str, operation: str, duration_s: float, success: bool):
    broker_request_duration_seconds.labels(broker=broker, operation=operation).observe(duration_s)
    if success:
        broker_requests_success.labels(broker=broker, operation=operation).inc()
    else:
        broker_requests_failure.labels(broker=broker, operation=operation).inc()


def record_broadcast_metrics(strategy_key: str, total: int, success_count: int, paper: bool):
    broadcast_total.labels(strategy_key=strategy_key, paper=str(paper)).inc()
    broadcast_recipients.labels(strategy_key=strategy_key).observe(total)


def record_rate_limit_breach(broker: str):
    rate_limit_breaches.labels(broker=broker).inc()


def record_broker_transport_metric(name: str, broker: str, endpoint: str, value: int = 1):
    counter = _TRANSPORT_METRICS.get(name)
    if counter is not None:
        counter.labels(broker=broker, endpoint=endpoint).inc(value)


def record_broker_transport_latency(broker: str, endpoint: str, seconds: float):
    broker_http_latency_seconds.labels(broker=broker, endpoint=endpoint).observe(seconds)


_HEALTH_TO_VALUE = {
    "connected": 1,
    "websocket_healthy": 2,
    "rest_healthy": 3,
    "degraded": 4,
    "rate_limited": 5,
    "circuit_open": 6,
    "authentication_failed": 7,
    "disconnected": 8,
}

_AUTH_TO_VALUE = {
    "anonymous": 0,
    "authenticating": 1,
    "authenticated": 2,
    "expired": 3,
    "reauth_required": 4,
    "refresh_failed": 5,
}


def record_broker_event(broker: str, kind: str) -> None:
    """Record one broker audit event kind (wired via events.MetricsSink)."""
    broker_events_total.labels(broker=broker or "unknown", kind=kind).inc()


def record_broker_health(broker: str, state: str) -> None:
    value = 8 if state not in _HEALTH_TO_VALUE else _HEALTH_TO_VALUE[state]
    broker_health_state.labels(broker=broker).set(value)


def record_broker_auth(broker: str, auth_state: str) -> None:
    value = 0 if auth_state not in _AUTH_TO_VALUE else _AUTH_TO_VALUE[auth_state]
    broker_auth_state.labels(broker=broker).set(value)


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


def on_breaker_state_change(name: str, state: str) -> None:
    state_val = {"closed": 0, "half_open": 1, "open": 2}.get(state, 0)
    circuit_breaker_state.labels(breaker=name).set(state_val)


@router.get("/metrics")
async def prometheus_metrics():
    update_process_metrics()
    record_market_metrics()
    api_health_status.set(1)
    from core.resilience import get_circuit_breaker_stats
    for name, stats in get_circuit_breaker_stats().items():
        state_val = {"closed": 0, "half_open": 1, "open": 2}.get(stats["state"], 0)
        circuit_breaker_state.labels(breaker=name).set(state_val)

    try:
        from runtime.observability import runtime_metrics
        rs = runtime_metrics.stats
        active_strategies.set(rs.get("active_strategies", 0))
    except Exception:
        pass

    try:
        from oms.observability import oms_metrics
        os_ = oms_metrics.stats
        for status in ("rejected", "cancelled", "expired"):
            val = os_.get(f"orders_{status}", 0)
            orders_failed_total.labels(status=status).inc(val - orders_failed_total.labels(status=status)._value.get())
            # ^ incremental — we just set since this runs on each scrape and counters accumulate
        orders_failed_total.labels(status="error").inc(os_.get("errors", 0) - orders_failed_total.labels(status="error")._value.get())
    except Exception:
        pass

    try:
        from portfolio.observability import portfolio_metrics
        ps = portfolio_metrics.stats
        active_broker_sessions.set(len(ps.get("broker_sync_counts", {})))
    except Exception:
        pass

    return Response(content=generate_latest(REGISTRY), media_type="text/plain; version=0.0.4")
