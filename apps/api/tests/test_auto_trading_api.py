"""Auto Trading v1.0 — HTTP surface tests.

Covers the wire protocol for trading modes: explicit LIVE confirmation (409),
mode refusal while an emergency stop is active (423), emergency stop /
release / pause-all, reconcile and accounts, plus paper-mode deploy working
with no confirmation.
"""
import pytest

import tests.test_strategy_runtime_api as api_tests

_patch_runtime = api_tests._patch_runtime
_make_strategy = api_tests._make_strategy


async def _deploy(client, auth_headers, sid, mode="paper", broker="", confirm=False):
    return await client.post("/api/v1/runtime/deploy", json={
        "strategy_id": sid,
        "symbol": "NIFTY",
        "interval": "15m",
        "mode": mode,
        "broker": broker,
        "confirm_live": confirm,
        "quantity": 10,
    }, headers=auth_headers)


@pytest.mark.asyncio
async def test_paper_deploy_needs_no_confirmation(client, auth_headers, monkeypatch):
    await _patch_runtime(monkeypatch)
    sid = await _make_strategy()
    r = await _deploy(client, auth_headers, sid, mode="paper")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "started"


@pytest.mark.asyncio
async def test_live_deploy_without_confirm_409(client, auth_headers, monkeypatch):
    await _patch_runtime(monkeypatch)
    sid = await _make_strategy()
    r = await _deploy(client, auth_headers, sid, mode="live", broker="fyers", confirm=False)
    assert r.status_code == 409, r.text
    assert "confirmation" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_live_deploy_with_confirm_requires_account(client, auth_headers, monkeypatch):
    await _patch_runtime(monkeypatch)
    from strategy_runtime import mode as mode_mod

    async def _no_account(user_id, broker):
        return False

    monkeypatch.setattr(mode_mod, "_user_has_broker_account", _no_account)
    sid = await _make_strategy()
    r = await _deploy(client, auth_headers, sid, mode="live", broker="fyers", confirm=True)
    assert r.status_code == 400, r.text
    assert "credentials" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_live_deploy_confirm_starts(client, auth_headers, monkeypatch):
    await _patch_runtime(monkeypatch)
    from strategy_runtime import mode as mode_mod

    async def _has_account(user_id, broker):
        return True

    monkeypatch.setattr(mode_mod, "_user_has_broker_account", _has_account)
    sid = await _make_strategy()
    r = await _deploy(client, auth_headers, sid, mode="live", broker="fyers", confirm=True)
    assert r.status_code == 200, r.text
    status = await client.get(f"/api/v1/runtime/{sid}/status", headers=auth_headers)
    assert status.json()["state"] == "RUNNING"
    assert status.json()["mode"] == "live"
    assert status.json()["confirmed"] is True


@pytest.mark.asyncio
async def test_emergency_stop_via_http(client, auth_headers, monkeypatch):
    await _patch_runtime(monkeypatch)
    sid = await _make_strategy()
    await _deploy(client, auth_headers, sid)
    r = await client.post("/api/v1/runtime/emergency", json={"reason": "http-test"},
                          headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "emergency_stopped"
    assert sid in body["halted"]
    status = await client.get(f"/api/v1/runtime/{sid}/status", headers=auth_headers)
    assert status.json()["state"] == "PAUSED"
    # new deploy is blocked while the emergency stop is active (423)
    sid2 = await _make_strategy()
    r2 = await _deploy(client, auth_headers, sid2, mode="paper")
    assert r2.status_code == 423, r2.text
    # release → deploy works again
    rel = await client.post("/api/v1/runtime/emergency/release", headers=auth_headers)
    assert rel.json()["status"] == "emergency_released"
    r3 = await _deploy(client, auth_headers, sid2, mode="paper")
    assert r3.status_code == 200


@pytest.mark.asyncio
async def test_strategy_emergency_stop_and_pause_all(client, auth_headers, monkeypatch):
    await _patch_runtime(monkeypatch)
    sid = await _make_strategy()
    await _deploy(client, auth_headers, sid)
    r = await client.post(f"/api/v1/runtime/{sid}/emergency-stop", json={"reason": "per-strategy"},
                          headers=auth_headers)
    assert r.json()["status"] == "emergency_stopped"
    # release then resume + pause-all
    await client.post("/api/v1/runtime/emergency/release", headers=auth_headers)
    await client.post(f"/api/v1/runtime/{sid}/resume", headers=auth_headers)
    r2 = await client.post("/api/v1/runtime/pause-all", headers=auth_headers)
    assert r2.json()["status"] == "paused"
    assert sid in r2.json()["halted"]


@pytest.mark.asyncio
async def test_reconcile_via_http(client, auth_headers, monkeypatch):
    await _patch_runtime(monkeypatch)
    sid = await _make_strategy()
    await _deploy(client, auth_headers, sid)
    r = await client.post(f"/api/v1/runtime/{sid}/reconcile", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "runtime" in body and "checks" in body
    assert body["broker"] == "paper"


@pytest.mark.asyncio
async def test_reconcile_unknown_404(client, auth_headers, monkeypatch):
    await _patch_runtime(monkeypatch)
    r = await client.post("/api/v1/runtime/nope-000000/reconcile", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_accounts_endpoint(client, auth_headers, monkeypatch):
    await _patch_runtime(monkeypatch)
    from infrastructure.repositories import broker_repository as repo_mod

    async def _list_creds(self, user_id):
        return [{"broker": "fyers", "broker_name": "Fyers", "is_active": True,
                 "token_status": "valid", "token_expires_at": None}]

    monkeypatch.setattr(repo_mod, "BrokerRepository",
                        type("Repo", (), {"list_credentials": _list_creds}))
    r = await client.get("/api/v1/runtime/accounts", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert any(a["broker"] == "fyers" for a in r.json()["accounts"])
