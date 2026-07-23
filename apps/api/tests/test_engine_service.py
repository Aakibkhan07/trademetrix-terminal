from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.engine_service import EngineService


@pytest.fixture
def svc() -> EngineService:
    return EngineService()


@pytest.fixture
def mock_supabase() -> Generator[dict, None, None]:
    with (
        patch("application.services.engine_service.async_supabase") as mock_async,
        patch("application.services.engine_service.get_supabase") as mock_get,
        patch("application.services.engine_service.async_safe_single") as mock_single,
        patch("application.services.engine_service.async_safe_execute") as mock_execute,
    ):
        mock_table = MagicMock()
        mock_get.return_value.table.return_value = mock_table
        mock_async.return_value = MagicMock()
        yield {
            "async_supabase": mock_async,
            "get_supabase": mock_get,
            "async_safe_single": mock_single,
            "async_safe_execute": mock_execute,
            "table": mock_table,
        }


class TestCreateRun:
    @pytest.mark.asyncio
    async def test_creates_run_and_returns_id(self, svc, mock_supabase) -> None:
        mock_supabase["async_supabase"].return_value.data = [{"id": "run-1"}]

        result = await svc.create_run("u1", "strat-1", "fyers", "PAPER")

        assert result["run_id"] == "run-1"
        assert result["status"] == "running"
        mock_supabase["async_supabase"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_run_with_symbols(self, svc, mock_supabase) -> None:
        mock_supabase["async_supabase"].return_value.data = [{"id": "run-2"}]

        result = await svc.create_run("u1", "strat-1", "fyers", "LIVE", symbols=["NIFTY", "BANKNIFTY"])

        assert result["run_id"] == "run-2"
        assert result["status"] == "running"


class TestStopRun:
    @pytest.mark.asyncio
    async def test_stops_run_and_updates_status(self, svc, mock_supabase) -> None:
        result = await svc.stop_run("u1", "run-1")

        assert result["message"] == "Engine stopped"
        mock_supabase["async_supabase"].assert_awaited_once()


class TestExecuteTrade:
    @patch("application.services.engine_service.execute_order", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_executes_trade(self, mock_exec, svc) -> None:
        mock_exec.return_value = MagicMock(model_dump=lambda: {"order_id": "ord-1"})
        req = {
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 50,
            "price": 18500.0,
            "strategy_id": "strat-1",
            "option_type": "CE",
            "strike_price": 18500,
            "expiry_date": "2026-07-30",
            "instrument_type": "OPT",
        }

        result = await svc.execute_trade("u1", req)

        assert result["result"]["order_id"] == "ord-1"
        mock_exec.assert_awaited_once()


class TestGetOrders:
    @pytest.mark.asyncio
    async def test_returns_orders(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_execute"].return_value = [{"id": "ord-1"}, {"id": "ord-2"}]

        result = await svc.get_orders("u1")

        assert len(result) == 2
        assert result[0]["id"] == "ord-1"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_orders(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_execute"].return_value = None

        result = await svc.get_orders("u1")

        assert result == []


class TestCancelOrder:
    @patch("execution.execution_manager")
    @pytest.mark.asyncio
    async def test_cancels_order(self, mock_em, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = {"broker": "fyers"}
        mock_em.cancel_order = AsyncMock(return_value=MagicMock(model_dump=lambda: {"status": "cancelled"}))

        result = await svc.cancel_order("u1", "ord-1")

        assert result["result"]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_raises_when_no_active_broker(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = None

        with pytest.raises(ValueError, match="No active broker configured"):
            await svc.cancel_order("u1", "ord-1")


class TestGetActiveBroker:
    @pytest.mark.asyncio
    async def test_returns_broker_name(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = {"broker": "fyers"}

        broker = await svc.get_active_broker("u1")

        assert broker == "fyers"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_active(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = None

        broker = await svc.get_active_broker("u1")

        assert broker is None


class TestGetRuns:
    @pytest.mark.asyncio
    async def test_returns_runs(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_execute"].return_value = [{"id": "run-1"}]

        result = await svc.get_runs("u1")

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_when_none(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_execute"].return_value = None

        result = await svc.get_runs("u1")

        assert result == []


class TestGetPositions:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_broker(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = None

        result = await svc.get_positions("u1")

        assert result == []


class TestGetFunds:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_broker(self, svc, mock_supabase) -> None:
        mock_supabase["async_safe_single"].return_value = None

        result = await svc.get_funds("u1")

        assert result == {"total_margin": 0, "used_margin": 0, "available_margin": 0}
