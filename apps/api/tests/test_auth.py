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
    data = resp.json()
    assert data["status"] == "healthy"
    assert "system" in data
    assert "requests" in data


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
