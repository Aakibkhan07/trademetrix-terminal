"""Unit tests for leg-level execution controls.

Covers: trailing SL math (percent + points), re-entry state machine,
square-off trigger, kill-switch cancellation.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from core.models import (
    LegOptionType, LegPosition, LegSegment, SLTargetType, StrikeCriteria,
    UserStrategyLeg,
)
from risk.leg_controls import (
    MAX_REENTRIES, ReentryMode, build_square_off_order,
    cancel_pending_reentries, check_trailing_sl_trigger,
    compute_trailing_stop, execute_leg_control, handle_reentry,
    handle_square_off, handle_trailing_sl,
)


def make_leg(
    leg_order: int = 1,
    trailing_sl_type: SLTargetType | None = SLTargetType.percent,
    trailing_sl_value: float | None = 5.0,
    trailing_activation: float | None = 3.0,
    **kwargs,
) -> UserStrategyLeg:
    return UserStrategyLeg(
        leg_order=leg_order,
        segment=LegSegment.options,
        position=LegPosition.buy,
        option_type=LegOptionType.ce,
        lots=1,
        expiry="weekly",
        strike_criteria=StrikeCriteria.atm_offset,
        strike_value=0.0,
        trailing_sl_type=trailing_sl_type,
        trailing_sl_value=trailing_sl_value,
        trailing_activation=trailing_activation,
        **kwargs,
    )


# ═══════════════════════════════════════════
#  Trailing SL Math — Percent Type
# ═══════════════════════════════════════════

@pytest.mark.asyncio
async def test_trail_percent_not_activated():
    """Trailing not activated when P&L below activation threshold."""
    leg = make_leg(trailing_sl_type=SLTargetType.percent, trailing_sl_value=5.0, trailing_activation=10.0)
    act, stop, is_active = await compute_trailing_stop(leg, 100, 105, "buy")
    assert is_active is False
    assert act is None
    assert stop is None


@pytest.mark.asyncio
async def test_trail_percent_activated_ratchets_up():
    """Trailing activates when activation met, stop ratchets upward for long."""
    leg = make_leg(trailing_sl_type=SLTargetType.percent, trailing_sl_value=5.0, trailing_activation=3.0)
    # entry=100, current=110 (P&L=10% > activation=3%)
    act, stop, is_active = await compute_trailing_stop(leg, 100, 110, "buy")
    assert is_active is True
    assert stop == 110 - (100 * 0.05)  # 105
    assert act == 3.0


@pytest.mark.asyncio
async def test_trail_percent_triggered_long():
    """SL triggers when price falls below trailed stop."""
    leg = make_leg(trailing_sl_type=SLTargetType.percent, trailing_sl_value=5.0, trailing_activation=3.0)
    _, stop, is_active = await compute_trailing_stop(leg, 100, 110, "buy")
    assert is_active is True
    triggered = await check_trailing_sl_trigger(leg, 100, stop, 104, "buy")
    assert triggered is True


@pytest.mark.asyncio
async def test_trail_percent_not_triggered_above_stop():
    """No trigger when price is still above trailed stop."""
    leg = make_leg(trailing_sl_type=SLTargetType.percent, trailing_sl_value=5.0, trailing_activation=3.0)
    _, stop, _ = await compute_trailing_stop(leg, 100, 110, "buy")
    triggered = await check_trailing_sl_trigger(leg, 100, stop, 106, "buy")
    assert triggered is False


@pytest.mark.asyncio
async def test_trail_percent_sell_side():
    """Sell side: stop ratchets downward, triggers when price rises."""
    leg = make_leg(trailing_sl_type=SLTargetType.percent, trailing_sl_value=5.0, trailing_activation=3.0)

    # entry=100 (short), price drops to 90 (P&L=10 > 3% activated)
    _, stop, is_active = await compute_trailing_stop(leg, 100, 90, "sell")
    assert is_active is True
    assert stop == 90 + (100 * 0.05)  # 95

    # price rises to 96 → trigger
    triggered = await check_trailing_sl_trigger(leg, 100, stop, 96, "sell")
    assert triggered is True


# ═══════════════════════════════════════════
#  Trailing SL Math — Points Type
# ═══════════════════════════════════════════

@pytest.mark.asyncio
async def test_trail_points():
    """Points type: trail_by is absolute point value."""
    leg = make_leg(trailing_sl_type=SLTargetType.points, trailing_sl_value=50.0, trailing_activation=0.5)
    # entry=24000, current=24200 (P&L=200 → 0.83% > activation=0.5%)
    _, stop, is_active = await compute_trailing_stop(leg, 24000, 24200, "buy")
    assert is_active is True
    assert stop == 24200 - 50  # 24150


@pytest.mark.asyncio
async def test_trail_points_trigger():
    """Points type: trigger when price drops below stop."""
    leg = make_leg(trailing_sl_type=SLTargetType.points, trailing_sl_value=50.0, trailing_activation=0.5)
    _, stop, _ = await compute_trailing_stop(leg, 24000, 24200, "buy")
    triggered = await check_trailing_sl_trigger(leg, 24000, stop, 24149, "buy")
    assert triggered is True


# ═══════════════════════════════════════════
#  Trailing SL — No trailing configured
# ═══════════════════════════════════════════

@pytest.mark.asyncio
async def test_trail_no_config():
    """No trailing SL configured → returns (None, None, False)."""
    leg = make_leg(trailing_sl_type=None, trailing_sl_value=None, trailing_activation=None)
    act, stop, is_active = await compute_trailing_stop(leg, 100, 110, "buy")
    assert act is None and stop is None and is_active is False


# ═══════════════════════════════════════════
#  Square-Off Order Builder
# ═══════════════════════════════════════════

def test_build_square_off_order_buy_to_sell():
    """Buy leg → square-off order is SELL."""
    order = build_square_off_order("strat-1", "user-1", "NIFTY...CE", "buy", 65, 1)
    assert order.side.value == "SELL"
    assert order.quantity == 65
    assert order.source == "leg_control"
    assert order.is_paper is True


def test_build_square_off_order_sell_to_buy():
    """Sell leg → square-off order is BUY."""
    order = build_square_off_order("strat-1", "user-1", "NIFTY...PE", "sell", 130, 2)
    assert order.side.value == "BUY"
    assert order.quantity == 130


# ═══════════════════════════════════════════
#  Re-entry State Machine
# ═══════════════════════════════════════════

@pytest.mark.asyncio
async def test_reentry_asap():
    """RE_ASAP: re-enters immediately after SL hit."""
    leg = make_leg()
    with patch("risk.leg_controls.resolve_capabilities_by_id", AsyncMock(return_value=Mock(spec=["reentry_squareoff_allowed"], reentry_squareoff_allowed=True))), \
         patch("risk.leg_controls._get_reentry_count", AsyncMock(return_value=0)), \
         patch("risk.leg_controls._set_reentry_count", AsyncMock()), \
         patch("risk.leg_controls.execute_leg_control", AsyncMock(return_value={"success": True, "reason": ""})):

        result = await handle_reentry(
            "user-1", "strat-1", leg, ReentryMode.RE_ASAP,
            100, 105, "buy", "NIFTY...CE", 65,
        )
        assert result["action"] == "re_entered"
        assert result["details"]["count"] == 1


@pytest.mark.asyncio
async def test_reentry_cost_waits():
    """RE_COST: waits until price returns to entry before re-entering."""
    leg = make_leg()
    with patch("risk.leg_controls.resolve_capabilities_by_id", AsyncMock(return_value=Mock(reentry_squareoff_allowed=True))), \
         patch("risk.leg_controls._get_reentry_count", AsyncMock(return_value=0)), \
         patch("risk.leg_controls._set_reentry_count", AsyncMock()) as mock_set, \
         patch("risk.leg_controls.execute_leg_control", AsyncMock(return_value={"success": True, "reason": ""})):

        # price 95 < entry 100 → should re-enter for buy
        result = await handle_reentry(
            "user-1", "strat-1", leg, ReentryMode.RE_COST,
            100, 95, "buy", "NIFTY...CE", 65,
        )
        assert result["action"] == "re_entered"
        assert mock_set.called


@pytest.mark.asyncio
async def test_reentry_cost_blocks_above_entry():
    """RE_COST: blocks re-entry when price is above entry (for buy)."""
    leg = make_leg()
    with patch("risk.leg_controls.resolve_capabilities_by_id", AsyncMock(return_value=Mock(reentry_squareoff_allowed=True))), \
         patch("risk.leg_controls._get_reentry_count", AsyncMock(return_value=0)), \
         patch("risk.leg_controls.execute_leg_control", AsyncMock()) as mock_exec:

        result = await handle_reentry(
            "user-1", "strat-1", leg, ReentryMode.RE_COST,
            100, 110, "buy", "NIFTY...CE", 65,
        )
        assert result["action"] == "skipped"
        assert not mock_exec.called


@pytest.mark.asyncio
async def test_reentry_max_reentries_hard_cap():
    """Hard cap MAX_REENTRIES prevents infinite re-entries."""
    leg = make_leg()
    with patch("risk.leg_controls.resolve_capabilities_by_id", AsyncMock(return_value=Mock(reentry_squareoff_allowed=True))), \
         patch("risk.leg_controls._get_reentry_count", AsyncMock(return_value=MAX_REENTRIES)), \
         patch("risk.leg_controls.execute_leg_control", AsyncMock()) as mock_exec:

        result = await handle_reentry(
            "user-1", "strat-1", leg, ReentryMode.RE_ASAP,
            100, 105, "buy", "NIFTY...CE", 65,
        )
        assert result["action"] == "skipped"
        assert not mock_exec.called


@pytest.mark.asyncio
async def test_reentry_count_persists():
    """Re-entry counter increments (simulating Redis persist)."""
    leg = make_leg()
    _counter = 0

    async def mock_get(*args, **kwargs):
        return _counter

    async def mock_set(*args, **kwargs):
        nonlocal _counter
        _counter = args[3]  # count is 4th positional arg

    with patch("risk.leg_controls.resolve_capabilities_by_id", AsyncMock(return_value=Mock(reentry_squareoff_allowed=True))), \
         patch("risk.leg_controls._get_reentry_count", side_effect=mock_get), \
         patch("risk.leg_controls._set_reentry_count", side_effect=mock_set), \
         patch("risk.leg_controls.execute_leg_control", AsyncMock(return_value={"success": True, "reason": ""})):

        for i in range(3):
            result = await handle_reentry(
                "user-1", "strat-1", leg, ReentryMode.RE_ASAP,
                100, 105, "buy", "NIFTY...CE", 65,
            )
            assert result["action"] == "re_entered"
            assert result["details"]["count"] == i + 1

        result = await handle_reentry(
            "user-1", "strat-1", leg, ReentryMode.RE_ASAP,
            100, 105, "buy", "NIFTY...CE", 65,
        )
        assert result["action"] == "skipped"


# ═══════════════════════════════════════════
#  Square-Off — Idempotency
# ═══════════════════════════════════════════

@pytest.mark.asyncio
async def test_square_off_already_done():
    """Already squared-off leg is skipped."""
    with patch("risk.leg_controls._is_squared_off", AsyncMock(return_value=True)), \
         patch("risk.leg_controls.execute_leg_control", AsyncMock()) as mock_exec:

        results = await handle_square_off("user-1", "strat-1", [
            {"leg_order": 1, "symbol": "NIFTY...CE", "side": "buy", "quantity": 65},
        ], "15:00")
        assert len(results) == 0
        assert not mock_exec.called


# ═══════════════════════════════════════════
#  Restart-Safety — Redis Persistence
# ═══════════════════════════════════════════

@pytest.mark.asyncio
async def test_restart_safety_persists_counter():
    """Re-entry counter survives process restart via Redis (ttl=86400)."""
    import risk.leg_controls as lc
    leg = make_leg()

    # Process A: set counter to 2 and crash
    await lc._set_reentry_count("user-r", "strat-r", 1, 2)

    # Process B: starts fresh, reads counter from Redis
    with patch.object(lc, "_get_reentry_count", AsyncMock(return_value=2)):
        count = await lc._get_reentry_count("user-r", "strat-r", 1)
        assert count == 2

    # Process B: tries re-entry, blocked at max (counter=3 = MAX_REENTRIES)
    with patch.object(lc, "resolve_capabilities_by_id", AsyncMock(return_value=Mock(reentry_squareoff_allowed=True))), \
         patch.object(lc, "_get_reentry_count", AsyncMock(return_value=MAX_REENTRIES)), \
         patch.object(lc, "execute_leg_control", AsyncMock()) as mock_exec:
        result = await handle_reentry(
            "user-r", "strat-r", leg, ReentryMode.RE_ASAP,
            100, 105, "buy", "NIFTY...CE", 65,
        )
        assert result["action"] == "skipped"
        assert not mock_exec.called


# ═══════════════════════════════════════════
#  Kill-Switch — Cancels Pending Re-entries
# ═══════════════════════════════════════════

@pytest.mark.asyncio
async def test_cancel_pending_reentries():
    """Kill switch cancels all pending re-entries."""
    with patch("risk.leg_controls.cache.delete", AsyncMock()) as mock_del, \
         patch("risk.leg_controls._record_audit", AsyncMock()) as mock_audit:

        await cancel_pending_reentries("user-1", "strat-1", reason="kill_switch")
        # 6 leg keys + 6 squared-off keys = 12 deletes
        assert mock_del.call_count == 12
        assert mock_audit.called


# ═══════════════════════════════════════════
#  Execute Leg Control — RiskGuard Integration
# ═══════════════════════════════════════════

@pytest.mark.asyncio
async def test_leg_control_blocked_by_riskguard():
    """RiskGuard blocks leg control when kills switch active."""
    from core.models import NormalizedOrder, OrderSide, OrderType, ProductType, Exchange
    mock_order = NormalizedOrder(
        symbol="NIFTY...CE", exchange=Exchange.NFO, side=OrderSide.SELL,
        order_type=OrderType.MARKET, product=ProductType.INTRADAY, quantity=65,
    )
    with patch("risk.leg_controls.RiskGuard.check_order", AsyncMock(return_value={
        "allowed": False, "reason": "Kill switch is enabled. All trading halted."
    })), patch("risk.leg_controls._record_audit", AsyncMock()):
        result = await execute_leg_control("user-1", "strat-1", mock_order, "test")
        assert result["success"] is False
        assert "kill switch" in result["reason"].lower()
