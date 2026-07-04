import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "Trade Metrix API"


@pytest.mark.asyncio
async def test_metrics(client):
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert len(resp.text) > 0


@pytest.mark.asyncio
async def test_signup(client):
    email = f"test_{id(client)}@example.com"
    resp = await client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": "StrongPass1!",
    })
    assert resp.status_code in (201, 409)
    if resp.status_code == 201:
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["email"] == email


@pytest.mark.asyncio
async def test_signin_invalid(client):
    resp = await client.post("/api/v1/auth/signin", json={
        "email": "nonexistent@example.com",
        "password": "wrongpass",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_unauthenticated(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_signout(client, auth_headers):
    resp = await client.post("/api/v1/auth/signout", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["message"] == "Signed out"


@pytest.mark.asyncio
async def test_csrf_bootstrap(client):
    """GET /auth/csrf returns 200 and sets the csrf_token cookie."""
    resp = await client.get("/api/v1/auth/csrf")
    assert resp.status_code == 200
    data = resp.json()
    assert "csrf_token" in data
    token = data["csrf_token"]
    assert len(token) == 64  # secrets.token_hex(32) → 64 hex chars
    # Cookie should be set in the response
    set_cookie = resp.headers.get("set-cookie", "")
    assert "csrf_token=" in set_cookie
    assert "Secure" in set_cookie
    assert "HttpOnly" not in set_cookie  # must be readable by JS


@pytest.mark.asyncio
async def test_csrf_bootstrap_no_auth_required(client):
    """GET /auth/csrf does not require authentication."""
    resp = await client.get("/api/v1/auth/csrf")
    assert resp.status_code == 200  # no auth needed — just sets cookie


@pytest.mark.asyncio
async def test_csrf_still_enforced(client):
    """A write without a valid CSRF token still gets 403 (CSRF not weakened)."""
    # Use a fresh client without the CSRF cookie
    from httpx import ASGITransport, AsyncClient
    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as nc:
        resp = await nc.post(
            "/api/v1/user-strategies/",
            json={"name": "hack", "index_symbol": "NIFTY", "legs": []},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "CSRF validation failed"
