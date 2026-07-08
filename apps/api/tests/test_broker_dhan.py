import pytest
from unittest.mock import AsyncMock, MagicMock

from brokers.dhan_adapter import DhanAdapter
from core.models import Exchange, NormalizedOrder, OrderSide, OrderType, ProductType


@pytest.fixture
def adapter():
    return DhanAdapter()


@pytest.mark.asyncio
async def test_authenticate_success(adapter: DhanAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"data": []}
    client.get = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)

    session = await adapter.authenticate({"access_token": "test_token", "client_id": "test_client"})
    assert session.authenticated is True
    assert session.access_token == "test_token"
    assert session.broker == "dhan"


@pytest.mark.asyncio
async def test_authenticate_failure(adapter: DhanAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=401)
    client.get = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)

    with pytest.raises(ValueError, match="Dhan authentication failed"):
        await adapter.authenticate({"access_token": "bad_token"})


@pytest.mark.asyncio
async def test_authenticate_with_oauth(adapter: DhanAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"access_token": "oauth_token_dhan"}
    client.post = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)

    session = await adapter.authenticate({"client_id": "cid", "auth_code": "ac1", "secret_key": "sk1"})
    assert session.authenticated is True
    assert session.access_token == "oauth_token_dhan"


@pytest.mark.asyncio
async def test_authenticate_with_oauth_failure(adapter: DhanAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=400)
    resp.json.return_value = {"message": "invalid_grant"}
    client.post = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)

    with pytest.raises(ValueError, match="Dhan token exchange failed"):
        await adapter.authenticate({"client_id": "cid", "auth_code": "bad", "secret_key": "sk1"})


@pytest.mark.asyncio
async def test_place_order(adapter: DhanAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"status": "success", "orderId": "dh123"}
    client.post = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)
    adapter._access_token = "test"
    adapter._client_id = "c1"

    order = NormalizedOrder(symbol="RELIANCE", exchange=Exchange.NSE, side=OrderSide.BUY, order_type=OrderType.MARKET, product=ProductType.INTRADAY, quantity=10)
    result = await adapter.place_order(order)
    assert result.success is True
    assert result.broker_order_id == "dh123"


@pytest.mark.asyncio
async def test_cancel_order_returns_status(adapter: DhanAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"status": "success", "orderId": "dh999"}
    client.delete = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)
    adapter._access_token = "test"

    result = await adapter.cancel_order("dh999")
    assert result.success is True
    assert result.broker_order_id == "dh999"


@pytest.mark.asyncio
async def test_cancel_order_failure(adapter: DhanAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=400)
    resp.json.return_value = {"status": "failure", "message": "Order already cancelled"}
    client.delete = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)
    adapter._access_token = "test"

    result = await adapter.cancel_order("dh999")
    assert result.success is False
