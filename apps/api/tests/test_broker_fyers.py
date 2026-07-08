import pytest
from unittest.mock import AsyncMock, MagicMock

from brokers.fyers_adapter import FyersAdapter
from core.models import Exchange, NormalizedOrder, OrderSide, OrderType, ProductType


@pytest.fixture
def adapter():
    return FyersAdapter()


@pytest.mark.asyncio
async def test_authenticate_success(adapter: FyersAdapter):
    session = await adapter.authenticate({"client_id": "test_client", "access_token": "test_token"})
    assert session.authenticated is True
    assert session.user_id == "test_client"
    assert session.broker == "fyers"


@pytest.mark.asyncio
async def test_authenticate_failure(adapter: FyersAdapter):
    with pytest.raises(ValueError, match="auth_code and secret_key required"):
        await adapter.authenticate({"client_id": "test_client"})


@pytest.mark.asyncio
async def test_authenticate_with_oauth(adapter: FyersAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"s": "ok", "access_token": "oauth_token"}
    client.post = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)

    session = await adapter.authenticate({"client_id": "cid", "auth_code": "ac1", "secret_key": "sk1"})
    assert session.authenticated is True
    assert session.access_token == "oauth_token"


@pytest.mark.asyncio
async def test_place_order(adapter: FyersAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"s": "ok", "id": "fy123"}
    client.post = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)
    adapter._access_token = "test"
    adapter._client_id = "cid"

    order = NormalizedOrder(symbol="RELIANCE", exchange=Exchange.NSE, side=OrderSide.BUY, order_type=OrderType.MARKET, product=ProductType.INTRADAY, quantity=10)
    result = await adapter.place_order(order)
    assert result.success is True
    assert result.broker_order_id == "fy123"


@pytest.mark.asyncio
async def test_cancel_order_returns_status(adapter: FyersAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"s": "ok", "id": "fy999"}
    client.delete = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)
    adapter._access_token = "test"
    adapter._client_id = "cid"

    result = await adapter.cancel_order("fy999")
    assert result.success is True
    assert result.broker_order_id == "fy999"


@pytest.mark.asyncio
async def test_get_orderbook(adapter: FyersAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"s": "ok", "orderBook": [{"id": "o1", "symbol": "NSE:RELIANCE", "qty": 1, "type": 2, "side": 1, "status": 2, "productType": "INTRADAY"}]}
    client.get = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)
    adapter._access_token = "test"
    adapter._client_id = "cid"

    orders = await adapter.get_orderbook()
    assert len(orders) == 1
    assert orders[0].broker == "fyers"


@pytest.mark.asyncio
async def test_get_positions(adapter: FyersAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"s": "ok", "netPositions": [{"symbol": "NSE:RELIANCE", "netQty": 10}]}
    client.get = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)
    adapter._access_token = "test"
    adapter._client_id = "cid"

    positions = await adapter.get_positions()
    assert len(positions) == 1


@pytest.mark.asyncio
async def test_get_funds(adapter: FyersAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"s": "ok", "fund_limit": [{"title": "Total Balance", "equityAmount": 50000}, {"title": "Utilized Amount", "equityAmount": 10000}, {"title": "Clear Balance", "equityAmount": 40000}]}
    client.get = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)
    adapter._access_token = "test"
    adapter._client_id = "cid"

    funds = await adapter.get_funds()
    assert funds.total_margin == 50000
    assert funds.available_margin == 40000
    assert funds.broker == "fyers"
