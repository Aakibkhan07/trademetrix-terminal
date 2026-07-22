"""Tests for user strategy server runner (time-based square-off)."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from engine.user_strategy_runner import (
    UserStrategyRunner, _mark_squared_off_today,
)


@pytest.mark.asyncio
async def test_square_off_triggers_at_exit_time():
    """Square-off fires when current time >= exit_time and day matches."""
    runner = UserStrategyRunner()

    mock_rows = [
        {
            "id": "strat-1",
            "user_id": "user-1",
            "exit_time": "10:00",
            "days_of_week": [1, 2, 3, 4, 5],
            "underlying_from": "cash",
            "strategy_type": "intraday",
            "name": "Test",
        },
    ]

    with patch("engine.user_strategy_runner.async_safe_execute", AsyncMock(return_value=mock_rows)), \
         patch("engine.user_strategy_runner._mark_squared_off_today", AsyncMock(return_value=True)), \
         patch("engine.user_strategy_runner._get_open_legs", AsyncMock(return_value=[
             {"leg_order": 1, "symbol": "NIFTY...CE", "side": "buy", "quantity": 65},
         ])), \
         patch("engine.user_strategy_runner.handle_square_off", AsyncMock(return_value=[
             {"leg_order": 1, "result": {"success": True, "reason": ""}},
         ])) as mock_sqoff:

        ist_now = datetime(2026, 7, 6, 10, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        await runner._check_square_off(ist_now)

        assert mock_sqoff.called


@pytest.mark.asyncio
async def test_square_off_skips_before_exit():
    """Square-off does NOT fire before exit_time."""
    runner = UserStrategyRunner()

    mock_rows = [
        {
            "id": "strat-1",
            "user_id": "user-1",
            "exit_time": "15:00",
            "days_of_week": [1, 2, 3, 4, 5],
            "underlying_from": "cash",
            "strategy_type": "intraday",
            "name": "Test",
        },
    ]

    with patch("engine.user_strategy_runner.async_safe_execute", AsyncMock(return_value=mock_rows)), \
         patch("engine.user_strategy_runner.handle_square_off", AsyncMock()) as mock_sqoff:

        ist_now = datetime(2026, 7, 6, 10, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        await runner._check_square_off(ist_now)

        assert not mock_sqoff.called


@pytest.mark.asyncio
async def test_square_off_skips_weekend():
    """Square-off does NOT fire on days outside days_of_week."""
    runner = UserStrategyRunner()

    mock_rows = [
        {
            "id": "strat-1",
            "user_id": "user-1",
            "exit_time": "10:00",
            "days_of_week": [1, 2, 3, 4, 5],  # Mon-Fri
            "underlying_from": "cash",
            "strategy_type": "intraday",
            "name": "Test",
        },
    ]

    with patch("engine.user_strategy_runner.async_safe_execute", AsyncMock(return_value=mock_rows)), \
         patch("engine.user_strategy_runner.handle_square_off", AsyncMock()) as mock_sqoff:

        # Sunday (day 7 in isoweekday)
        ist_now = datetime(2026, 7, 5, 15, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        await runner._check_square_off(ist_now)

        assert not mock_sqoff.called


@pytest.mark.asyncio
async def test_square_off_skips_already_done():
    """Square-off skips if already squared off today."""
    runner = UserStrategyRunner()

    mock_rows = [
        {
            "id": "strat-1",
            "user_id": "user-1",
            "exit_time": "10:00",
            "days_of_week": [1, 2, 3, 4, 5],
            "underlying_from": "cash",
            "strategy_type": "intraday",
            "name": "Test",
        },
    ]

    with patch("engine.user_strategy_runner.async_safe_execute", AsyncMock(return_value=mock_rows)), \
         patch("engine.user_strategy_runner._mark_squared_off_today", AsyncMock(return_value=False)), \
         patch("engine.user_strategy_runner.handle_square_off", AsyncMock()) as mock_sqoff:

        ist_now = datetime(2026, 7, 6, 15, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        await runner._check_square_off(ist_now)

        assert not mock_sqoff.called


@pytest.mark.asyncio
async def test_square_off_no_active_strategies():
    """No active strategies → no-op."""
    runner = UserStrategyRunner()

    with patch("engine.user_strategy_runner.async_safe_execute", AsyncMock(return_value=[])), \
         patch("engine.user_strategy_runner.handle_square_off", AsyncMock()) as mock_sqoff:

        ist_now = datetime(2026, 7, 6, 15, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        await runner._check_square_off(ist_now)

        assert not mock_sqoff.called


@pytest.mark.asyncio
async def test_mark_squared_off_cache():
    """Marking square-off persists to Redis with TTL."""
    with patch("engine.user_strategy_runner.cache.set_nx", AsyncMock()) as mock_set:
        await _mark_squared_off_today("user-1", "strat-1")
        assert mock_set.called
        args, kwargs = mock_set.call_args
        assert kwargs.get("ttl") == 86400


@pytest.mark.asyncio
async def test_runner_start_stop():
    """Runner start/stop lifecycle works."""
    runner = UserStrategyRunner()
    assert runner._running is False

    with patch("engine.user_strategy_runner.asyncio.create_task") as mock_task:
        await runner.start()
        assert runner._running is True
        assert mock_task.called

    assert runner._running is True
    await runner.stop()
    assert runner._running is False


@pytest.mark.asyncio
async def test_activate_deactivate_strategy():
    """Activate/deactivate transitions work."""
    runner = UserStrategyRunner()

    with patch("engine.user_strategy_runner.async_safe_single", AsyncMock(return_value={"user_id": "user-1"})), \
         patch("engine.user_strategy_runner.cancel_pending_reentries", AsyncMock()) as mock_cancel:

        await runner.activate_strategy("strat-1")
        await runner.deactivate_strategy("strat-1", reason="test")
        assert mock_cancel.called
