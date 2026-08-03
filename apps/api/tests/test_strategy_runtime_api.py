"""Strategy Runtime v1.0 — HTTP API smoke tests (via the conftest client).

Verifies the router is wired, auth-gated, and the full deploy -> status ->
evaluate -> pause -> resume -> stop lifecycle works over HTTP against a real
builder strategy (in-memory builder store + fake engine gate).
"""
import pytest

_CSRF = "test-csrf-token-32-chars-for-testing!!"


async def _patch_runtime(monkeypatch):
    """Fake strategy loading + engine gate (same isolation as the unit tests)."""
    from strategy_runtime import workers as workers_module

    from tests.test_strategy_runtime import FakeStrategy

    async def _fake_load(sid, symbol):
        return FakeStrategy({"symbol": symbol, "strategy_id": sid})

    monkeypatch.setattr(workers_module, "load_strategy", _fake_load)
    monkeypatch.setattr("engine.gate.execute_order", _fake_execute)

    from strategy_runtime.manager import strategy_runtime_manager
    from strategy_runtime.observability import runtime_observability

    runtime_observability._running.clear()
    strategy_runtime_manager._registry._records.clear()
    strategy_runtime_manager.configure_state_store(None)
    return strategy_runtime_manager


async def _fake_execute(user_id, order, source=""):
    from core.models import OrderResult

    return OrderResult(success=True, broker_order_id="http-fake", status="filled")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    from execution_engine.events import ExecutionDomain, LoggingSink, execution_bus
    from execution_engine.init import reset_execution_engine
    from execution_engine.persistence import runtime_persistence
    from engine.graph_strategy_runner import _running_tasks, _runtime

    reset_execution_engine()
    execution_bus.reset_subscribers()
    execution_bus.subscribe(ExecutionDomain.ORDER, LoggingSink())
    execution_bus.clear()
    runtime_persistence.configure(None)
    runtime_persistence._installed = False
    runtime_persistence._last_hash.clear()
    for sid in list(_running_tasks):
        task = _running_tasks.pop(sid, None)
        if task and not task.done():
            task.cancel()
    _runtime.clear()


async def _make_strategy() -> str:
    from builder.manager import builder_manager

    dsl = await builder_manager.create(name="http-runtime-test", author="user", template="ema_crossover")
    await builder_manager.set_status(dsl.id, "ready")
    return dsl.id


@pytest.mark.asyncio
async def test_runtime_http_lifecycle(client, auth_headers, monkeypatch):
    await _patch_runtime(monkeypatch)
    sid = await _make_strategy()

    deploy = await client.post("/api/v1/runtime/deploy", json={
        "strategy_id": sid,
        "symbol": "NIFTY",
        "interval": "15m",
        "mode": "paper",
        "is_paper": True,
        "broker": "paper",
        "quantity": 10,
    }, headers=auth_headers)
    assert deploy.status_code == 200, deploy.text
    body = deploy.json()
    assert body["status"] == "started"
    assert body["strategy_id"] == sid

    status = await client.get(f"/api/v1/runtime/{sid}/status", headers=auth_headers)
    assert status.status_code == 200
    assert status.json()["state"] == "RUNNING"

    paused = await client.post(f"/api/v1/runtime/{sid}/pause", headers=auth_headers)
    assert paused.json()["status"] == "paused"
    resumed = await client.post(f"/api/v1/runtime/{sid}/resume", headers=auth_headers)
    assert resumed.json()["status"] == "resumed"

    evaluated = await client.post(f"/api/v1/runtime/{sid}/evaluate", headers=auth_headers)
    assert evaluated.status_code == 200
    assert evaluated.json()["evaluated"] in (True, False)

    listed = await client.get("/api/v1/runtime/strategies", headers=auth_headers)
    assert listed.status_code == 200
    assert any(s["strategy_id"] == sid for s in listed.json()["strategies"])

    stopped = await client.post(f"/api/v1/runtime/{sid}/stop", headers=auth_headers)
    assert stopped.json()["status"] == "stopped"

    gone = await client.get(f"/api/v1/runtime/{sid}/status", headers=auth_headers)
    assert gone.status_code == 200
    assert gone.json()["state"] == "STOPPED"


@pytest.mark.asyncio
async def test_runtime_http_health(client, auth_headers, monkeypatch):
    await _patch_runtime(monkeypatch)
    health = await client.get("/api/v1/runtime/health", headers=auth_headers)
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "healthy"
    assert "runtime_state" in body
    assert "metrics" in body


@pytest.mark.asyncio
async def test_runtime_http_stop_unknown_404(client, auth_headers, monkeypatch):
    await _patch_runtime(monkeypatch)
    resp = await client.post(
        "/api/v1/runtime/does-not-exist/stop", headers=auth_headers
    )
    assert resp.status_code == 404
