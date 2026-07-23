from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.buyer_strategy_service import BuyerStrategyService


@pytest.fixture
def svc() -> BuyerStrategyService:
    return BuyerStrategyService()


@pytest.fixture
def patches() -> Generator[dict, None, None]:
    with (
        patch("application.services.buyer_strategy_service.BUYER_KEYS", {"valid_key": "SomeStrategy"}),
        patch("application.services.buyer_strategy_service.buyer_strategy_runner") as mock_runner,
        patch("application.services.buyer_strategy_service.get_strategy") as mock_get_strat,
    ):
        mock_runner.activate = AsyncMock()
        mock_runner.deactivate = AsyncMock()
        mock_runner.get_statuses = AsyncMock()
        yield {"runner": mock_runner, "get_strategy": mock_get_strat}


class TestActivate:
    @pytest.mark.asyncio
    async def test_activates_successfully(self, svc, patches) -> None:
        patches["runner"].activate.return_value = True
        result = await svc.activate("u1", "strat-1", "valid_key", "NIFTY", {"p": "v"})
        assert result == {"message": "Strategy activated", "strategy_id": "strat-1"}
        patches["get_strategy"].assert_called_once_with("valid_key")
        patches["runner"].activate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_on_unknown_key(self, svc, patches) -> None:
        with pytest.raises(ValueError, match="Unknown buyer strategy"):
            await svc.activate("u1", "strat-1", "unknown_key", "NIFTY", {})

    @pytest.mark.asyncio
    async def test_raises_on_bad_index(self, svc, patches) -> None:
        with pytest.raises(ValueError, match="index must be NIFTY or SENSEX"):
            await svc.activate("u1", "strat-1", "valid_key", "BANKNIFTY", {})

    @pytest.mark.asyncio
    async def test_raises_on_strategy_class_not_found(self, svc, patches) -> None:
        patches["get_strategy"].side_effect = ValueError("not found")
        with pytest.raises(ValueError, match="Strategy class not found"):
            await svc.activate("u1", "strat-1", "valid_key", "NIFTY", {})

    @pytest.mark.asyncio
    async def test_raises_on_runner_failure(self, svc, patches) -> None:
        patches["runner"].activate.return_value = False
        with pytest.raises(RuntimeError, match="Failed to activate strategy"):
            await svc.activate("u1", "strat-1", "valid_key", "NIFTY", {})


class TestDeactivate:
    @pytest.mark.asyncio
    async def test_deactivates_successfully(self, svc, patches) -> None:
        patches["runner"].deactivate.return_value = True
        result = await svc.deactivate("strat-1")
        assert result == {"message": "Strategy deactivated"}
        patches["runner"].deactivate.assert_awaited_once_with("strat-1")

    @pytest.mark.asyncio
    async def test_raises_when_not_found(self, svc, patches) -> None:
        patches["runner"].deactivate.return_value = False
        with pytest.raises(ValueError, match="Strategy not found or already inactive"):
            await svc.deactivate("strat-1")


class TestStatus:
    @pytest.mark.asyncio
    async def test_returns_statuses(self, svc, patches) -> None:
        expected = [{"id": "strat-1", "active": True}]
        patches["runner"].get_statuses.return_value = expected
        result = await svc.status()
        assert result == {"strategies": expected}
        patches["runner"].get_statuses.assert_awaited_once()


class TestBacktest:
    @pytest.mark.asyncio
    async def test_runs_backtest_with_historical_data(self, svc) -> None:
        candles = [{"symbol": "NIFTY", "close": 19500.0}]
        mock_results = {"total_trades": 5, "final_capital": 100000.0}

        with (
            patch("application.services.buyer_strategy_service.BUYER_KEYS", {"valid_key": "SomeStrategy"}),
            patch("application.services.buyer_strategy_service.get_strategy"),
            patch("application.services.buyer_strategy_service.fetch_historical_data", new_callable=AsyncMock) as mock_fetch,
            patch("application.services.buyer_strategy_service.BuyerBacktestEngine") as mock_engine_cls,
        ):
            mock_fetch.return_value = candles
            mock_engine = MagicMock()
            mock_engine.run = AsyncMock(return_value=mock_results)
            mock_engine_cls.return_value = mock_engine

            result = await svc.backtest(
                "u1", "valid_key", "NIFTY", "NSE", "5min", 5, 100000.0, {}
            )

        assert result["symbol"] == "NIFTY"
        assert result["strategy"] == "valid_key"
        assert result["total_trades"] == 5
        mock_fetch.assert_awaited_once()
        mock_engine.run.assert_awaited_once_with(candles)

    @pytest.mark.asyncio
    async def test_falls_back_to_simulated_data_on_fetch_failure(self, svc) -> None:
        mock_results = {"total_trades": 3, "final_capital": 95000.0}

        with (
            patch("application.services.buyer_strategy_service.BUYER_KEYS", {"valid_key": "SomeStrategy"}),
            patch("application.services.buyer_strategy_service.get_strategy"),
            patch("application.services.buyer_strategy_service.fetch_historical_data", new_callable=AsyncMock) as mock_fetch,
            patch("application.services.buyer_strategy_service.BuyerBacktestEngine") as mock_engine_cls,
        ):
            mock_fetch.side_effect = Exception("API error")
            mock_engine = MagicMock()
            mock_engine.run = AsyncMock(return_value=mock_results)
            mock_engine_cls.return_value = mock_engine

            result = await svc.backtest(
                "u1", "valid_key", "NIFTY", "NSE", "5min", 5, 100000.0, {}
            )

        assert result["symbol"] == "NIFTY"
        assert result["strategy"] == "valid_key"
        assert result["total_trades"] == 3
        mock_engine.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_on_unknown_key(self, svc) -> None:
        with (
            patch("application.services.buyer_strategy_service.BUYER_KEYS", {"valid_key": "SomeStrategy"}),
        ):
            with pytest.raises(ValueError, match="Unknown buyer strategy"):
                await svc.backtest(
                    "u1", "invalid", "NIFTY", "NSE", "5min", 5, 100000.0, {}
                )
