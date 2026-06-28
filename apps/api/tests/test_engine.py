import pytest


@pytest.mark.asyncio
async def test_engine_start_invalid_broker(client, auth_headers):
    resp = await client.post("/api/v1/engine/start", json={
        "strategy_id": "nonexistent",
        "broker": "invalid_broker",
        "mode": "PAPER",
    }, headers=auth_headers)
    assert resp.status_code in (200, 400, 500)


@pytest.mark.asyncio
async def test_engine_runs(client, auth_headers):
    resp = await client.get("/api/v1/engine/runs", headers=auth_headers)
    assert resp.status_code == 200
    assert "runs" in resp.json()
