"""Phase 4 observability + broker health endpoint tests."""
import pytest

from brokers.sdk.events import AuditEventBus, BrokerEventKind
from brokers.sdk.health import BrokerHealthService
from brokers.sdk.metrics import (
    CACHE_HIT_RATIO,
    REQUESTS_TOTAL,
    BrokerMetrics,
    MetricSource,
)
from brokers.sdk.observability import (
    TransportMetricSource,
    breaker_state_bridge,
)

# ---------------------------------------------------------------------------
# unified metrics module
# ---------------------------------------------------------------------------


class FakeTransport:
    def __init__(self):
        self._endpoints = []

    def set(self, row):
        self._endpoints = [row]

    def snapshot(self):
        return {
            "budget_rpm": 100,
            "used_last_minute": 25,
            "endpoints": [
                {
                    "calls": row["calls"],
                    "failures": row["failures"],
                    "waf_blocked": row.get("waf_blocked", 0),
                    "retries": row["retries"],
                    "cache_hits": row["cache_hits"],
                    "dedup_hits": row["dedup_hits"],
                    "rpm": row["calls"] * 6,
                }
                for row in self._endpoints
            ],
        }

    def health(self):
        return {"avg_latency_ms": 42.0, "rate_limit": {"used_last_minute": 25, "budget_rpm": 100}}


def test_metric_source_overlays_raw_values():
    tr = FakeTransport()
    tr.set({"calls": 100, "failures": 5, "retries": 3, "cache_hits": 40, "dedup_hits": 10, "waf_blocked": 1})
    src = TransportMetricSource("faker", tr)
    raw = src.raw_values()
    assert raw[REQUESTS_TOTAL] == 100
    assert raw["failure_total"] == 6  # failures + waf
    assert raw["retry_total"] == 3
    assert raw["cache_hit_ratio"] == 0.4
    assert raw["dedup_hit_ratio"] == 0.1
    assert raw["rate_limit_utilization"] == 25.0
    assert raw["rest_latency_ms"] == 42.0


def test_metric_source_lazy_resolver():
    holder = {"tr": FakeTransport()}

    def resolver():
        return holder["tr"]

    src = TransportMetricSource("faker", resolver)
    holder["tr"].set({"calls": 7, "failures": 0, "retries": 0, "cache_hits": 0, "dedup_hits": 0})
    assert src.raw_values()[REQUESTS_TOTAL] == 7


def test_metrics_registry_snapshot_with_health():
    hs = BrokerHealthService()
    hs.report_rest_health("faker", True, detail="ok")
    hs.report_ws_health("faker", True)

    class Src(MetricSource):
        broker = "faker"

        def raw_values(self):
            return {REQUESTS_TOTAL: 10, "failure_total": 2, CACHE_HIT_RATIO: 0.8}

    reg = BrokerMetrics(health_service=hs)
    reg.register("faker", Src())
    snap = reg.snapshot("faker")
    assert snap.health_state == "connected"
    assert snap.metrics["success_rate"] == 0.8
    assert snap.metrics["failure_rate"] == 0.2
    d = snap.to_dict()
    assert d["registered"] is True


def test_metrics_registry_token_refresh_count():
    reg = BrokerMetrics()
    reg.record_event("faker", BrokerEventKind.TOKEN_REFRESH.value)
    assert reg.token_refresh_count("faker") == 1


def test_metrics_registry_all_snapshot():
    class Src(MetricSource):
        def raw_values(self):
            return {}

    reg = BrokerMetrics()
    reg.register("a", Src())
    reg.register("b", Src())
    assert set(reg.snapshot_all()) == {"a", "b"}


# ---------------------------------------------------------------------------
# breaker bridge
# ---------------------------------------------------------------------------


def test_breaker_bridge_reports_health():
    hs = BrokerHealthService()
    bus = AuditEventBus()
    events = []
    bus.subscribe(lambda e: events.append(e))
    bridge = breaker_state_bridge(event_bus=bus, health_service=hs)
    bridge("broker_faker", "open")
    assert hs.get("faker").state.value in ("circuit_open", "rate_limited")
    found = [e for e in events if e.kind == BrokerEventKind.CIRCUIT_OPEN]
    assert len(found) == 1
    bridge("broker_faker", "closed")
    assert hs.get("faker").circuit_open is False


def test_breaker_bridge_ignores_unknown():
    half = breaker_state_bridge()
    half("weird", "half_open")  # must not raise
    half("nobroker_", "open")   # no trailing broker name -> no-op


# ---------------------------------------------------------------------------
# health + metrics endpoints
# ---------------------------------------------------------------------------


@pytest.fixture
def wire_metrics():
    from brokers.sdk.observability import wire_default_observability

    return wire_default_observability()


@pytest.mark.asyncio
async def test_brokers_health_endpoint_shape(wire_metrics, client, auth_headers):
    r = await client.get("/api/v1/brokers/health", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "brokers" in body
    assert "fyers" in body["brokers"]


@pytest.mark.asyncio
async def test_broker_health_endpoint_unknown(wire_metrics, client, auth_headers):
    r = await client.get("/api/v1/brokers/health/not_a_broker", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_broker_health_endpoint_known(wire_metrics, client, auth_headers):
    r = await client.get("/api/v1/brokers/health/fyers", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    for key in (
        "broker",
        "authentication",
        "rest_connectivity",
        "websocket_connectivity",
        "circuit_state",
        "rate_limit",
        "last_successful_request",
        "last_failed_request",
        "capabilities",
    ):
        assert key in body, key


@pytest.mark.asyncio
async def test_broker_metrics_endpoint(wire_metrics, client, auth_headers):
    r = await client.get("/api/v1/brokers/metrics/fyers", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["broker"] == "fyers"
    for key in (
        "requests_total",
        "success_rate",
        "failure_rate",
        "retry_total",
        "token_refresh_total",
        "order_latency_ms",
        "rest_latency_ms",
        "websocket_latency_ms",
        "cache_hit_ratio",
        "dedup_hit_ratio",
        "rate_limit_utilization",
    ):
        assert key in body["metrics"], key


@pytest.mark.asyncio
async def test_broker_metrics_endpoint_unknown(wire_metrics, client, auth_headers):
    r = await client.get("/api/v1/brokers/metrics/ghost", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_broker_capabilities_endpoint(wire_metrics, client, auth_headers):
    r = await client.get("/api/v1/brokers/capabilities", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "fyers" in body["brokers"]
    assert "orders" in body["brokers"]["fyers"]["capabilities"]


def test_broker_capabilities_runtime_discovery_shape():
    from brokers.sdk.capabilities import get_capabilities

    caps = get_capabilities("fyers")
    d = caps.to_dict()
    assert d["broker"] == "fyers"
    assert "orders" in d["capabilities"]
    assert "websocket" in d["capabilities"]


# ---------------------------------------------------------------------------
# observability end-to-end (bus -> health -> metrics)
# ---------------------------------------------------------------------------


def test_event_bus_drives_health_and_metrics():
    class Src(MetricSource):
        def raw_values(self):
            return {}

    bus = AuditEventBus()
    hs = BrokerHealthService(event_bus=bus)
    hs.attach_event_listener()
    reg = BrokerMetrics(health_service=hs)
    reg.register("faker", Src())
    bus.emit(BrokerEventKind.CIRCUIT_OPEN, broker="faker", message="breaker open")
    assert hs.get("faker").circuit_open is True
    snap = reg.snapshot("faker")
    assert snap.metrics["circuit_open"] == 1.0