import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from brokers.angelone_adapter import AngelOneAdapter
from core.models import Exchange, NormalizedOrder, OrderSide, OrderType, ProductType


@pytest.fixture
def adapter():
    return AngelOneAdapter()


@pytest.mark.asyncio
async def test_authenticate_with_token(adapter: AngelOneAdapter):
    session = await adapter.authenticate({"access_token": "bearer_token", "feed_token": "ft1", "client_code": "user1", "api_key": "key1"})
    assert session.authenticated is True
    assert session.access_token == "bearer_token"
    assert session.broker == "angelone"


@pytest.mark.asyncio
async def test_authenticate_no_creds(adapter: AngelOneAdapter):
    with pytest.raises(ValueError, match="Angel One requires api_key"):
        await adapter.authenticate({})


@pytest.mark.asyncio
async def test_place_order(adapter: AngelOneAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"status": True, "data": {"orderid": "an123"}}
    client.post = AsyncMock(return_value=resp)
    adapter._auth_token = "test"
    adapter._api_key = "key1"

    with patch("brokers.angelone_adapter.get_http_client", return_value=client):
        order = NormalizedOrder(symbol="RELIANCE", exchange=Exchange.NSE, side=OrderSide.BUY, order_type=OrderType.MARKET, product=ProductType.INTRADAY, quantity=10)
        result = await adapter.place_order(order)
    assert result.success is True
    assert result.broker_order_id == "an123"


@pytest.mark.asyncio
async def test_cancel_order_returns_status(adapter: AngelOneAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"status": True, "data": {"orderid": "an999"}}
    client.post = AsyncMock(return_value=resp)
    adapter._auth_token = "test"
    adapter._api_key = "key1"

    with patch("brokers.angelone_adapter.get_http_client", return_value=client):
        result = await adapter.cancel_order("an999")
    assert result.success is True
    assert result.broker_order_id == "an999"


@pytest.mark.asyncio
async def test_cancel_order_failure(adapter: AngelOneAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=400)
    resp.json.return_value = {"status": False, "message": "Order already cancelled"}
    client.post = AsyncMock(return_value=resp)
    adapter._auth_token = "test"
    adapter._api_key = "key1"

    with patch("brokers.angelone_adapter.get_http_client", return_value=client):
        result = await adapter.cancel_order("an999")
    assert result.success is False


@pytest.mark.asyncio
async def test_get_orderbook(adapter: AngelOneAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"status": True, "data": [{"orderid": "o1", "tradingsymbol": "RELIANCE", "exchange": "NSE", "transactiontype": "BUY", "quantity": 10, "price": 2500, "orderstatus": "FILLED"}]}
    client.get = AsyncMock(return_value=resp)
    adapter._auth_token = "test"
    adapter._api_key = "key1"

    with patch("brokers.angelone_adapter.get_http_client", return_value=client):
        orders = await adapter.get_orderbook()
    assert len(orders) == 1
    assert orders[0].broker == "angelone"


@pytest.mark.asyncio
async def test_get_positions(adapter: AngelOneAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"status": True, "data": [{"tradingsymbol": "RELIANCE", "exchange": "NSE", "netqty": 10}]}
    client.get = AsyncMock(return_value=resp)
    adapter._auth_token = "test"
    adapter._api_key = "key1"

    with patch("brokers.angelone_adapter.get_http_client", return_value=client):
        positions = await adapter.get_positions()
    assert len(positions) == 1
