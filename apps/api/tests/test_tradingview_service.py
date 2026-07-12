import json
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.tradingview_service import TradingViewService


@pytest.fixture
def svc() -> TradingViewService:
    return TradingViewService()


@pytest.fixture
def mock_deps() -> Generator[dict, None, None]:
    with (
        patch("application.services.tradingview_service.execute_order") as mock_exec,
        patch("application.services.tradingview_service.get_mirror_recipients") as mock_recip,
        patch("application.services.tradingview_service.scaled_qty", new_callable=AsyncMock) as mock_scaled,
    ):
        mock_exec.return_value = MagicMock(
            success=True, broker_order_id="ord-1",
            message="Order placed", status="open",
        )
        mock_scaled.return_value = 100
        yield {
            "execute_order": mock_exec,
            "get_mirror_recipients": mock_recip,
            "scaled_qty": mock_scaled,
        }


class TestVerifySignature:
    def test_passes_without_secret(self, svc) -> None:
        with patch("application.services.tradingview_service.WEBHOOK_SECRET", ""):
            result = svc.verify_signature(b"{}", "anything")
            assert result is True

    def test_verifies_correctly_with_secret(self, svc) -> None:
        import hashlib
        import hmac

        secret = "mysecret"
        body = b'{"key": "value"}'
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        with patch("application.services.tradingview_service.WEBHOOK_SECRET", secret):
            result = svc.verify_signature(body, expected)
            assert result is True

    def test_rejects_wrong_signature(self, svc) -> None:
        with patch("application.services.tradingview_service.WEBHOOK_SECRET", "mysecret"):
            result = svc.verify_signature(b"{}", "wrongsig")
            assert result is False


class TestExecuteForUser:
    @pytest.mark.asyncio
    async def test_executes_buy(self, svc, mock_deps) -> None:
        result = await svc.execute_for_user(
            "u1", "RELIANCE", "BUY", 100, 2500.0, "NSE", "MARKET", "INTRADAY",
            "strat-1", "test", "manual",
        )

        assert result["success"] is True
        assert result["broker_order_id"] == "ord-1"
        mock_deps["scaled_qty"].assert_awaited_once()
        mock_deps["execute_order"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_executes_sell(self, svc, mock_deps) -> None:
        result = await svc.execute_for_user(
            "u1", "RELIANCE", "SELL", 100, 2500.0, "NSE", "MARKET", "INTRADAY",
            None, "", "manual",
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_executes_long_as_buy(self, svc, mock_deps) -> None:
        result = await svc.execute_for_user(
            "u1", "RELIANCE", "LONG", 100, 2500.0, "NSE", "MARKET", "INTRADAY",
            None, "", "manual",
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_catches_exceptions(self, svc, mock_deps) -> None:
        mock_deps["execute_order"].side_effect = Exception("Broker timeout")

        result = await svc.execute_for_user(
            "u1", "RELIANCE", "BUY", 100, 2500.0, "NSE", "MARKET", "INTRADAY",
            None, "", "manual",
        )

        assert result["success"] is False
        assert "Broker timeout" in result["message"]
        assert result["status"] == "error"


class TestHandleWebhook:
    @pytest.mark.asyncio
    async def test_full_flow_with_user_id(self, svc, mock_deps) -> None:
        body = json.dumps({
            "symbol": "reliance", "action": "buy", "quantity": 100, "price": 2500,
            "exchange": "NSE", "order_type": "MARKET", "product": "INTRADAY",
            "user_id": "u1", "strategy_id": "", "reason": "webhook",
        }).encode()

        with patch("application.services.tradingview_service.WEBHOOK_SECRET", ""):
            with patch.object(svc, "verify_signature", return_value=True):
                result = await svc.handle_webhook(body, "sig")

        assert result["success"] is True
        assert result["user_id"] == "u1"

    @pytest.mark.asyncio
    async def test_mirror_flow_without_user_id(self, svc, mock_deps) -> None:
        recipients = [{"user_id": "u1"}, {"user_id": "u2"}]
        mock_deps["get_mirror_recipients"].return_value = recipients

        body = json.dumps({
            "symbol": "reliance", "action": "buy", "quantity": 50, "price": 2500,
            "exchange": "NSE", "order_type": "MARKET", "product": "INTRADAY",
            "user_id": "", "strategy_id": "strat-1", "reason": "mirror",
        }).encode()

        with patch("application.services.tradingview_service.WEBHOOK_SECRET", ""):
            with patch.object(svc, "verify_signature", return_value=True):
                result = await svc.handle_webhook(body, "sig")

        assert result["count"] == 2
        assert len(result["results"]) == 2
        assert mock_deps["execute_order"].await_count == 2

    @pytest.mark.asyncio
    async def test_mirror_flow_no_recipients(self, svc, mock_deps) -> None:
        mock_deps["get_mirror_recipients"].return_value = []

        body = json.dumps({
            "symbol": "reliance", "action": "buy", "quantity": 50, "price": 2500,
            "exchange": "NSE", "order_type": "MARKET", "product": "INTRADAY",
            "user_id": "", "strategy_id": "strat-1", "reason": "mirror",
        }).encode()

        with patch("application.services.tradingview_service.WEBHOOK_SECRET", ""):
            with patch.object(svc, "verify_signature", return_value=True):
                result = await svc.handle_webhook(body, "sig")

        assert result["message"] == "No recipients found for this strategy"
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_raises_on_bad_signature(self, svc, mock_deps) -> None:
        with patch.object(svc, "verify_signature", return_value=False):
            with pytest.raises(ValueError, match="Invalid signature"):
                await svc.handle_webhook(b"{}", "badsig")

    @pytest.mark.asyncio
    async def test_raises_on_bad_json(self, svc, mock_deps) -> None:
        with patch.object(svc, "verify_signature", return_value=True):
            with pytest.raises(ValueError, match="Invalid JSON body"):
                await svc.handle_webhook(b"not json", "sig")

    @pytest.mark.asyncio
    async def test_raises_on_missing_fields(self, svc, mock_deps) -> None:
        body = json.dumps({"symbol": "", "action": "", "quantity": 0}).encode()

        with patch("application.services.tradingview_service.WEBHOOK_SECRET", ""):
            with patch.object(svc, "verify_signature", return_value=True):
                with pytest.raises(ValueError, match="symbol, action, and quantity are required"):
                    await svc.handle_webhook(body, "sig")

    @pytest.mark.asyncio
    async def test_raises_when_no_user_id_and_no_strategy(self, svc, mock_deps) -> None:
        body = json.dumps({
            "symbol": "reliance", "action": "buy", "quantity": 10, "price": 2500,
            "exchange": "NSE", "order_type": "MARKET", "product": "INTRADAY",
            "user_id": "", "strategy_id": "", "reason": "",
        }).encode()

        with patch("application.services.tradingview_service.WEBHOOK_SECRET", ""):
            with patch.object(svc, "verify_signature", return_value=True):
                with pytest.raises(ValueError, match="user_id is required"):
                    await svc.handle_webhook(body, "sig")

    @pytest.mark.asyncio
    async def test_normalizes_symbol_to_upper(self, svc, mock_deps) -> None:
        body = json.dumps({
            "symbol": "reliance", "action": "buy", "quantity": 100, "price": 2500,
            "exchange": "nse", "order_type": "market", "product": "intraday",
            "user_id": "u1", "strategy_id": "", "reason": "",
        }).encode()

        with patch("application.services.tradingview_service.WEBHOOK_SECRET", ""):
            with patch.object(svc, "verify_signature", return_value=True):
                result = await svc.handle_webhook(body, "sig")

        assert result["success"] is True
