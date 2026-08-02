"""Generic broker transport tests: strategies, retry, dedup, cache, WAF,
health, correlation ids, metrics, and the no-broker-branch invariant."""

import asyncio
import json
import logging

import pytest

from brokers.sdk.transport import (
    AuthStrategy,
    BrokerWAFError,
    HttpTransport,
    RateLimiter,
    TransportConfig,
    TransportResponse,
)
from brokers.sdk import transport as transport_module


class FakeHttpResponse:
    def __init__(self, status: int, body: dict | str = None):
        self.status_code = status
        self.headers = {}
        self._body = json.dumps(body) if isinstance(body, dict) else (body or "")

    @property
    def text(self) -> str:
        return self._body

    @property
    def content(self) -> bytes:
        return self._body.encode("utf-8")


def _canned_client(calls: list, default_status: int = 200, default_body: dict | None = None):
    client = type("FakeClient", (), {})()
    client.seen = calls
    counter = {"i": 0}

    async def _go(method, url, **kwargs):
        client.seen.append((method, url, kwargs))
        counter["i"] += 1
        return FakeHttpResponse(default_status, default_body)

    client.get = lambda url, **kw: _go("GET", url, **kw)
    client.post = lambda url, **kw: _go("POST", url, **kw)
    client.patch = lambda url, **kw: _go("PATCH", url, **kw)
    client.delete = lambda url, **kw: _go("DELETE", url, **kw)
    client.aclose = _AsyncNoop()
    return client


class _AsyncNoop:
    async def __call__(self):
        return None


def _config(**overrides) -> TransportConfig:
    kwargs = dict(broker="dummy", base_url="https://api.example.com")
    kwargs.update(overrides)
    return TransportConfig(**kwargs)


@pytest.fixture
def t():
    tr = HttpTransport(_config(), client_id="cid", access_token="tok")
    tr._limiter.rpm = 10000   # disable limiter for logic tests
    tr._limiter.burst = 10000
    return tr


# ---------------------------------------------------------------------------
# Invariant: the generic transport must not know any broker's name or branch
# on broker identity.
# ---------------------------------------------------------------------------


def test_transport_has_no_broker_specific_logic():
    src = transport_module.__file__ and open(transport_module.__file__).read()
    assert "fyers" not in src.lower()
    assert "zerodha" not in src.lower()
    assert 'broker == "' not in src
    assert "== 'dummy'" not in src


# ---------------------------------------------------------------------------
# Strategy behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_builds_url_and_default_bearer_auth(t):
    calls = []
    t._client = _canned_client(calls, 200, {"s": "ok"})
    resp = await t.request("GET", "/v1/balances", caller="t")
    assert resp.status_code == 200
    assert resp.json() == {"s": "ok"}
    method, url, kwargs = calls[0]
    assert method == "GET"
    assert url == "https://api.example.com/v1/balances"
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    assert kwargs["headers"]["Accept"] == "application/json, text/plain, */*"


@pytest.mark.asyncio
async def test_content_type_added_for_json_body(t):
    calls = []
    t._client = _canned_client(calls, 200, {"s": "ok"})
    await t.request("POST", "/v1/orders", json_body={"qty": 1}, caller="t")
    assert calls[0][2]["headers"]["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_signing_hook_called_before_each_attempt(t):
    calls = []
    signs = []

    class SigningAuth(AuthStrategy):
        def sign(self, method, url, headers, json_body, params, client_id, access_token):
            signs.append((method, url, dict(headers), json_body, params))

    t._auth = SigningAuth()
    t._client = _canned_client(calls, 200, {"s": "ok"})
    await t.request("GET", "/v1/data", params={"q": "1"}, caller="t")
    assert len(signs) == 1
    assert signs[0][0] == "GET"
    assert signs[0][1] == "https://api.example.com/v1/data"
    assert signs[0][3] is None
    assert signs[0][4] == {"q": "1"}


@pytest.mark.asyncio
async def test_url_builder_absolute_urls_passthrough(t):
    calls = []
    t._client = _canned_client(calls, 200, {"s": "ok"})
    await t.request("GET", "https://cdn.example.com/files/a.csv", caller="t")
    assert calls[0][1] == "https://cdn.example.com/files/a.csv"


# ---------------------------------------------------------------------------
# Dedup + cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_identical_requests_deduplicated(t):
    client = type("FakeClient", (), {})()
    attempts = {"n": 0}

    async def go(url, **kw):
        attempts["n"] += 1
        await asyncio.sleep(0.05)
        return FakeHttpResponse(200, {"s": "ok"})

    client.get = go
    t._client = client

    results = await asyncio.gather(*[
        t.request("GET", "/v1/quotes", params={"symbols": "A"}, caller="t")
        for _ in range(5)
    ])
    assert all(r.status_code == 200 for r in results)
    assert attempts["n"] == 1
    assert t._stats["/v1/quotes"].dedup_hits == 4


@pytest.mark.asyncio
async def test_static_cache_serves_second_call(t):
    client = type("FakeClient", (), {})()
    attempts = {"n": 0}

    async def go(url, **kw):
        attempts["n"] += 1
        return FakeHttpResponse(200, {"s": "ok"})

    client.get = go
    t._client = client

    r1 = await t.request("GET", "/v1/funds", cache_ttl=60.0, caller="t")
    r2 = await t.request("GET", "/v1/funds", cache_ttl=60.0, caller="t")
    assert r1.status_code == 200 and r2.status_code == 200
    assert attempts["n"] == 1
    assert t._stats["/v1/funds"].cache_hits == 1


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_429_respected_with_retry_after(t):
    client = type("FakeClient", (), {})()
    attempts = {"n": 0}
    delays = []
    orig_sleep = asyncio.sleep

    async def fake_sleep(secs):
        delays.append(secs)

    async def go(url, **kw):
        attempts["n"] += 1
        r = FakeHttpResponse(429 if attempts["n"] == 1 else 200, {"s": "ok"})
        if attempts["n"] == 1:
            r.headers["Retry-After"] = "1.5"
        return r

    client.get = go
    t._client = client

    with __import__("unittest.mock").mock.patch("brokers.sdk.transport.asyncio.sleep", fake_sleep):
        resp = await t.request("GET", "/v1/orders", retries=3, caller="t")
    assert resp.status_code == 200
    assert attempts["n"] == 2
    assert delays == [1.5]


@pytest.mark.asyncio
async def test_waf_403_raises_and_never_retries(t):
    client = type("FakeClient", (), {})()
    attempts = {"n": 0}

    async def go(url, **kw):
        attempts["n"] += 1
        return FakeHttpResponse(403, "<html>Attention Required!</html>")

    client.get = go
    t._client = client

    with pytest.raises(BrokerWAFError):
        await t.request("GET", "/v1/quotes", retries=3, caller="t")
    assert attempts["n"] == 1  # zero retries on WAF block
    assert t._stats["/v1/quotes"].waf_blocked == 1


@pytest.mark.asyncio
async def test_5xx_retries_then_exhausts(t):
    client = type("FakeClient", (), {})()
    attempts = {"n": 0}

    async def go(url, **kw):
        attempts["n"] += 1
        return FakeHttpResponse(502, {"s": "error"})

    client.get = go
    t._client = client

    resp = await t.request("GET", "/v1/orders", retries=2, caller="t")
    assert resp.status_code == 502
    assert attempts["n"] == 3
    st = t._stats["/v1/orders"]
    assert st.retries == 2
    assert st.failures == 1


@pytest.mark.asyncio
async def test_no_retry_on_plain_4xx(t):
    client = type("FakeClient", (), {})()
    attempts = {"n": 0}

    async def go(url, **kw):
        attempts["n"] += 1
        return FakeHttpResponse(400, {"s": "error"})

    client.get = go
    t._client = client

    resp = await t.request("GET", "/v1/orders", retries=3, caller="t")
    assert resp.status_code == 400
    assert attempts["n"] == 1


@pytest.mark.asyncio
async def test_net_error_retries_then_raises(t):
    import httpx

    client = type("FakeClient", (), {})()
    attempts = {"n": 0}

    async def go(url, **kw):
        attempts["n"] += 1
        raise httpx.ConnectError("boom")

    client.get = go
    t._client = client

    with pytest.raises(httpx.ConnectError):
        await t.request("GET", "/v1/orders", retries=1, caller="t")
    assert attempts["n"] == 2
    st = t._stats["/v1/orders"]
    assert st.retries == 1
    assert st.failures == 1
    assert "transport" in t._last_error


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_correlation_id_in_request_logs(t, caplog):
    calls = []
    t._client = _canned_client(calls, 200, {"s": "ok"})
    with caplog.at_level(logging.INFO, logger="brokers.sdk.transport"):
        await t.request("GET", "/v1/orders", caller="t", correlation_id="abc123")
    assert any("corr=abc123" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_metrics_emitted_for_cache_dedup_and_wire(t, monkeypatch):
    emitted = []
    monkeypatch.setattr("core.prometheus.record_broker_transport_metric",
                        lambda name, broker, endpoint, value=1: emitted.append((name, broker, endpoint)))
    monkeypatch.setattr("core.prometheus.record_broker_transport_latency",
                        lambda broker, endpoint, seconds: emitted.append(("latency", broker, endpoint)))

    client = type("FakeClient", (), {})()
    attempts = {"n": 0}

    async def go(url, **kw):
        attempts["n"] += 1
        await asyncio.sleep(0.001)
        return FakeHttpResponse(200, {"s": "ok"})

    client.get = go
    t._client = client

    r1 = await t.request("GET", "/v1/funds", cache_ttl=60.0, caller="t")
    assert r1.status_code == 200
    await t.request("GET", "/v1/funds", cache_ttl=60.0, caller="t")
    results = await asyncio.gather(*[t.request("GET", "/v1/quotes", params={"s": "A"}, caller="t") for _ in range(3)])
    assert all(r.status_code == 200 for r in results)

    names = {name for name, _, _ in emitted}
    assert {"calls", "wire_calls", "cache_hits", "dedup_hits", "latency"} <= names
    assert ("cache_hits", "dummy", "/v1/funds") in emitted


@pytest.mark.asyncio
async def test_health_and_snapshot_shape(t):
    client = type("FakeClient", (), {})()
    attempts = {"n": 0}

    async def go(url, **kw):
        attempts["n"] += 1
        await asyncio.sleep(0.01)
        return FakeHttpResponse(200, {"s": "ok"})

    client.get = go
    t._client = client
    for _ in range(5):
        await t.request("GET", "/v1/orders", caller="t")
    snap = t.snapshot()
    assert snap["token"] == "cid"
    assert snap["endpoints"][0]["path"] == "/v1/orders"
    assert snap["endpoints"][0]["calls"] == 5
    health = t.health()
    assert health["ok"] is True
    assert health["broker"] == "dummy"
    assert health["rate_limit"]["budget_rpm"] == t._limiter.rpm
    assert health["endpoints_active"] == 1
    assert health["avg_latency_ms"] > 0


# ---------------------------------------------------------------------------
# RateLimiter as the rate-limit policy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limiter_sliding_window():
    lim = RateLimiter(key="k", rpm=3, burst=3, window_seconds=2.0)

    async def _acquire():
        await lim.acquire()

    await asyncio.gather(*[_acquire() for _ in range(3)])  # all fit
    started = __import__("time").monotonic()
    await lim.acquire()  # 4th call must wait ~ the sliding window
    assert __import__("time").monotonic() - started >= 1.8
    assert lim.pending_in_window(60) <= 3


@pytest.mark.asyncio
async def test_transport_uses_shared_limiter():
    lim = RateLimiter(key="shared", rpm=10, burst=10)
    t1 = HttpTransport(_config(), client_id="shared", access_token="t", limiter=lim)
    t2 = HttpTransport(_config(), client_id="shared", access_token="t", limiter=lim)
    assert t1._limiter is t2._limiter
    assert t1._limiter.key == "shared"


@pytest.mark.asyncio
async def test_custom_rate_limit_statuses(t):
    client = type("FakeClient", (), {})()
    attempts = {"n": 0}
    delays = []

    async def fake_sleep(secs):
        delays.append(secs)

    async def go(url, **kw):
        attempts["n"] += 1
        return FakeHttpResponse(9001, {"s": "custom"})

    t.config.rate_limit_statuses = frozenset({9001})
    client.get = go
    t._client = client

    with __import__("unittest.mock").mock.patch("brokers.sdk.transport.asyncio.sleep", fake_sleep):
        resp = await t.request("GET", "/v1/orders", retries=2, caller="t")
    assert resp.status_code == 9001
    assert attempts["n"] == 3
    assert t._stats["/v1/orders"].rate_limited == 3
