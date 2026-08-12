"""Regression tests: Beta Hardening Sprint — kill switch reliability.

Covers: emergency-stop state persisted to Redis (survives restarts), audit
trail fallback to `audit_log` when `risk_audit_log` is missing on the schema,
and the global kill switch reading the Redis `global:kill_switch` flag (the
old DB probe with user_id='system' could never match the uuid FK column).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from risk.kill_switch import KillSwitch


@pytest.mark.asyncio
async def test_global_kill_switch_reads_redis():
    ks = KillSwitch()
    with patch("risk.kill_switch.cache.get", AsyncMock(return_value="1")):
        assert await ks.global_kill_switch_active() is True
    with patch("risk.kill_switch.cache.get", AsyncMock(return_value=None)):
        assert await ks.global_kill_switch_active() is False
    with patch("risk.kill_switch.cache.get", AsyncMock(side_effect=Exception("redis down"))):
        assert await ks.global_kill_switch_active() is False


@pytest.mark.asyncio
async def test_global_kill_switch_active_for_raw_redis_int():
    """Raw `redis-cli SET global:kill_switch 1` round-trips through
    json.loads as the int 1 (not the string "1"). The gate must still
    engage — a fail-open here silently disables the kill switch."""
    ks = KillSwitch()
    with patch("risk.kill_switch.cache.get", AsyncMock(return_value=1)):
        assert await ks.global_kill_switch_active() is True


@pytest.mark.asyncio
async def test_kill_switch_rule_halts_on_raw_redis_int():
    from risk.rules import KillSwitchRule

    rule = KillSwitchRule()
    config = MagicMock(kill_switch_enabled=False)
    req = MagicMock()
    with patch("risk.rules.cache.get", AsyncMock(return_value=1)):
        result = await rule.evaluate(req, config)
    assert result.decision.value == "REJECTED"
    assert "Kill switch" in result.reason


@pytest.mark.asyncio
async def test_risk_guard_halts_on_raw_redis_int():
    from risk.riskguard import RiskGuard

    guard = RiskGuard("u1")
    order = MagicMock(is_paper=True)
    with (
        patch("core.cache.cache.get", AsyncMock(return_value=1)),
        patch("risk.riskguard.RiskSettings", MagicMock()),
    ):
        outcome = await guard.check_order(order)
    assert outcome["allowed"] is False
    assert "GLOBAL_KILL_SWITCH" in outcome["reason"]


@pytest.mark.asyncio
async def test_admin_kill_switch_reads_raw_redis_int():
    from application.services.admin_service import AdminService

    svc = AdminService()
    with patch("application.services.admin_service.cache.get", AsyncMock(return_value=1)):
        status = await svc.get_kill_switch()
    assert status["kill_switch"] is True


@pytest.mark.asyncio
async def test_trigger_persists_emergency_state_to_redis():
    ks = KillSwitch()
    fake_r = AsyncMock()
    with (
        patch.object(ks, "_emergency_stops", {}),
        patch("risk.kill_switch.cache.get_redis", AsyncMock(return_value=fake_r)),
        patch("risk.kill_switch._persist_audit", AsyncMock(return_value=True)),
    ):
        ok = await ks.trigger_emergency_stop("u1", reason="test")
        assert ok is True
        assert ks._emergency_stops["u1"] is True
    fake_r.set.assert_awaited_once_with("kill_switch:emergency:u1", "1")


@pytest.mark.asyncio
async def test_release_clears_emergency_state_from_redis():
    ks = KillSwitch()
    fake_r = AsyncMock()
    with (
        patch.object(ks, "_emergency_stops", {"u1": True}),
        patch("risk.kill_switch.cache.get_redis", AsyncMock(return_value=fake_r)),
        patch("risk.kill_switch._persist_audit", AsyncMock(return_value=True)),
    ):
        await ks.release_emergency_stop("u1", triggered_by="admin")
        assert ks._emergency_stops["u1"] is False
    fake_r.delete.assert_awaited_once_with("kill_switch:emergency:u1")


@pytest.mark.asyncio
async def test_recover_restores_emergency_stops_from_redis():
    ks = KillSwitch()
    fake_r = AsyncMock()
    fake_r.keys.return_value = ["kill_switch:emergency:u1", "kill_switch:emergency:u2"]
    with (
        patch.object(ks, "_emergency_stops", {}),
        patch("risk.kill_switch.cache.get_redis", AsyncMock(return_value=fake_r)),
        patch("risk.kill_switch.async_safe_execute", return_value=[]),
    ):
        await ks.recover()
        assert ks._emergency_stops == {"u1": True, "u2": True}


@pytest.mark.asyncio
async def test_audit_falls_back_to_audit_log_table():
    from risk.kill_switch import _persist_audit

    calls = {"n": 0}

    async def fake_async(call, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("PGRST205: Could not find the table 'public.risk_audit_log'")
        return MagicMock()

    with (
        patch("risk.kill_switch.async_supabase", side_effect=fake_async),
        patch("risk.kill_switch.get_supabase"),
    ):
        ok = await _persist_audit("u1", "EMERGENCY_STOP", "test", "admin")
    assert ok is True
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_audit_returns_false_when_all_tables_missing():
    from risk.kill_switch import _persist_audit

    async def fake_async(call, *args, **kwargs):
        raise Exception("PGRST205: table missing")

    with (
        patch("risk.kill_switch.async_supabase", side_effect=fake_async),
        patch("risk.kill_switch.get_supabase"),
    ):
        ok = await _persist_audit("u1", "EMERGENCY_STOP", "test", "admin")
    assert ok is False


@pytest.mark.asyncio
async def test_fail_closed_trading_still_halts_when_audit_missing():
    ks = KillSwitch()
    # Audit persistence failing (missing table) must NOT prevent the
    # in-memory flag from engaging — in-memory first, persist best-effort.
    with (
        patch.object(ks, "_emergency_stops", {}),
        patch("risk.kill_switch.cache.get_redis", AsyncMock(return_value=None)),
        patch("risk.kill_switch.async_supabase", side_effect=Exception("table missing")),
    ):
        ok = await ks.trigger_emergency_stop("u1", reason="test")
        assert ok is False  # audit failed
        assert ks.active("u1") is True  # trading still halted