from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from application.services.strategy_catalog_service import StrategyCatalogService
from core.capabilities import Capabilities


@pytest.fixture
def svc() -> StrategyCatalogService:
    return StrategyCatalogService()


@pytest.fixture
def mock_catalog_strategy() -> MagicMock:
    s = MagicMock()
    s.key = "iron_condor"
    s.name = "Iron Condor"
    s.description = "An iron condor strategy"
    s.model_dump.return_value = {
        "key": "iron_condor",
        "name": "Iron Condor",
        "description": "An iron condor strategy",
    }
    return s


@pytest.fixture
def mock_supabase() -> Generator[dict, None, None]:
    with (
        patch("application.services.strategy_catalog_service.get_supabase") as mock_get,
        patch("application.services.strategy_catalog_service.async_safe_execute") as mock_execute,
        patch("application.services.strategy_catalog_service.record_audit") as mock_audit,
        patch("strategies.get_strategy_catalog") as mock_catalog,
        patch("strategies.get_strategy_category") as mock_category,
        patch("strategies.list_strategies") as mock_list,
    ):
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_get.return_value.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.order.return_value = mock_select
        mock_select.in_.return_value = mock_select
        mock_select.limit.return_value = mock_select
        mock_execute.return_value = None
        yield {
            "get_supabase": mock_get,
            "async_safe_execute": mock_execute,
            "record_audit": mock_audit,
            "get_strategy_catalog": mock_catalog,
            "get_strategy_category": mock_category,
            "list_strategies": mock_list,
            "table": mock_table,
            "select": mock_select,
        }


def make_caps() -> Capabilities:
    return Capabilities(
        tier="enterprise", max_active_strategies=15,
        trailing_sl_allowed=True, reentry_squareoff_allowed=True,
        builder_allowed=True, custom_strategy_dev_allowed=True,
        backtest_allowed=True, backtest_years=5,
        daily_loss_floor=10000.0, live_trading_allowed=True,
    )


class TestListBuiltin:
    @pytest.mark.asyncio
    async def test_returns_catalog(self, svc, mock_supabase, mock_catalog_strategy) -> None:
        mock_supabase["get_strategy_catalog"].return_value = [mock_catalog_strategy]

        result = await svc.list_builtin()

        assert len(result) == 1
        assert result[0]["key"] == "iron_condor"
        assert result[0]["name"] == "Iron Condor"


class TestGetMarketplace:
    @pytest.mark.asyncio
    async def test_returns_enriched_catalog(self, svc, mock_supabase, mock_catalog_strategy) -> None:
        mock_supabase["get_strategy_catalog"].return_value = [mock_catalog_strategy]
        mock_supabase["get_strategy_category"].return_value = "options"
        mock_supabase["list_strategies"].return_value = {"iron_condor"}
        mock_supabase["async_safe_execute"].return_value = []

        result = await svc.get_marketplace()

        assert len(result) == 1
        entry = result[0]
        assert entry["key"] == "iron_condor"
        assert entry["category"] == "options"
        assert entry["user_count"] == 0
        assert entry["total_trades"] == 0
        assert entry["win_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_skips_graph_strategy(self, svc, mock_supabase, mock_catalog_strategy) -> None:
        graph_strat = MagicMock()
        graph_strat.key = "graph_strategy"
        graph_strat.name = "Graph Strategy"
        graph_strat.description = ""
        graph_strat.model_dump.return_value = {
            "key": "graph_strategy",
            "name": "Graph Strategy",
            "description": "",
        }
        mock_supabase["get_strategy_catalog"].return_value = [mock_catalog_strategy, graph_strat]
        mock_supabase["get_strategy_category"].return_value = "options"
        mock_supabase["list_strategies"].return_value = set()
        mock_supabase["async_safe_execute"].return_value = []

        result = await svc.get_marketplace()

        assert len(result) == 1
        assert result[0]["key"] == "iron_condor"


class TestGetStrategyDetail:
    @pytest.mark.asyncio
    async def test_returns_detail(self, svc, mock_supabase, mock_catalog_strategy) -> None:
        mock_supabase["get_strategy_catalog"].return_value = [mock_catalog_strategy]
        mock_supabase["get_strategy_category"].return_value = "options"
        mock_supabase["async_safe_execute"].return_value = []

        result = await svc.get_strategy_detail("iron_condor")

        assert result is not None
        assert result["key"] == "iron_condor"
        assert result["category"] == "options"
        assert result["user_count"] == 0
        assert result["total_trades"] == 0

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, svc, mock_supabase) -> None:
        mock_supabase["get_strategy_catalog"].return_value = []

        result = await svc.get_strategy_detail("nonexistent")

        assert result is None


class TestGetAssignedStrategies:
    @pytest.mark.asyncio
    async def test_returns_assigned_strategies(self, svc, mock_supabase, mock_catalog_strategy) -> None:
        mock_supabase["get_strategy_catalog"].return_value = [mock_catalog_strategy]
        mock_supabase["async_safe_execute"].return_value = [
            {"strategy_key": "iron_condor", "mirror_enabled": True, "required_tier": "free"},
        ]

        result = await svc.get_assigned_strategies("user-1", make_caps())

        assert result["active_count"] == 1
        assert result["max_active_strategies"] == 15
        assert result["strategies"][0]["strategy_key"] == "iron_condor"
        assert result["strategies"][0]["name"] == "Iron Condor"
        assert result["strategies"][0]["mirror_enabled"] is True
        assert result["strategies"][0]["required_tier"] == "free"


class TestListUserStrategies:
    @pytest.mark.asyncio
    async def test_returns_list(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_execute"].return_value = [
            {"id": "s1", "name": "My Strat", "user_id": "user-1", "type": "builtin", "config": {}}
        ]

        result = await svc.list_user_strategies("user-1")

        assert len(result) == 1
        assert result[0]["id"] == "s1"
        assert result[0]["name"] == "My Strat"

    @pytest.mark.asyncio
    async def test_returns_empty_when_none(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_execute"].return_value = None

        result = await svc.list_user_strategies("user-1")

        assert result == []


class TestCreateStrategy:
    @pytest.mark.asyncio
    async def test_creates_and_returns_result(self, svc, mock_supabase) -> None:
        mock_supabase["list_strategies"].return_value = ["iron_condor"]
        mock_supabase["async_safe_execute"].return_value = [
            {"id": "new-s1", "name": "My Strat", "user_id": "user-1", "type": "builtin", "config": {}}
        ]

        req = {"name": "My Strat", "type": "builtin", "config": {"type": "iron_condor"}}
        result = await svc.create_strategy("user-1", req)

        assert result["id"] == "new-s1"
        assert result["name"] == "My Strat"
        mock_supabase["record_audit"].assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_unknown_builtin_type(self, svc, mock_supabase) -> None:
        mock_supabase["list_strategies"].return_value = ["iron_condor"]

        req = {"name": "Bad", "type": "builtin", "config": {"type": "nonexistent"}}
        with pytest.raises(ValueError, match="Unknown builtin strategy type"):
            await svc.create_strategy("user-1", req)


class TestUpdateStrategy:
    @pytest.mark.asyncio
    async def test_updates_successfully(self, svc, mock_supabase) -> None:
        updates = {"name": "New Name", "config": {"key": "val"}}

        await svc.update_strategy("s1", "user-1", updates)

        mock_supabase["async_safe_execute"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_on_empty_updates(self, svc, mock_supabase) -> None:
        with pytest.raises(ValueError, match="No updates provided"):
            await svc.update_strategy("s1", "user-1", {})


class TestDeleteStrategy:
    @pytest.mark.asyncio
    async def test_deletes_successfully(self, svc, mock_supabase) -> None:
        await svc.delete_strategy("s1", "user-1")

        mock_supabase["async_safe_execute"].assert_awaited_once()
