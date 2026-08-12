"""Regression tests: builder deploy status gate.

The deploy route sets a strategy's status to PAPER on deploy, then rejects
every subsequent deploy because PAPER was not in the allowed statuses —
making redeploy impossible from the UI ("Strategy is paper; validate and
mark ready before deploying"). PAPER and STOPPED must be redeployable.
"""
import pytest

from builder.manager import builder_manager
from builder.models import StrategyStatus

_DEPLOY_PAYLOAD = {
    "symbol": "NSE:NIFTY50-INDEX",
    "interval": "5m",
    "mode": "paper",
    "broker": "",
    "capital": 100000,
    "risk": {},
    "schedule": {},
}


async def _make_paper_strategy() -> str:
    dsl = await builder_manager.create(name="Redeploy Test", template="ema_crossover")
    await builder_manager.set_status(dsl.id, StrategyStatus.PAPER)
    return dsl.id


@pytest.mark.asyncio
async def test_redeploy_paper_strategy_succeeds(client, auth_headers, monkeypatch):
    """A strategy already deployed (status PAPER) must be deployable again."""
    import routes.v1_builder as v1_builder

    monkeypatch.setattr(v1_builder, "_runtime_start", _fake_runtime_start)
    sid = await _make_paper_strategy()

    resp = await client.post(
        f"/api/v1/builder/strategies/{sid}/deploy",
        json=_DEPLOY_PAYLOAD,
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "started"
    assert resp.json()["mode"] == "paper"


@pytest.mark.asyncio
async def test_redeploy_stopped_strategy_succeeds(client, auth_headers, monkeypatch):
    """A stopped strategy (status STOPPED) must be deployable again."""
    import routes.v1_builder as v1_builder

    monkeypatch.setattr(v1_builder, "_runtime_start", _fake_runtime_start)
    sid = await _make_paper_strategy()
    await builder_manager.set_status(sid, StrategyStatus.STOPPED)

    resp = await client.post(
        f"/api/v1/builder/strategies/{sid}/deploy",
        json=_DEPLOY_PAYLOAD,
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "started"


@pytest.mark.asyncio
async def test_deploy_archived_strategy_still_rejected(client, auth_headers, monkeypatch):
    """ARCHIVED must stay non-deployable."""
    import routes.v1_builder as v1_builder

    monkeypatch.setattr(v1_builder, "_runtime_start", _fake_runtime_start)
    dsl = await builder_manager.create(name="Archived Test", template="ema_crossover")
    await builder_manager.archive(dsl.id)

    resp = await client.post(
        f"/api/v1/builder/strategies/{dsl.id}/deploy",
        json=_DEPLOY_PAYLOAD,
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text
    assert "validate and mark ready" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_deploy_missing_strategy_404(client, auth_headers):
    resp = await client.post(
        "/api/v1/builder/strategies/doesnotexist/deploy",
        json=_DEPLOY_PAYLOAD,
        headers=auth_headers,
    )
    assert resp.status_code == 404, resp.text


async def _fake_runtime_start(spec):
    return {"status": "started"}
