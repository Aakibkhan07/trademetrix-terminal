"""Phase 4.3 lifecycle tests: version control, status transitions, deploy,
validation score, logs, compare, template categories."""

from __future__ import annotations

import pytest

from builder.logs import get_logs, record
from builder.manager import builder_manager
from builder.models import StrategyStatus
from builder.score import score_strategy


async def _make(template: str = "ema_crossover") -> tuple[str, dict]:
    dsl = await builder_manager.create(name="Lifecycle Test", template=template)
    return dsl.id, dsl.model_dump(mode="json")


# ─── Version control ───

@pytest.mark.asyncio
async def test_every_save_creates_version():
    sid, _ = await _make()
    for i in range(3):
        await builder_manager.update(sid, {"name": f"v{i+1}"})
    versions = await builder_manager.get_versions(sid)
    assert len(versions) == 4  # create(v1) + 3 saves
    assert [v["version"] for v in versions] == [1, 2, 3, 4]
    dsl = await builder_manager.get(sid)
    assert dsl.version_number == 4
    assert dsl.name == "v3"


@pytest.mark.asyncio
async def test_compare_versions_detects_changes():
    sid, _ = await _make()
    await builder_manager.update(sid, {"name": "Renamed"})
    diff = await builder_manager.compare(sid, 1, 2)
    assert diff is not None
    kinds = {c["kind"] for c in diff["changes"]}
    assert "changed" in kinds
    name_changes = [c for c in diff["changes"] if c["field"] == "name"]
    assert name_changes and name_changes[0]["to"] == "Renamed"


@pytest.mark.asyncio
async def test_rollback_restores_and_bumps_version():
    sid, _ = await _make()
    await builder_manager.update(sid, {"name": "Changed Name"})
    restored = await builder_manager.rollback(sid, 1)
    assert restored is not None
    assert restored.name == "EMA Crossover"  # v1 snapshot = original template name
    assert restored.version_number == 3
    versions = await builder_manager.get_versions(sid)
    assert len(versions) == 3
    assert versions[-1]["version"] == 3


@pytest.mark.asyncio
async def test_rename_via_update():
    sid, _ = await _make()
    dsl = await builder_manager.update(sid, {"name": "My Renamed Strategy"})
    assert dsl.name == "My Renamed Strategy"


# ─── Status transitions ───

@pytest.mark.asyncio
async def test_status_transition_flow():
    sid, _ = await _make()
    dsl = await builder_manager.get(sid)
    assert dsl.status == StrategyStatus.DRAFT

    await builder_manager.set_status(sid, StrategyStatus.VALIDATED)
    dsl = await builder_manager.get(sid)
    assert dsl.status == StrategyStatus.VALIDATED

    await builder_manager.set_status(sid, StrategyStatus.READY)
    await builder_manager.set_status(sid, StrategyStatus.PAPER)
    dsl = await builder_manager.get(sid)
    assert dsl.status == StrategyStatus.PAPER

    await builder_manager.set_status(sid, StrategyStatus.STOPPED)
    dsl = await builder_manager.get(sid)
    assert dsl.status == StrategyStatus.STOPPED

    await builder_manager.archive(sid)
    dsl = await builder_manager.get(sid)
    assert dsl.status == StrategyStatus.ARCHIVED


# ─── Deployment config ───

@pytest.mark.asyncio
async def test_deployment_config_roundtrip():
    sid, _ = await _make()
    deploy = {
        "mode": "paper",
        "broker": "paper",
        "capital": 25000,
        "risk": {"risk_per_trade": 2.0, "max_daily_loss": 1000},
        "schedule": {"start_time": "09:30", "end_time": "14:30"},
    }
    dsl = await builder_manager.update(sid, {"deployment": deploy})
    assert dsl.deployment.capital == 25000
    assert dsl.deployment.risk.risk_per_trade == 2.0
    assert dsl.deployment.schedule.start_time == "09:30"
    assert dsl.deployment.mode == "paper"


# ─── Validation score ───

@pytest.mark.asyncio
async def test_score_structure_and_fields():
    sid, _ = await _make()
    dsl = await builder_manager.get(sid)
    score = score_strategy(dsl)
    assert 0 <= score.overall <= 100
    assert 0 <= score.quality <= 100
    assert 0 <= score.risk <= 100
    assert 0 <= score.complexity <= 100
    assert 0 <= score.readability <= 100
    assert 0 <= score.readiness <= 100
    assert score.grade in ("A+", "A", "B", "C", "D", "F")
    assert len(score.breakdown) == 5
    assert score.readiness > 0  # valid template with order blocks


# ─── Logs ───

@pytest.mark.asyncio
async def test_logs_record_and_retrieve():
    sid, _ = await _make()
    await record(sid, "lifecycle", "started", user_id="test")
    await record(sid, "signal", "buy signal", level="info")
    await record(sid, "error", "boom", level="error")
    logs = await get_logs(sid)
    kinds = [l["kind"] for l in logs]
    assert "lifecycle" in kinds
    assert "signal" in kinds
    assert "error" in kinds
    assert all(l["strategy_id"] == sid for l in logs)


# ─── Templates ───

@pytest.mark.asyncio
async def test_template_categories():
    templates = await builder_manager.list_templates()
    assert len(templates) == 9
    for t in templates:
        assert t["category"] in ("official", "community", "private")
        assert t["category"] == "official"
