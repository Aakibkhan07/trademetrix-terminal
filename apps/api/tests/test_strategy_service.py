from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from application.services.strategy_service import StrategyService
from core.models import (
    CreateUserStrategyRequest, DeployStrategyRequest, UpdateUserStrategyRequest,
    UserProfile, UserStrategyLeg,
)
from core.capabilities import Capabilities


@pytest.fixture
def svc() -> StrategyService:
    return StrategyService()


@pytest.fixture
def mock_supabase() -> Generator[dict, None, None]:
    with (
        patch("application.services.strategy_service.async_supabase") as mock_async,
        patch("application.services.strategy_service.get_supabase") as mock_get,
        patch("application.services.strategy_service.async_safe_execute") as mock_execute,
        patch("application.services.strategy_service.async_safe_single") as mock_single,
        patch("application.services.strategy_service.validate_user_strategy"),
    ):
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_get.return_value.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.order.return_value = mock_select
        mock_select.neq.return_value = mock_select
        mock_single.return_value = None
        mock_execute.return_value = None
        yield {
            "async_supabase": mock_async,
            "get_supabase": mock_get,
            "async_safe_execute": mock_execute,
            "async_safe_single": mock_single,
            "table": mock_table,
            "select": mock_select,
        }


def make_user(role="user") -> UserProfile:
    return UserProfile(id="u1", email="test@test.com", full_name="Test", subscription_tier="enterprise", role=role)


def make_caps() -> Capabilities:
    return Capabilities(
        tier="enterprise", max_active_strategies=15,
        trailing_sl_allowed=True, reentry_squareoff_allowed=True,
        builder_allowed=True, custom_strategy_dev_allowed=True,
        backtest_allowed=True, backtest_years=5,
        daily_loss_floor=10000.0, live_trading_allowed=True,
    )


def make_strategy_row(overrides=None) -> dict:
    row = {
        "id": "s1", "name": "Test Strat", "user_id": "u1",
        "strategy_type": "intraday", "index_symbol": "NIFTY",
        "underlying_from": "futures", "entry_time": "09:15", "exit_time": "15:15",
        "days_of_week": [1, 2, 3, 4, 5], "legs": [],
    }
    if overrides:
        row.update(overrides)
    return row


class TestListStrategies:
    @pytest.mark.asyncio
    async def test_lists_all_strategies(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_execute"].return_value = [make_strategy_row()]

        result = await svc.list_strategies("u1")

        assert len(result) == 1
        assert result[0].name == "Test Strat"

    @pytest.mark.asyncio
    async def test_filters_by_status(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_execute"].return_value = []

        result = await svc.list_strategies("u1", status_filter="active")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_none(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_execute"].return_value = None

        result = await svc.list_strategies("u1")

        assert result == []


class TestCreateStrategy:
    @pytest.mark.asyncio
    async def test_creates_strategy(self, svc, mock_supabase) -> None:
        req = CreateUserStrategyRequest(
            name="Test Strat", strategy_type="intraday", index_symbol="NIFTY",
            entry_time="09:15", exit_time="15:15", legs=[],
        )
        mock_supabase["async_supabase"].return_value.data = [{"id": "strat-1"}]

        result = await svc.create_strategy(req, make_user(), make_caps())

        assert result["id"] == "strat-1"
        assert result["message"] == "Strategy created"

    @pytest.mark.asyncio
    async def test_rejects_exceeding_cap(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_execute"].return_value = [{"id": f"s{i}"} for i in range(15)]
        req = CreateUserStrategyRequest(
            name="Extra", strategy_type="intraday", index_symbol="NIFTY",
            entry_time="09:15", exit_time="15:15", legs=[],
        )

        with pytest.raises(ValueError, match="Your plan allows a maximum of 15 active strategies"):
            await svc.create_strategy(req, make_user(), make_caps())

    @pytest.mark.asyncio
    async def test_skips_cap_check_for_super_admin(self, svc, mock_supabase) -> None:
        mock_supabase["async_supabase"].return_value.data = [{"id": "s1"}]
        req = CreateUserStrategyRequest(
            name="Admin Strat", strategy_type="intraday", index_symbol="NIFTY",
            entry_time="09:15", exit_time="15:15", legs=[],
        )

        result = await svc.create_strategy(req, make_user(role="super_admin"), make_caps())

        assert result["id"] == "s1"

    @pytest.mark.asyncio
    async def test_creates_with_legs(self, svc, mock_supabase) -> None:
        mock_supabase["async_supabase"].return_value.data = [{"id": "s1"}]
        leg = UserStrategyLeg(
            leg_order=1, segment="options", position="buy",
            lots=1, expiry="weekly", strike_criteria="atm_offset",
            strike_value=0.0,
        )
        req = CreateUserStrategyRequest(
            name="Leg Strat", strategy_type="intraday", index_symbol="NIFTY",
            entry_time="09:15", exit_time="15:15", legs=[leg],
        )

        result = await svc.create_strategy(req, make_user(), make_caps())

        assert result["id"] == "s1"


class TestGetStrategy:
    @pytest.mark.asyncio
    async def test_returns_strategy(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = make_strategy_row()

        strategy = await svc.get_strategy("u1", "s1")

        assert strategy.name == "Test Strat"

    @pytest.mark.asyncio
    async def test_raises_when_not_found(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = None

        with pytest.raises(ValueError, match="Strategy not found"):
            await svc.get_strategy("u1", "nonexistent")


class TestDeleteStrategy:
    @pytest.mark.asyncio
    async def test_deletes_strategy(self, svc, mock_supabase) -> None:
        await svc.delete_strategy("u1", "s1")

        mock_supabase["async_supabase"].assert_awaited_once()


class TestUpdateStrategy:
    @pytest.mark.asyncio
    async def test_updates_fields(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = {"id": "s1"}
        req = UpdateUserStrategyRequest(name="New Name", status="active")

        await svc.update_strategy("u1", "s1", req)

        assert mock_supabase["async_supabase"].await_count >= 1

    @pytest.mark.asyncio
    async def test_raises_when_not_found(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = None
        req = UpdateUserStrategyRequest(name="New")

        with pytest.raises(ValueError, match="Strategy not found"):
            await svc.update_strategy("u1", "nonexistent", req)


class TestDeployStrategy:
    @pytest.mark.asyncio
    async def test_rejects_invalid_mode(self, svc, mock_supabase) -> None:
        req = DeployStrategyRequest(mode="INVALID")
        with pytest.raises(ValueError, match="mode must be"):
            await svc.deploy_strategy("u1", "s1", req, make_user(), make_caps())

    @pytest.mark.asyncio
    async def test_deploys_paper(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = make_strategy_row()
        mock_supabase["async_safe_execute"].return_value = None

        req = DeployStrategyRequest(mode="PAPER")

        with patch("application.services.strategy_service.compile_user_strategy") as mock_compile:
            mock_plan = MagicMock()
            mock_plan.orders = []
            mock_plan.legs = []
            mock_compile.return_value = mock_plan

            result = await svc.deploy_strategy("u1", "s1", req, make_user(), make_caps())

        assert result["mode"] == "PAPER"
        assert result["strategy_id"] == "s1"
