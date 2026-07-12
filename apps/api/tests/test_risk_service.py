from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from application.services.risk_service import RiskService
from core.capabilities import Capabilities


@pytest.fixture
def svc() -> RiskService:
    return RiskService()


@pytest.fixture
def mock_riskguard() -> Generator[MagicMock, None, None]:
    with patch("application.services.risk_service.RiskGuard") as m:
        inst = MagicMock()
        inst.update_settings = AsyncMock()
        inst.enable_kill_switch = AsyncMock()
        inst.disable_kill_switch = AsyncMock()
        inst.get_kill_switch_status = AsyncMock()
        inst.enable_live = AsyncMock()
        inst.disable_live = AsyncMock()
        inst.get_live_status = AsyncMock()
        m.return_value = inst
        yield inst


@pytest.fixture
def mock_db() -> Generator[dict, None, None]:
    with (
        patch("application.services.risk_service.get_supabase") as mock_get,
        patch("application.services.risk_service.async_safe_execute") as mock_execute,
    ):
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_get.return_value.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_execute.return_value = None
        yield {"get_supabase": mock_get, "async_safe_execute": mock_execute, "table": mock_table, "select": mock_select}


class TestGetSettings:
    @pytest.mark.asyncio
    async def test_returns_settings(self, svc, mock_db) -> None:
        mock_db["async_safe_execute"].return_value = [{"id": "1", "max_daily_loss": 50000}]

        result = await svc.get_settings("u1")

        assert result == {"settings": [{"id": "1", "max_daily_loss": 50000}]}

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_data(self, svc, mock_db) -> None:
        mock_db["async_safe_execute"].return_value = []

        result = await svc.get_settings("u1")

        assert result == {"settings": []}

    @pytest.mark.asyncio
    async def test_handles_none_response(self, svc, mock_db) -> None:
        mock_db["async_safe_execute"].return_value = None

        result = await svc.get_settings("u1")

        assert result == {"settings": []}


class TestUpdateSettings:
    @pytest.fixture
    def caps(self) -> Capabilities:
        return Capabilities(
            tier="enterprise", max_active_strategies=15,
            trailing_sl_allowed=True, reentry_squareoff_allowed=True,
            builder_allowed=True, custom_strategy_dev_allowed=True,
            backtest_allowed=True, backtest_years=5,
            daily_loss_floor=10000.0, live_trading_allowed=True,
        )

    @pytest.fixture
    def req(self) -> MagicMock:
        return MagicMock(
            strategy_id="strat-1", max_capital=100000, max_position_size=5000,
            max_open_positions=5, max_daily_loss=50000, max_drawdown_pct=10.0,
        )

    @pytest.mark.asyncio
    async def test_updates_settings(self, svc, mock_riskguard, mock_db, caps, req) -> None:
        result = await svc.update_settings("u1", req, caps)

        assert result == {"message": "Risk settings updated"}
        mock_riskguard.update_settings.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_when_max_daily_loss_is_zero(self, svc, mock_riskguard, mock_db, caps, req) -> None:
        req.max_daily_loss = 0

        with pytest.raises(HTTPException) as exc:
            await svc.update_settings("u1", req, caps)
        assert exc.value.status_code == 400
        assert "cannot be disabled" in exc.value.detail

    @pytest.mark.asyncio
    async def test_raises_when_below_tier_floor(self, svc, mock_riskguard, mock_db, caps, req) -> None:
        req.max_daily_loss = 5000

        with pytest.raises(HTTPException) as exc:
            await svc.update_settings("u1", req, caps)
        assert exc.value.status_code == 400
        assert "below your tier floor" in exc.value.detail


class TestKillSwitch:
    @pytest.mark.asyncio
    async def test_enables(self, svc, mock_riskguard) -> None:
        result = await svc.enable_kill_switch("u1")

        assert result == {"message": "Kill switch enabled"}
        mock_riskguard.enable_kill_switch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disables(self, svc, mock_riskguard) -> None:
        result = await svc.disable_kill_switch("u1")

        assert result == {"message": "Kill switch disabled"}
        mock_riskguard.disable_kill_switch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_status(self, svc, mock_riskguard) -> None:
        mock_riskguard.get_kill_switch_status.return_value = True

        result = await svc.kill_switch_status("u1")

        assert result == {"kill_switch_enabled": True}
        mock_riskguard.get_kill_switch_status.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_status_when_disabled(self, svc, mock_riskguard) -> None:
        mock_riskguard.get_kill_switch_status.return_value = False

        result = await svc.kill_switch_status("u1")

        assert result == {"kill_switch_enabled": False}


class TestLiveMode:
    @pytest.mark.asyncio
    async def test_enables_with_confirm(self, svc, mock_riskguard) -> None:
        mock_riskguard.enable_live.return_value = True

        result = await svc.enable_live("u1", confirm=True)

        assert result == {"message": "LIVE trading enabled"}
        mock_riskguard.enable_live.assert_awaited_once_with(multi_step_confirm=True)

    @pytest.mark.asyncio
    async def test_enable_fails_without_confirm(self, svc, mock_riskguard) -> None:
        mock_riskguard.enable_live.return_value = False

        with pytest.raises(HTTPException) as exc:
            await svc.enable_live("u1", confirm=False)
        assert exc.value.status_code == 400
        assert "Multi-step confirmation required" in exc.value.detail

    @pytest.mark.asyncio
    async def test_disables(self, svc, mock_riskguard) -> None:
        result = await svc.disable_live("u1")

        assert result == {"message": "LIVE trading disabled"}
        mock_riskguard.disable_live.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_status(self, svc, mock_riskguard) -> None:
        mock_riskguard.get_live_status.return_value = True

        result = await svc.live_status("u1")

        assert result == {"is_live": True}

    @pytest.mark.asyncio
    async def test_status_when_disabled(self, svc, mock_riskguard) -> None:
        mock_riskguard.get_live_status.return_value = False

        result = await svc.live_status("u1")

        assert result == {"is_live": False}
