from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from application.services.multileg_service import MultiLegService
from core.models import OrderResult


@pytest.fixture
def svc() -> MultiLegService:
    return MultiLegService()


@pytest.fixture
def mock_supabase() -> Generator[dict, None, None]:
    with (
        patch("application.services.multileg_service.get_supabase") as mock_get,
        patch("application.services.multileg_service.async_safe_execute") as mock_execute,
        patch("application.services.multileg_service.async_safe_single") as mock_single,
        patch("application.services.multileg_service.execute_order") as mock_exec_order,
    ):
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_get.return_value.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.order.return_value = mock_select
        mock_select.in_.return_value = mock_select
        mock_execute.return_value = None
        mock_single.return_value = None
        yield {
            "get_supabase": mock_get,
            "async_safe_execute": mock_execute,
            "async_safe_single": mock_single,
            "execute_order": mock_exec_order,
            "table": mock_table,
            "select": mock_select,
        }


def make_mock_req(leg_count=2) -> MagicMock:
    req = MagicMock()
    req.name = "Iron Condor"
    req.description = "Test strategy"
    req.underlying = "NIFTY"
    req.expiry = "2026-07-30"
    legs = []
    for i in range(leg_count):
        leg = MagicMock()
        leg.action.value = "BUY" if i % 2 == 0 else "SELL"
        leg.symbol = "NIFTY"
        leg.quantity = 25
        leg.exchange = "NFO"
        leg.order_type = "LIMIT"
        leg.product = "INTRADAY"
        leg.price = 100.0
        leg.trigger_price = None
        leg.instrument_type = "OPT"
        leg.strike_price = 19500.0
        leg.expiry_date = "2026-07-30"
        leg.option_type = "CE"
        legs.append(leg)
    req.legs = legs
    return req


def make_strategy_row(overrides=None) -> dict:
    row = {
        "id": "strat-1",
        "user_id": "user-1",
        "name": "Iron Condor",
        "description": "Test",
        "underlying": "NIFTY",
        "expiry": "2026-07-30",
        "leg_count": 2,
        "status": "draft",
    }
    if overrides:
        row.update(overrides)
    return row


def make_leg_row(index=0, overrides=None) -> dict:
    row = {
        "id": f"leg-{index}",
        "strategy_id": "strat-1",
        "leg_index": index,
        "action": "BUY" if index % 2 == 0 else "SELL",
        "symbol": "NIFTY",
        "quantity": 25,
        "exchange": "NFO",
        "order_type": "LIMIT",
        "product": "INTRADAY",
        "price": 100.0,
        "trigger_price": None,
        "instrument_type": "OPT",
        "strike_price": 19500.0,
        "expiry_date": "2026-07-30",
        "option_type": "CE",
    }
    if overrides:
        row.update(overrides)
    return row


class TestListStrategies:
    @pytest.mark.asyncio
    async def test_returns_list(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_execute"].return_value = [make_strategy_row()]

        result = await svc.list_strategies("user-1")

        assert len(result) == 1
        assert result[0]["name"] == "Iron Condor"

    @pytest.mark.asyncio
    async def test_returns_empty_when_none(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_execute"].return_value = None

        result = await svc.list_strategies("user-1")

        assert result == []


class TestGetStrategy:
    @pytest.mark.asyncio
    async def test_returns_strategy_with_legs(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = make_strategy_row()
        mock_supabase["async_safe_execute"].return_value = [make_leg_row(0)]

        result = await svc.get_strategy("strat-1", "user-1")

        assert result["name"] == "Iron Condor"
        assert len(result["legs"]) == 1
        assert result["legs"][0]["id"] == "leg-0"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = None

        result = await svc.get_strategy("nonexistent", "user-1")

        assert result is None


class TestCreateStrategy:
    @pytest.mark.asyncio
    async def test_creates_strategy_and_legs(self, svc, mock_supabase) -> None:
        req = make_mock_req(leg_count=2)

        result = await svc.create_strategy("user-1", req)

        assert result["strategy_id"] is not None
        assert result["name"] == "Iron Condor"
        assert result["leg_count"] == 2
        assert mock_supabase["async_safe_execute"].await_count >= 3


class TestDeleteStrategy:
    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = {"id": "strat-1"}

        result = await svc.delete_strategy("strat-1", "user-1")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = None

        result = await svc.delete_strategy("nonexistent", "user-1")

        assert result is False


class TestPlaceStrategy:
    @pytest.mark.asyncio
    async def test_places_all_legs(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = make_strategy_row()
        mock_supabase["async_safe_execute"].return_value = [make_leg_row(0), make_leg_row(1)]

        def make_result(broker_id) -> MagicMock:
            r = MagicMock(spec=OrderResult)
            r.broker_order_id = broker_id
            r.model_dump.return_value = {"broker_order_id": broker_id, "success": True}
            return r

        mock_supabase["execute_order"].side_effect = [
            make_result("ord-1"),
            make_result("ord-2"),
        ]

        result = await svc.place_strategy("strat-1", "user-1")

        assert result["message"] == "Placed 2 legs"
        assert result["strategy_id"] == "strat-1"
        assert result["order_ids"] == ["ord-1", "ord-2"]
        assert len(result["results"]) == 2
        assert mock_supabase["execute_order"].await_count == 2

    @pytest.mark.asyncio
    async def test_raises_when_strategy_not_found(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = None

        with pytest.raises(ValueError, match="Strategy not found"):
            await svc.place_strategy("nonexistent", "user-1")

    @pytest.mark.asyncio
    async def test_raises_when_no_legs(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = make_strategy_row()
        mock_supabase["async_safe_execute"].return_value = None

        with pytest.raises(ValueError, match="No legs defined"):
            await svc.place_strategy("strat-1", "user-1")
