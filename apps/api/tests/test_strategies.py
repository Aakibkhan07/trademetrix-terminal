import pytest


@pytest.mark.asyncio
async def test_list_builtin_strategies(client):
    resp = await client.get("/api/v1/strategies/list-builtin")
    assert resp.status_code == 200
    data = resp.json()
    assert "strategies" in data
    assert len(data["strategies"]) >= 4


@pytest.mark.asyncio
async def test_create_strategy(client, auth_headers):
    resp = await client.post("/api/v1/strategies/", json={
        "name": "Test Strategy",
        "type": "builtin",
        "config": {"type": "trend_rider", "symbol": "NIFTY"},
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data or "strategy" in data


@pytest.mark.asyncio
async def test_list_strategies(client, auth_headers):
    resp = await client.get("/api/v1/strategies/", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "strategies" in data
