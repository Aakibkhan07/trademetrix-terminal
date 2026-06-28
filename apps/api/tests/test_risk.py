import pytest


@pytest.mark.asyncio
async def test_kill_switch_toggle(client, auth_headers):
    resp = await client.get("/api/v1/risk/kill-switch", headers=auth_headers)
    assert resp.status_code == 200
    initial = resp.json()["kill_switch_enabled"]

    enable_resp = await client.post("/api/v1/risk/kill-switch/enable", headers=auth_headers)
    assert enable_resp.status_code == 200

    check_resp = await client.get("/api/v1/risk/kill-switch", headers=auth_headers)
    assert check_resp.json()["kill_switch_enabled"] is True

    if not initial:
        disable_resp = await client.post("/api/v1/risk/kill-switch/disable", headers=auth_headers)
        assert disable_resp.status_code == 200


@pytest.mark.asyncio
async def test_live_mode_requires_confirmation(client, auth_headers):
    resp = await client.post("/api/v1/risk/live/enable", headers=auth_headers)
    assert resp.status_code == 400
    assert "confirmation" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_live_mode_toggle(client, auth_headers):
    enable_resp = await client.post("/api/v1/risk/live/enable", headers=auth_headers)
    assert enable_resp.status_code == 400

    status_resp = await client.get("/api/v1/risk/live/status", headers=auth_headers)
    assert status_resp.status_code == 200
    assert "is_live" in status_resp.json()


@pytest.mark.asyncio
async def test_risk_settings(client, auth_headers):
    resp = await client.get("/api/v1/risk/settings", headers=auth_headers)
    assert resp.status_code == 200
    assert "settings" in resp.json()
