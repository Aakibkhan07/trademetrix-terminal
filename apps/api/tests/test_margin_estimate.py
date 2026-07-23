from unittest.mock import AsyncMock, MagicMock

import pytest

from brokers.fyers_adapter import FyersAdapter


@pytest.fixture
def adapter():
    a = FyersAdapter()
    a._access_token = "test_token"
    a._client_id = "test_client"
    return a


class TestFyersMarginEstimate:

    @pytest.mark.asyncio
    async def test_margin_estimate_single_leg(self, adapter):
        client = AsyncMock()
        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "s": "ok",
            "span_margin": 15000.0,
            "exposure_margin": 5000.0,
            "total_margin": 20000.0,
        }
        client.post = AsyncMock(return_value=resp)
        adapter._get_client = AsyncMock(return_value=client)

        result = await adapter.get_margin_estimate([
            {"symbol": "NIFTY05JUL24500CE", "quantity": 65, "side": "SELL", "order_type": "MARKET", "product": "INTRADAY"}
        ])

        assert result["supported"] is True
        assert result["total_margin"] == 20000.0
        assert result["span_margin"] == 15000.0
        assert result["exposure_margin"] == 5000.0
        assert result["broker"] == "fyers"
        assert result["currency"] == "INR"

        client.post.assert_called_once()
        call_args = client.post.call_args
        assert call_args[0][0].endswith("/v3/span_margin")
        assert call_args[1]["json"]["symbol"] == "NSE:NIFTY05JUL24500CE"
        assert call_args[1]["json"]["qty"] == 65
        assert call_args[1]["json"]["side"] == -1
        assert call_args[1]["json"]["type"] == 1
        assert call_args[1]["json"]["productType"] == "INTRADAY"

    @pytest.mark.asyncio
    async def test_margin_estimate_multi_leg(self, adapter):
        client = AsyncMock()
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"s": "ok", "span": 8000.0, "exposure": 2000.0}
        client.post = AsyncMock(return_value=resp)
        adapter._get_client = AsyncMock(return_value=client)

        result = await adapter.get_margin_estimate([
            {"symbol": "NIFTY05JUL24500CE", "quantity": 65, "side": "BUY", "order_type": "MARKET", "product": "INTRADAY"},
            {"symbol": "NIFTY05JUL24600PE", "quantity": 65, "side": "SELL", "order_type": "MARKET", "product": "INTRADAY"},
        ])

        assert result["supported"] is True
        assert result["total_margin"] == 20000.0
        assert result["span_margin"] == 16000.0
        assert result["exposure_margin"] == 4000.0
        assert client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_margin_estimate_api_error(self, adapter):
        client = AsyncMock()
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"s": "error", "code": -50, "message": "Please provide valid symbols"}
        client.post = AsyncMock(return_value=resp)
        adapter._get_client = AsyncMock(return_value=client)

        result = await adapter.get_margin_estimate([
            {"symbol": "BAD_SYMBOL", "quantity": 65, "side": "BUY", "order_type": "MARKET", "product": "INTRADAY"}
        ])

        assert result["supported"] is False
        assert result["broker"] == "fyers"
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_margin_estimate_not_authenticated(self):
        a = FyersAdapter()
        result = await a.get_margin_estimate([{"symbol": "NIFTY", "quantity": 65, "side": "BUY", "order_type": "MARKET", "product": "INTRADAY"}])
        assert result["supported"] is False
        assert result["broker"] == "fyers"

    @pytest.mark.asyncio
    async def test_margin_estimate_with_limit_price(self, adapter):
        client = AsyncMock()
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"s": "ok", "span_margin": 12000.0, "exposure_margin": 3000.0, "total_margin": 15000.0}
        client.post = AsyncMock(return_value=resp)
        adapter._get_client = AsyncMock(return_value=client)

        result = await adapter.get_margin_estimate([
            {"symbol": "NIFTY05JUL24500CE", "quantity": 65, "side": "BUY", "order_type": "LIMIT", "product": "INTRADAY", "price": 150.0}
        ])

        assert result["supported"] is True
        assert client.post.call_args[1]["json"]["limitPrice"] == 150.0
        assert client.post.call_args[1]["json"]["type"] == 2


class TestUnsupportedBroker:

    @pytest.mark.asyncio
    async def test_unsupported_broker_returns_false(self):
        adapter = FyersAdapter()
        adapter._access_token = ""
        result = await adapter.get_margin_estimate([{"symbol": "NIFTY", "quantity": 65}])
        assert result["supported"] is False
        assert result["broker"] == "fyers"
