import pytest
from fastapi import HTTPException, Request

from routes.v1_auth import _client_ip, _throttle_login


def _make_request(ip: str = "203.0.113.7", xff: str | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/signin",
        "headers": [],
        "client": ("203.0.113.7", 54321),
        "query_string": b"",
    }
    if xff:
        scope["headers"] = [(b"x-forwarded-for", xff.encode())]
    return Request(scope)


def test_client_ip_uses_forwarded_first_hop():
    req = _make_request(xff="198.51.100.3, 10.0.0.1")
    assert _client_ip(req) == "198.51.100.3"


def test_client_ip_falls_back_to_socket():
    req = _make_request()
    assert _client_ip(req) == "203.0.113.7"


@pytest.mark.asyncio
async def test_throttle_clears_on_success(monkeypatch):
    cleared = []

    async def fake_set(key, value, ttl=300):
        cleared.append(key)
        return True

    monkeypatch.setattr("routes.v1_auth.cache.set", fake_set)
    await _throttle_login(_make_request(), "user@example.com", failed=False)
    assert cleared and "loginfail:user@example.com:203.0.113.7" in cleared[0]


@pytest.mark.asyncio
async def test_throttle_progressive_delay_then_lockout(monkeypatch):
    attempts = {"n": 0}

    async def fake_get(key, default=0):
        return attempts["n"]

    async def fake_set(key, value, ttl=300):
        attempts["n"] = value
        return True

    monkeypatch.setattr("routes.v1_auth.cache.get", fake_get)
    monkeypatch.setattr("routes.v1_auth.cache.set", fake_set)

    req = _make_request(xff="203.0.113.9")
    # First 5 failures: progressive delay, still 401-compatible (no HTTPException)
    for _ in range(5):
        await _throttle_login(req, "victim@example.com", failed=True)

    # 6th failure: locked out → 429
    with pytest.raises(HTTPException) as exc:
        await _throttle_login(req, "victim@example.com", failed=True)
    assert exc.value.status_code == 429