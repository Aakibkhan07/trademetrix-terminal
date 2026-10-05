import pytest
from unittest.mock import AsyncMock, MagicMock

from brokers.dhan_adapter import DhanAdapter
from core.models import (
    Exchange,
    InstrumentType,
    NormalizedOrder,
    OrderSide,
    OrderType,
    ProductType,
)


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


@pytest.fixture
def instrument_provider():
    """Register one resolved instrument for the duration of a test.

    place_order refuses to build a payload without authoritative contract metadata,
    so every order-path test needs a resolved contract. Swapping the registry
    wholesale (rather than appending) keeps one test's provider out of the next.
    """
    from market.instruments import Instrument, instrument_resolver

    saved = list(instrument_resolver._providers)

    def _register(inst: Instrument | None):
        instrument_resolver._providers = []
        if inst is not None:
            instrument_resolver.register("fixture", lambda *a, **k: inst, authoritative=True)

    yield _register
    instrument_resolver._providers = saved


def _nifty_future():
    from market.instruments import Instrument

    return Instrument(
        broker="dhan",
        security_id="49081",
        broker_symbol="NIFTY26AUGFUT",
        exchange_segment="NSE_FNO",
        instrument_type="FUT",
        lot_size=65,
        underlying="NIFTY",
        expiry="2026-08-28",
        source="fixture",
    )


@pytest.mark.asyncio
async def test_place_order(adapter: DhanAdapter, instrument_provider):
    """A resolved contract produces a payload built from resolved metadata."""
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"status": "success", "orderId": "dh123"}
    client.post = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)
    adapter._access_token = "test"
    adapter._client_id = "c1"
    instrument_provider(_nifty_future())

    order = NormalizedOrder(
        symbol="NSE:NIFTY26AUGFUT",
        exchange=Exchange.NFO,
        instrument_type=InstrumentType.FUT,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        product=ProductType.INTRADAY,
        quantity=65,
    )
    result = await adapter.place_order(order)
    assert result.success is True
    assert result.broker_order_id == "dh123"

    # The payload must carry the broker's own identifiers, not the display symbol,
    # and must not multiply the quantity by the lot size.
    payload = client.post.await_args.kwargs["json"]
    assert payload["securityId"] == "49081"
    assert payload["exchangeSegment"] == "NSE_FNO"
    assert payload["quantity"] == 65
    assert payload["drvExpiryDate"] == "2026-08-28"
    assert payload["securityId"] != "NSE:NIFTY26AUGFUT"


@pytest.mark.asyncio
async def test_place_order_blocks_when_metadata_unresolvable(adapter: DhanAdapter, instrument_provider):
    """No authoritative provider means no order, and no HTTP call is issued."""
    client = AsyncMock()
    adapter._get_client = AsyncMock(return_value=client)
    adapter._access_token = "test"
    adapter._client_id = "c1"
    instrument_provider(None)

    order = NormalizedOrder(
        symbol="NSE:NIFTY26AUGFUT",
        exchange=Exchange.NFO,
        instrument_type=InstrumentType.FUT,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        product=ProductType.INTRADAY,
        quantity=65,
    )
    result = await adapter.place_order(order)

    assert result.success is False
    assert result.status == "rejected"
    for required in ("Security ID", "Exchange Segment", "Instrument Type", "Lot Size"):
        assert required in result.message
    client.post.assert_not_called()


@pytest.mark.asyncio
async def test_place_order_does_not_default_segment_to_cash_equity(adapter: DhanAdapter, instrument_provider):
    """The resolved segment wins, even for a pair the removed local map did not list.

    That map defaulted to "NSE_EQ" for any (exchange, instrument_type) pair outside
    its seven entries, which addressed a futures order to the cash-equity segment.
    """
    client = AsyncMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"status": "success", "orderId": "dh124"}
    client.post = AsyncMock(return_value=resp)
    adapter._get_client = AsyncMock(return_value=client)
    adapter._access_token = "test"
    adapter._client_id = "c1"
    instrument_provider(_nifty_future())

    # (NSE, FUT) is not in the map the old code used -- (NFO, FUT) is.
    order = NormalizedOrder(
        symbol="NSE:NIFTY26AUGFUT",
        exchange=Exchange.NSE,
        instrument_type=InstrumentType.FUT,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        product=ProductType.INTRADAY,
        quantity=130,
    )
    await adapter.place_order(order)

    payload = client.post.await_args.kwargs["json"]
    assert payload["exchangeSegment"] == "NSE_FNO"
    assert payload["quantity"] == 130


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
