"""Tests for the Paper Trading views (routes/v1_paper.py) + runtime scoping.

Wires the real Execution Engine in-process, injects canonical fills through the
legacy bus (the exact production path), then asserts the read-only views expose
the resulting engine state. Also verifies the privacy fix: the runtime
dashboard is scoped to the owning user.
"""
import asyncio
import pytest
from pytest_asyncio import fixture as async_fixture
from fastapi import Request

from core.models import UserProfile


TEST_USER = "paper-test-user-0001"


async def _me(request: Request) -> UserProfile:
    return UserProfile(
        id=TEST_USER, email="paper@test.example.com",
        full_name="Paper Test", subscription_tier="enterprise",
    )


@async_fixture(autouse=True)
async def _clean_engine(client):
    """Give this module an isolated engine + auth override; restore after.

    Depends on the conftest ``client`` fixture so this override is applied
    AFTER ``_apply_test_mocks`` (which otherwise wins the dependency_overrides
    slot on first application).
    """
    from main import app
    from core.deps import get_current_user

    saved = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = _me

    # Reset engine state (isolated from tests/test_execution_engine.py).
    from execution_engine.init import reset_execution_engine
    from execution_engine.events import ExecutionDomain, LoggingSink, execution_bus

    from execution_engine import pnl_engine, portfolio_engine, position_manager, trade_manager
    from execution_engine.metrics import execution_metrics

    reset_execution_engine()
    execution_bus.reset_subscribers()
    execution_bus.subscribe(ExecutionDomain.ORDER, LoggingSink())
    execution_bus.clear()
    trade_manager.ledger.clear()
    for mgr in (position_manager, pnl_engine, portfolio_engine):
        mgr.clear()
    for mgr in (trade_manager, position_manager, pnl_engine, portfolio_engine, execution_metrics):
        mgr._installed = False
    from execution_engine.events import _ENGINE_BRIDGE_WIRED, _LEGACY_BRIDGE_WIRED
    _LEGACY_BRIDGE_WIRED = False
    _ENGINE_BRIDGE_WIRED = False

    yield

    execution_bus.clear()
    if saved is not None:
        app.dependency_overrides[get_current_user] = saved
    else:
        app.dependency_overrides.pop(get_current_user, None)


async def inject_fills() -> None:
    """Inject the canonical 3-fill contract through the real legacy bridge."""
    from execution_engine.init import init_execution_engine
    from execution.event_bus import execution_event_bus
    from execution.models import ExecutionEvent

    init_execution_engine()

    def payload(req_id, qty, price, fill_qty):
        return {
            "order_id": req_id, "quantity": qty, "price": price,
            "fill": {"order_id": req_id, "filled_quantity": fill_qty, "filled_price": price},
            "is_paper": True, "strategy_id": "paper-test", "source": "smoke",
        }

    async def pub(etype, req_id, side, qty, price, fill_qty):
        await execution_event_bus.publish(ExecutionEvent(
            event_type=etype, execution_request_id=req_id, user_id=TEST_USER,
            broker="paper", symbol="NIFTY", side=side, message="paper test inject",
            payload=payload(req_id, qty, price, fill_qty),
        ))

    await pub("PaperOrderPartiallyFilled", "p-part", "SELL", 2, 110.0, 2)
    await pub("PaperOrderFilled", "p-buy", "BUY", 10, 100.0, 10)
    await pub("PaperOrderFilled", "p-sell", "SELL", 8, 110.0, 8)
    await asyncio.sleep(0.2)


@pytest.mark.asyncio
async def test_paper_status_wired(client):
    await inject_fills()
    resp = await client.get("/api/v1/paper/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["engine"]["wired"] is True
    assert body["engine"]["engine_bridge"] is True
    assert body["user_id"] == TEST_USER


@pytest.mark.asyncio
async def test_paper_account(client):
    await inject_fills()
    resp = await client.get("/api/v1/paper/account")
    assert resp.status_code == 200
    acc = resp.json()
    assert acc["broker"] == "paper"
    assert acc["realised_pnl"] == 100.0
    assert acc["current_equity"] == pytest.approx(500100.0)


@pytest.mark.asyncio
async def test_paper_positions_flat_net(client):
    await inject_fills()
    resp = await client.get("/api/v1/paper/positions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0  # net flat after the 3-fill contract


@pytest.mark.asyncio
async def test_paper_trades(client):
    await inject_fills()
    resp = await client.get("/api/v1/paper/trades")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 3
    ids = {t["client_order_id"] for t in body["trades"]}
    assert ids == {"p-part", "p-buy", "p-sell"}


@pytest.mark.asyncio
async def test_paper_portfolio(client):
    await inject_fills()
    resp = await client.get("/api/v1/paper/portfolio")
    assert resp.status_code == 200
    body = resp.json()
    assert body["realised_pnl"] == 100.0
    assert body["open_positions"] == 0


@pytest.mark.asyncio
async def test_paper_unauthenticated(client):
    from main import app
    from core.deps import get_current_user

    app.dependency_overrides.pop(get_current_user, None)  # real auth -> 401
    try:
        resp = await client.get("/api/v1/paper/account")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = _me


@pytest.mark.asyncio
async def test_runtime_dashboard_scoped_to_user():
    from engine import graph_strategy_runner as runner

    a = runner._runtime_stats("strat-a")
    a.update({"status": "running", "user_id": "owner-a"})
    b = runner._runtime_stats("strat-b")
    b.update({"status": "running", "user_id": "owner-b"})

    try:
        rows_a = await runner.get_runtime_dashboard(user_id="owner-a")
        assert {r["strategy_id"] for r in rows_a} == {"strat-a"}
        rows_b = await runner.get_runtime_dashboard(user_id="owner-b")
        assert {r["strategy_id"] for r in rows_b} == {"strat-b"}
        rows_unknown = await runner.get_runtime_dashboard(user_id="nobody")
        assert rows_unknown == []
    finally:
        for sid in ("strat-a", "strat-b"):
            runner._runtime.pop(sid, None)