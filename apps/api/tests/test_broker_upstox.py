import pytest
from unittest.mock import AsyncMock, MagicMock

from brokers.upstox_adapter import UpstoxAdapter
from core.models import Exchange, NormalizedOrder, OrderSide, OrderType, ProductType


@pytest.fixture
def adapter():
    return UpstoxAdapter()


@pytest.mark.asyncio
async def test_authenticate_success(adapter: UpstoxAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"data": {"user_id": "test_user"}}
    client.get = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)

    session = await adapter.authenticate({"access_token": "test_token"})
    assert session.authenticated is True
    assert session.user_id == "test_user"
    assert session.broker == "upstox"


@pytest.mark.asyncio
async def test_authenticate_failure(adapter: UpstoxAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=401)
    client.get = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)

    with pytest.raises(ValueError, match="invalid access_token"):
        await adapter.authenticate({"access_token": "bad_token"})


@pytest.mark.asyncio
async def test_authenticate_with_refresh(adapter: UpstoxAdapter):
    client = AsyncMock()
    profile_resp = MagicMock(status_code=401)
    refresh_resp = MagicMock(status_code=200)
    refresh_resp.json.return_value = {"access_token": "refreshed_token", "expires_in": 3600}
    client.get = AsyncMock(return_value=profile_resp)
    client.post = AsyncMock(return_value=refresh_resp)
    adapter._get_client = AsyncMock(return_value=client)

    session = await adapter.authenticate({"access_token": "expired", "refresh_token": "rt1", "client_id": "c1"})
    assert session.authenticated is True
    assert session.access_token == "refreshed_token"
    assert session.broker == "upstox"


@pytest.mark.asyncio
async def test_login_with_credentials(adapter: UpstoxAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"access_token": "new_token"}
    client.post = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)

    session = await adapter.authenticate({"client_id": "api_key_1", "secret_key": "secret_1"})
    assert session.authenticated is True
    assert session.access_token == "new_token"


@pytest.mark.asyncio
async def test_authenticate_with_oauth(adapter: UpstoxAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"access_token": "oauth_token_upstox", "expires_in": 86400}
    client.post = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)

    session = await adapter.authenticate({"client_id": "cid", "auth_code": "ac1", "secret_key": "sk1"})
    assert session.authenticated is True
    assert session.access_token == "oauth_token_upstox"


@pytest.mark.asyncio
async def test_authenticate_with_oauth_failure(adapter: UpstoxAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=400)
    resp.json.return_value = {"message": "invalid_grant"}
    client.post = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)

    with pytest.raises(ValueError, match="Upstox token exchange failed"):
        await adapter.authenticate({"client_id": "cid", "auth_code": "bad", "secret_key": "sk1"})


@pytest.mark.asyncio
async def test_place_order(adapter: UpstoxAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"status": "success", "data": {"order_id": "up123"}}
    client.post = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)
    adapter._access_token = "test"

    order = NormalizedOrder(symbol="RELIANCE", exchange=Exchange.NSE, side=OrderSide.BUY, order_type=OrderType.MARKET, product=ProductType.INTRADAY, quantity=10)
    result = await adapter.place_order(order)
    assert result.success is True
    assert result.broker_order_id == "up123"


@pytest.mark.asyncio
async def test_cancel_order_returns_status(adapter: UpstoxAdapter):
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"status": "success", "data": {"order_id": "up999"}}
    client.delete = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)
    adapter._access_token = "test"

    result = await adapter.cancel_order("up999")
    assert result.success is True
    assert result.broker_order_id == "up999"
