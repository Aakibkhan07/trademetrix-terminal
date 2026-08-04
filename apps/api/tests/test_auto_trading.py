"""Auto Trading v1.0 — trading-mode, confirmation, kill-switch/emergency and
risk-limit tests built on the Strategy Runtime.

Covers the pipeline guarantees: never place live orders accidentally, explicit
LIVE confirmation, persisted trading mode, kill switch / emergency stop halts
everything, and per-strategy risk limits (max daily trades / max positions /
max exposure) are enforced at order time.
"""
import pytest

from strategy_runtime.mode import (
    ModeGuardError,
    assert_orders_allowed,
    confirm_live,
    normalize_mode,
)

# reuse the runtime test harness (fixture + fake strategy + candle emitter)
from tests.test_strategy_runtime import (
    FakeStrategy,
    _clean_runtime as _runtime_clean,
    _emit_closed_candle,
    _spec,
    USER,
    SID_A,
    SID_B,
)

USER = USER
SID_A = SID_A
SID_B = SID_B


@pytest.fixture(autouse=True)
def _clear_emergency(_runtime_clean):
    """Per-test reset of the process-wide kill-switch flags (they otherwise
    leak between tests: once triggered, every later start would be refused).
    Also clears the Redis-persisted emergency-stop keys written by trigger."""
    import asyncio

    from risk.kill_switch import EMERGENCY_REDIS_PREFIX, kill_switch

    kill_switch._emergency_stops.clear()

    async def _clean_redis():
        try:
            from core.cache import cache
            r = await cache.get_redis()
            if r:
                keys = await r.keys(f"{EMERGENCY_REDIS_PREFIX}*")
                for key in keys or []:
                    await r.delete(key)
        except Exception:
            pass

    asyncio.run(_clean_redis())


# -- trading-mode normalisation -------------------------------------------------
def test_normalize_paper():
    d = normalize_mode("paper", None, broker="")
    assert d.is_paper is True and d.broker == "paper" and d.confirmed is True
    assert d.mode == "paper"


def test_normalize_paper_explicit_is_paper_false_conflicts():
    d = normalize_mode("paper", False, broker="paper")
    assert d.rejected is True and d.code == "MODE_CONFLICT"


def test_normalize_live_requires_broker():
    d = normalize_mode("live", None, broker="")
    assert d.rejected is True and d.code == "MODE_NO_BROKER"
    d2 = normalize_mode("live", None, broker="paper")
    assert d2.rejected is True and d2.code == "MODE_NO_BROKER"


def test_normalize_live_requires_confirmation():
    d = normalize_mode("live", None, broker="fyers", account="acc1")
    assert d.rejected is False and d.confirmed is False and d.mode == "live"
    assert d.is_paper is False


def test_normalize_unknown_mode():
    d = normalize_mode("simulation", None)
    assert d.rejected is True and d.code == "MODE_UNKNOWN"


@pytest.mark.asyncio
async def test_confirm_live_gate(monkeypatch):
    from strategy_runtime import mode as mode_mod

    async def _has(user_id, broker):
        return True

    async def _has_not(user_id, broker):
        return False

    monkeypatch.setattr(mode_mod, "_user_has_broker_account", _has_not)
    d = normalize_mode("live", None, broker="fyers")
    out = await confirm_live(d, USER, confirm_live=False)
    assert out.rejected is True and out.code == "LIVE_CONFIRMATION_REQUIRED"

    out = await confirm_live(d, USER, confirm_live=True)
    assert out.rejected is True and out.code == "MODE_NO_ACCOUNT"

    monkeypatch.setattr(mode_mod, "_user_has_broker_account", _has)
    out = await confirm_live(d, USER, confirm_live=True)
    assert out.rejected is False and out.confirmed is True


@pytest.mark.asyncio
async def test_kill_switch_gate_blocks(monkeypatch):
    from risk.kill_switch import kill_switch as ks

    monkeypatch.setattr(ks, "active", lambda uid: True)
    with pytest.raises(ModeGuardError) as ei:
        await assert_orders_allowed(USER)
    assert ei.value.code == "EMERGENCY_STOP_ACTIVE"


# ---------------------------------------------------------------- manager guard
@pytest.mark.asyncio
async def test_live_unconfirmed_refused(_runtime_clean):
    mgr = _runtime_clean
    spec = _spec(SID_A, broker="fyers").model_copy(
        update={"mode": "live", "is_paper": False, "confirmed": False})
    out = await mgr.start_strategy(spec)
    assert out["status"] == "refused"
    assert out["code"] == "LIVE_CONFIRMATION_REQUIRED"


@pytest.mark.asyncio
async def test_live_confirmed_starts(_runtime_clean):
    mgr = _runtime_clean
    spec = _spec(SID_A, broker="fyers").model_copy(
        update={"mode": "live", "is_paper": False, "confirmed": True})
    out = await mgr.start_strategy(spec)
    assert out["status"] == "started"
    status = await mgr.get_status(SID_A, user_id=USER)
    assert status["state"] == "RUNNING"
    assert status["mode"] == "live"


@pytest.mark.asyncio
async def test_live_mode_persisted_in_checkpoint(_runtime_clean):
    mgr = _runtime_clean
    spec = _spec(SID_A, broker="fyers").model_copy(
        update={"mode": "live", "is_paper": False, "confirmed": True})
    await mgr.start_strategy(spec)
    saved = mgr._state_store._store._rows.get((USER, "strategy_runtime", SID_A))
    assert saved is not None
    spec = saved.get("spec", {})
    assert spec.get("mode") == "live" and spec.get("confirmed") is True
    assert saved["state"] == "RUNNING"


# ---------------------------------------------------------------- emergency stop
@pytest.mark.asyncio
async def test_emergency_stop_pauses_and_blocks_new(_runtime_clean):
    mgr = _runtime_clean
    await mgr.start_strategy(_spec(SID_A))
    assert (await mgr.get_status(SID_A, user_id=USER))["state"] == "RUNNING"
    res = await mgr.emergency_stop(USER, reason="test")
    assert res["status"] == "emergency_stopped"
    assert SID_A in res["halted"]
    assert (await mgr.get_status(SID_A, user_id=USER))["state"] == "PAUSED"
    # new strategy start blocked while emergency is active
    out = await mgr.start_strategy(_spec(SID_B))
    assert out["status"] == "refused"
    assert out["code"] == "EMERGENCY_STOP_ACTIVE"
    # release → can start again
    await mgr.release_emergency_stop(USER, triggered_by="test")
    out2 = await mgr.start_strategy(_spec(SID_B))
    assert out2["status"] == "started"


@pytest.mark.asyncio
async def test_pause_all_halts_everything(_runtime_clean):
    mgr = _runtime_clean
    await mgr.start_strategy(_spec(SID_A))
    await mgr.start_strategy(_spec(SID_B))
    res = await mgr.pause_all(USER, reason="test")
    assert len(res["halted"]) == 2
    assert (await mgr.get_status(SID_A, user_id=USER))["state"] == "PAUSED"
    assert (await mgr.get_status(SID_B, user_id=USER))["state"] == "PAUSED"


# ---------------------------------------------------------------- worker limits
@pytest.mark.asyncio
async def test_max_daily_trades_blocks_patiently(_runtime_clean):
    mgr = _runtime_clean
    spec = _spec(SID_A, warmup=False).model_copy(
        update={"max_daily_trades": 1, "max_positions": 0, "max_risk_per_trade": 0.0})
    await mgr.start_strategy(spec)
    await _emit_closed_candle(close=101.0, ts="2026-08-04T09:15:00")
    await _emit_closed_candle(close=102.0, ts="2026-08-04T09:30:00")
    status = await mgr.get_status(SID_A, user_id=USER)
    assert status["stats"]["orders_placed"] == 1
    assert status["stats"]["orders_rejected"] >= 1


@pytest.mark.asyncio
async def test_max_positions_blocks_new_entry(_runtime_clean, monkeypatch):
    from execution_engine import positions as positions_mod

    class _OpenPos:
        symbol = "NIFTY"
        quantity = 5
        average_price = 100.0

    def _has_open_position(self, user_id, broker):
        return [_OpenPos()]

    monkeypatch.setattr(positions_mod, "position_manager",
                        type("stub", (), {"get_positions": _has_open_position})())
    mgr = _runtime_clean
    spec = _spec(SID_A, warmup=False).model_copy(
        update={"max_positions": 1, "max_daily_trades": 0, "max_risk_per_trade": 0.0})
    await mgr.start_strategy(spec)
    await _emit_closed_candle(close=101.0, ts="2024-08-02T09:15:00")
    status = await mgr.get_status(SID_A, user_id=USER)
    assert status["stats"]["orders_placed"] == 0
    assert status["stats"]["orders_rejected"] >= 1


@pytest.mark.asyncio
async def test_max_risk_per_trade_blocks_exposure(_runtime_clean):
    mgr = _runtime_clean
    spec = _spec(SID_A, warmup=False).model_copy(
        update={"max_positions": 0, "max_daily_trades": 0, "max_risk_per_trade": 500.0})
    await mgr.start_strategy(spec)
    # order qty 10 at close ~101 → notional ~1010 > 500 → blocked
    await _emit_closed_candle(close=101.0, ts="2024-08-02T09:15:00")
    status = await mgr.get_status(SID_A, user_id=USER)
    assert status["stats"]["orders_placed"] == 0
    assert status["stats"]["orders_rejected"] >= 1


@pytest.mark.asyncio
async def test_emergency_stop_blocks_runtime_order(_runtime_clean):
    mgr = _runtime_clean
    await mgr.start_strategy(_spec(SID_A, warmup=False))
    await mgr.emergency_stop(USER, reason="mid-run")
    # resume against the active emergency → next candle order is blocked
    await mgr.resume_strategy(SID_A, user_id=USER)
    await _emit_closed_candle(close=101.0, ts="2024-08-02T09:15:00")
    status = await mgr.get_status(SID_A, user_id=USER)
    assert status["stats"]["orders_placed"] == 0
    assert status["stats"]["orders_rejected"] >= 1


# --------------------------------------------------------------------- reconcile
@pytest.mark.asyncio
async def test_reconcile_shape(_runtime_clean):
    mgr = _runtime_clean
    await mgr.start_strategy(_spec(SID_A))
    out = await mgr.reconcile(SID_A, user_id=USER)
    assert "runtime" in out and "checks" in out
    assert out["mode"] == "paper"
    assert out["broker"] == "paper"


@pytest.mark.asyncio
async def test_reconcile_unknown_strategy(_runtime_clean):
    mgr = _runtime_clean
    out = await mgr.reconcile("nope-000000", user_id=USER)
    assert out["status"] == "not_found"
