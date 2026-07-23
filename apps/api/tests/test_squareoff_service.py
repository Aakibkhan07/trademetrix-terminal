from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.squareoff_service import SquareoffService


@pytest.fixture
def svc() -> SquareoffService:
    return SquareoffService()


@pytest.fixture
def mock_async_safe_single() -> Generator[AsyncMock, None, None]:
    with patch("application.services.squareoff_service.async_safe_single", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def mock_async_safe_execute() -> Generator[AsyncMock, None, None]:
    with patch("application.services.squareoff_service.async_safe_execute", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def mock_supabase() -> Generator[MagicMock, None, None]:
    with patch("application.services.squareoff_service.get_supabase") as m:
        yield m


class TestGetConfig:
    @pytest.mark.asyncio
    async def test_returns_config(self, svc, mock_supabase, mock_async_safe_single) -> None:
        mock_async_safe_single.return_value = {
            "enabled": True,
            "squareoff_time": "15:00",
            "days": [0, 1, 2, 3, 4],
        }
        result = await svc.get_config("u1")
        assert result == {"enabled": True, "time": "15:00", "days": [0, 1, 2, 3, 4]}

    @pytest.mark.asyncio
    async def test_returns_defaults_when_not_found(self, svc, mock_supabase, mock_async_safe_single) -> None:
        mock_async_safe_single.return_value = None
        result = await svc.get_config("u1")
        assert result == {"enabled": False, "time": "15:15", "days": [0, 1, 2, 3, 4]}


class TestSetConfig:
    @pytest.mark.asyncio
    async def test_inserts_new_config(self, svc, mock_supabase, mock_async_safe_single, mock_async_safe_execute) -> None:
        mock_async_safe_single.return_value = None
        result = await svc.set_config("u1", True, "15:00", [0, 1, 2, 3, 4])
        assert result == {"message": "Squareoff config updated"}
        mock_async_safe_execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_updates_existing_config(self, svc, mock_supabase, mock_async_safe_single, mock_async_safe_execute) -> None:
        mock_async_safe_single.return_value = {"id": 1}
        result = await svc.set_config("u1", False, "14:00", [0, 1])
        assert result == {"message": "Squareoff config updated"}
        mock_async_safe_execute.assert_awaited_once()


class TestRunSquareoff:
    @pytest.mark.asyncio
    async def test_no_active_broker_returns_early(self, svc, mock_supabase, mock_async_safe_single, mock_async_safe_execute) -> None:
        mock_async_safe_single.return_value = None
        result = await svc.run_squareoff("u1")
        assert result == {"message": "No active broker", "squareoff_count": 0}

    @pytest.mark.asyncio
    async def test_no_intraday_positions_returns_early(self, svc, mock_supabase, mock_async_safe_single) -> None:
        mock_async_safe_single.return_value = {"broker": "fyers"}

        with patch("application.services.squareoff_service.ExecutionEngine") as mock_engine_cls:
            mock_engine = MagicMock()
            mock_engine.start = AsyncMock()
            mock_engine.get_positions = AsyncMock(return_value=[])
            mock_engine.stop = AsyncMock()
            mock_engine_cls.return_value = mock_engine

            result = await svc.run_squareoff("u1")

        assert result == {"message": "No intraday positions to square off", "squareoff_count": 0}
        mock_engine.start.assert_awaited_once()
        mock_engine.get_positions.assert_awaited_once()
        mock_engine.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_runs_with_intraday_positions(self, svc, mock_supabase, mock_async_safe_single) -> None:
        mock_async_safe_single.return_value = {"broker": "fyers"}

        pos = MagicMock()
        pos.product = "INTRADAY"
        pos.quantity = 10
        pos.symbol = "NIFTY"
        pos.exchange = "NSE"
        pos.instrument_type = "FUT"
        pos.strike_price = 0
        pos.expiry_date = None
        pos.option_type = None

        with (
            patch("application.services.squareoff_service.ExecutionEngine") as mock_engine_cls,
            patch("application.services.squareoff_service.execute_order", new_callable=AsyncMock) as mock_exec,
        ):
            mock_engine = MagicMock()
            mock_engine.start = AsyncMock()
            mock_engine.get_positions = AsyncMock(return_value=[pos])
            mock_engine.stop = AsyncMock()
            mock_engine_cls.return_value = mock_engine
            mock_exec.return_value = MagicMock(model_dump=lambda: {"status": "filled"})

            result = await svc.run_squareoff("u1")

        assert result["squareoff_count"] == 1
        assert "Squareoff executed" in result["message"]
        mock_engine.start.assert_awaited_once()
        mock_engine.get_positions.assert_awaited_once()
        mock_engine.stop.assert_awaited_once()
        mock_exec.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sells_short_positions(self, svc, mock_supabase, mock_async_safe_single) -> None:
        mock_async_safe_single.return_value = {"broker": "fyers"}

        pos = MagicMock()
        pos.product = "MIS"
        pos.quantity = -5
        pos.symbol = "BANKNIFTY"
        pos.exchange = "NSE"
        pos.instrument_type = "FUT"
        pos.strike_price = 0
        pos.expiry_date = None
        pos.option_type = None

        with (
            patch("application.services.squareoff_service.ExecutionEngine") as mock_engine_cls,
            patch("application.services.squareoff_service.execute_order", new_callable=AsyncMock) as mock_exec,
        ):
            mock_engine = MagicMock()
            mock_engine.start = AsyncMock()
            mock_engine.get_positions = AsyncMock(return_value=[pos])
            mock_engine.stop = AsyncMock()
            mock_engine_cls.return_value = mock_engine
            mock_exec.return_value = MagicMock(model_dump=lambda: {"status": "filled"})

            result = await svc.run_squareoff("u1")

        assert result["squareoff_count"] == 1
        mock_exec.assert_awaited_once()


class TestRunSquareoffForUser:
    @pytest.mark.asyncio
    async def test_no_active_broker_returns_early(self, svc, mock_supabase, mock_async_safe_single) -> None:
        mock_async_safe_single.return_value = None
        user = MagicMock()
        user.id = "u1"
        result = await svc.run_squareoff_for_user(user)
        assert result is None

    @pytest.mark.asyncio
    async def test_squares_off_positions(self, svc, mock_supabase, mock_async_safe_single) -> None:
        mock_async_safe_single.return_value = {"broker": "fyers"}
        user = MagicMock()
        user.id = "u1"

        pos = MagicMock()
        pos.product = "INTRADAY"
        pos.quantity = 10
        pos.symbol = "NIFTY"
        pos.exchange = "NSE"
        pos.instrument_type = "FUT"
        pos.strike_price = 0
        pos.expiry_date = None
        pos.option_type = None

        with (
            patch("application.services.squareoff_service.ExecutionEngine") as mock_engine_cls,
            patch("application.services.squareoff_service.execute_order", new_callable=AsyncMock) as mock_exec,
        ):
            mock_engine = MagicMock()
            mock_engine.start = AsyncMock()
            mock_engine.get_positions = AsyncMock(return_value=[pos])
            mock_engine.stop = AsyncMock()
            mock_engine_cls.return_value = mock_engine

            await svc.run_squareoff_for_user(user)

        mock_engine.start.assert_awaited_once()
        mock_engine.get_positions.assert_awaited_once()
        mock_engine.stop.assert_awaited_once()
        mock_exec.assert_awaited_once()


class TestScheduler:
    @pytest.mark.asyncio
    async def test_start_scheduler_creates_task(self, svc) -> None:
        assert svc._task is None
        with patch("asyncio.create_task") as mock_create:
            svc.start_scheduler()
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_scheduler_idempotent(self, svc) -> None:
        with patch("asyncio.create_task") as mock_create:
            svc.start_scheduler()
            svc.start_scheduler()
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_scheduler_cancels_task(self, svc) -> None:
        mock_task = MagicMock()
        svc._task = mock_task
        svc.stop_scheduler()
        mock_task.cancel.assert_called_once()
        assert svc._task is None

    @pytest.mark.asyncio
    async def test_stop_scheduler_no_task(self, svc) -> None:
        assert svc._task is None
        svc.stop_scheduler()
        assert svc._task is None
