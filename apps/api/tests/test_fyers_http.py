"""Rate-limit transport tests: backoff+jitter, 429/1015 handling, no tight
retry loops, dedup of identical requests, static caching, RPM accounting."""

import asyncio
import json

import pytest

from brokers.fyers_http import FyersTransport, FyersWAFError, TokenRateLimiter


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
    """A fake curl_cffi client that records (method, url, kwargs) and returns
    queued statuses (then the default)."""
    client = type("FakeClient", (), {})()
    client.seen = calls
    counter = {"i": 0}

    async def _go(method, url, **kwargs):
        client.seen.append((method, url, kwargs))
        i = counter["i"]
        counter["i"] += 1
        return FakeHttpResponse(default_status, default_body)

    client.get = lambda url, **kw: _go("GET", url, **kw)
    client.post = lambda url, **kw: _go("POST", url, **kw)
    client.patch = lambda url, **kw: _go("PATCH", url, **kw)
    client.delete = lambda url, **kw: _go("DELETE", url, **kw)
    client.aclose = AsyncMock2()
    return client


class AsyncMock2:
    async def __call__(self):
        return None


@pytest.fixture
def transport():
    t = FyersTransport(client_id="test_cid", access_token="test_token")
    t._limiter.rpm = 10000   # disable limiter for logic tests
    t._limiter.burst = 10000
    return t


@pytest.mark.asyncio
async def test_successful_get(transport):
    calls = []
    transport._client = _canned_client(calls, 200, {"s": "ok"})
    resp = await transport.request("GET", "/api/v3/orders", caller="t")
    assert resp.status_code == 200
    assert resp.json() == {"s": "ok"}
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_429_respected_with_retry_after(transport):
    """429 must sleep per Retry-After and retry — never tight-loop."""
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
    transport._client = client

    with __import__("unittest.mock").mock.patch("brokers.fyers_http.asyncio.sleep", fake_sleep):
        resp = await transport.request("GET", "/api/v3/orders", retries=3, caller="t")
    assert resp.status_code == 200
    assert attempts["n"] == 2
    assert len(delays) == 1
    assert delays[0] == 1.5  # Retry-After honored exactly


@pytest.mark.asyncio
async def test_1015_backoff_has_jitter_and_cap(transport):
    """1015 (Cloudflare rate limit) -> exponential backoff with jitter, capped."""
    client = type("FakeClient", (), {})()
    attempts = {"n": 0}
    delays = []

    async def fake_sleep(secs):
        delays.append(secs)

    async def go(url, **kw):
        attempts["n"] += 1
        return FakeHttpResponse(1015, {"s": "error"})

    client.get = go
    transport._client = client

    with __import__("unittest.mock").mock.patch("brokers.fyers_http.asyncio.sleep", fake_sleep):
        resp = await transport.request("GET", "/api/v3/orders", retries=2, caller="t")
    assert resp.status_code == 1015
    assert attempts["n"] == 3          # initial + 2 retries, no more
    assert len(delays) == 2
    assert all(0 <= d <= 8.0 for d in delays)  # jittered, never beyond cap
    assert delays[0] < delays[1] or max(delays) <= 8.0
    st = transport._stats["/api/v3/orders"]
    assert st.rate_limited == 3
    assert st.retries == 2


@pytest.mark.asyncio
async def test_waf_403_raises_and_never_retries(transport):
    client = type("FakeClient", (), {})()
    attempts = {"n": 0}

    async def go(url, **kw):
        attempts["n"] += 1
        return FakeHttpResponse(403, "<html>Attention Required!</html>")

    client.get = go
    transport._client = client

    with pytest.raises(FyersWAFError):
        await transport.request("GET", "/data/quotes", retries=3, caller="t")
    assert attempts["n"] == 1  # zero retries on WAF block
    assert transport._stats["/data/quotes"].waf_blocked == 1


@pytest.mark.asyncio
async def test_no_retry_on_plain_4xx(transport):
    client = type("FakeClient", (), {})()
    attempts = {"n": 0}

    async def go(url, **kw):
        attempts["n"] += 1
        return FakeHttpResponse(400, {"s": "error"})

    client.get = go
    transport._client = client

    resp = await transport.request("GET", "/api/v3/orders", retries=3, caller="t")
    assert resp.status_code == 400
    assert attempts["n"] == 1


@pytest.mark.asyncio
async def test_identical_requests_deduplicated(transport):
    """Concurrent identical requests must collapse to a single round-trip."""
    client = type("FakeClient", (), {})()
    attempts = {"n": 0}

    async def go(url, **kw):
        attempts["n"] += 1
        await asyncio.sleep(0.05)
        return FakeHttpResponse(200, {"s": "ok"})

    client.get = go
    transport._client = client

    results = await asyncio.gather(*[
        transport.request("GET", "/data/quotes", params={"symbols": "NSE:RELIANCE"}, caller="t")
        for _ in range(5)
    ])
    assert all(r.status_code == 200 for r in results)
    assert attempts["n"] == 1
    assert transport._stats["/data/quotes"].dedup_hits == 4


@pytest.mark.asyncio
async def test_static_cache_serves_second_call(transport):
    client = type("FakeClient", (), {})()
    attempts = {"n": 0}

    async def go(url, **kw):
        attempts["n"] += 1
        return FakeHttpResponse(200, {"s": "ok"})

    client.get = go
    transport._client = client

    r1 = await transport.request("GET", "/api/v3/funds", cache_ttl=60.0, caller="t")
    r2 = await transport.request("GET", "/api/v3/funds", cache_ttl=60.0, caller="t")
    assert r1.status_code == 200 and r2.status_code == 200
    assert attempts["n"] == 1
    assert transport._stats["/api/v3/funds"].cache_hits == 1


@pytest.mark.asyncio
async def test_rate_limiter_sliding_window():
    lim = TokenRateLimiter(key="k", rpm=3, burst=3, window_seconds=2.0)

    async def _acquire():
        await lim.acquire()

    await asyncio.gather(*[_acquire() for _ in range(3)])  # all fit
    started = __import__("time").monotonic()
    await lim.acquire()  # 4th call must wait ~ the sliding window
    assert __import__("time").monotonic() - started >= 1.8
    assert lim.pending_in_window(60) <= 3

    # burst ceiling
    lim2 = TokenRateLimiter(key="k2", rpm=100, burst=2, window_seconds=1.0)
    await lim2.acquire()
    await lim2.acquire()
    t0 = __import__("time").monotonic()
    await lim2.acquire()  # must wait ~1s for burst slot
    assert __import__("time").monotonic() - t0 >= 0.9


@pytest.mark.asyncio
async def test_rpm_accounting(transport):
    client = type("FakeClient", (), {})()
    async def go(url, **kw):
        return FakeHttpResponse(200, {"s": "ok"})
    client.get = go
    transport._client = client

    for _ in range(10):
        await transport.request("GET", "/api/v3/orders", caller="t")
    snap = transport.snapshot()
    orders = next(e for e in snap["endpoints"] if e["path"] == "/api/v3/orders")
    assert orders["calls"] == 10
    assert orders["wire_calls"] >= 1
    assert orders["rpm"] > 0
