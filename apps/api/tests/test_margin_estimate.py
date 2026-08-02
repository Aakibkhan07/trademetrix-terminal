from unittest.mock import AsyncMock

import pytest

from brokers.fyers_adapter import FyersAdapter
from brokers.fyers_http import FyersResponse

import json


def _resp(payload: dict) -> FyersResponse:
    return FyersResponse(status_code=200, body=json.dumps(payload).encode("utf-8"))


@pytest.fixture
def adapter():
    a = FyersAdapter()
    a._access_token = "test_token"
    a._client_id = "test_client"
    a._http.request = AsyncMock(return_value=_resp({"s": "ok"}))
    return a


class TestFyersMarginEstimate:

    @pytest.mark.asyncio
    async def test_margin_estimate_single_leg(self, adapter):
        adapter._http.request = AsyncMock(return_value=_resp({
            "s": "ok",
            "span_margin": 15000.0,
            "exposure_margin": 5000.0,
            "total_margin": 20000.0,
        }))

        result = await adapter.get_margin_estimate([
            {"symbol": "NIFTY05JUL24500CE", "quantity": 65, "side": "SELL", "order_type": "MARKET", "product": "INTRADAY"}
        ])

        assert result["supported"] is True
        assert result["total_margin"] == 20000.0
        assert result["span_margin"] == 15000.0
        assert result["exposure_margin"] == 5000.0
        assert result["broker"] == "fyers"
        assert result["currency"] == "INR"

        adapter._http.request.assert_awaited_once()
        args, kwargs = adapter._http.request.await_args
        assert args[1].endswith("/v3/span_margin")
        assert kwargs["json_body"]["symbol"] == "NSE:NIFTY05JUL24500CE"
        assert kwargs["json_body"]["qty"] == 65
        assert kwargs["json_body"]["side"] == -1
        assert kwargs["json_body"]["type"] == 1
        assert kwargs["json_body"]["productType"] == "INTRADAY"

    @pytest.mark.asyncio
    async def test_margin_estimate_multi_leg(self, adapter):
        adapter._http.request = AsyncMock(return_value=_resp({"s": "ok", "span": 8000.0, "exposure": 2000.0}))

        result = await adapter.get_margin_estimate([
            {"symbol": "NIFTY05JUL24500CE", "quantity": 65, "side": "BUY", "order_type": "MARKET", "product": "INTRADAY"},
            {"symbol": "NIFTY05JUL24600PE", "quantity": 65, "side": "SELL", "order_type": "MARKET", "product": "INTRADAY"},
        ])

        assert result["supported"] is True
        assert result["total_margin"] == 20000.0
        assert result["span_margin"] == 16000.0
        assert result["exposure_margin"] == 4000.0
        assert adapter._http.request.await_count == 2

    @pytest.mark.asyncio
    async def test_margin_estimate_api_error(self, adapter):
        adapter._http.request = AsyncMock(return_value=_resp({"s": "error", "code": -50, "message": "Please provide valid symbols"}))

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
        adapter._http.request = AsyncMock(return_value=_resp({"s": "ok", "span_margin": 12000.0, "exposure_margin": 3000.0, "total_margin": 15000.0}))

        result = await adapter.get_margin_estimate([
            {"symbol": "NIFTY05JUL24500CE", "quantity": 65, "side": "BUY", "order_type": "LIMIT", "product": "INTRADAY", "price": 150.0}
        ])

        assert result["supported"] is True
        assert adapter._http.request.await_args.kwargs["json_body"]["limitPrice"] == 150.0
        assert adapter._http.request.await_args.kwargs["json_body"]["type"] == 2


class TestUnsupportedBroker:

    @pytest.mark.asyncio
    async def test_unsupported_broker_returns_false(self):
        adapter = FyersAdapter()
        adapter._access_token = ""
        result = await adapter.get_margin_estimate([{"symbol": "NIFTY", "quantity": 65}])
        assert result["supported"] is False
        assert result["broker"] == "fyers"
