import pytest
from unittest.mock import AsyncMock, MagicMock

from brokers.fyers_adapter import FyersAdapter
from brokers.fyers_http import FyersResponse
from core.models import Exchange, NormalizedOrder, OrderSide, OrderType, ProductType


def _resp(status: int, payload: dict) -> FyersResponse:
    import json
    return FyersResponse(status_code=status, body=json.dumps(payload).encode("utf-8"))


@pytest.fixture
def adapter():
    a = FyersAdapter()
    a._http.request = AsyncMock()
    return a


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
async def test_authenticate_with_oauth(adapter: FyersAdapter, monkeypatch):
    fake_transport = MagicMock()
    fake_transport.request = AsyncMock(return_value=_resp(200, {"s": "ok", "access_token": "oauth_token"}))
    fake_transport.set_token = MagicMock()
    monkeypatch.setattr("brokers.fyers_adapter.get_transport", lambda cid, tok: fake_transport)

    session = await adapter.authenticate({"client_id": "cid", "auth_code": "ac1", "secret_key": "sk1"})
    assert session.authenticated is True
    assert session.access_token == "oauth_token"
    fake_transport.request.assert_awaited_once()
    assert fake_transport.request.await_args.kwargs["authenticated"] is False


@pytest.mark.asyncio
async def test_place_order(adapter: FyersAdapter):
    adapter._http.request = AsyncMock(return_value=_resp(200, {"s": "ok", "id": "fy123"}))
    adapter._access_token = "test"
    adapter._client_id = "cid"

    order = NormalizedOrder(symbol="RELIANCE", exchange=Exchange.NSE, side=OrderSide.BUY, order_type=OrderType.MARKET, product=ProductType.INTRADAY, quantity=10)
    result = await adapter.place_order(order)
    assert result.success is True
    assert result.broker_order_id == "fy123"
    assert adapter._http.request.await_args.kwargs["retries"] == 0


@pytest.mark.asyncio
async def test_cancel_order_returns_status(adapter: FyersAdapter):
    adapter._http.request = AsyncMock(return_value=_resp(200, {"s": "ok", "id": "fy999"}))
    adapter._access_token = "test"
    adapter._client_id = "cid"

    result = await adapter.cancel_order("fy999")
    assert result.success is True
    assert result.broker_order_id == "fy999"


@pytest.mark.asyncio
async def test_get_orderbook(adapter: FyersAdapter):
    adapter._http.request = AsyncMock(return_value=_resp(200, {"s": "ok", "orderBook": [{"id": "o1", "symbol": "NSE:RELIANCE", "qty": 1, "type": 2, "side": 1, "status": 2, "productType": "INTRADAY"}]}))
    adapter._access_token = "test"
    adapter._client_id = "cid"

    orders = await adapter.get_orderbook()
    assert len(orders) == 1
    assert orders[0].broker == "fyers"


@pytest.mark.asyncio
async def test_get_positions(adapter: FyersAdapter):
    adapter._http.request = AsyncMock(return_value=_resp(200, {"s": "ok", "netPositions": [{"symbol": "NSE:RELIANCE", "netQty": 10}]}))
    adapter._access_token = "test"
    adapter._client_id = "cid"

    positions = await adapter.get_positions()
    assert len(positions) == 1


@pytest.mark.asyncio
async def test_get_funds(adapter: FyersAdapter):
    adapter._http.request = AsyncMock(return_value=_resp(200, {"s": "ok", "fund_limit": [{"title": "Total Balance", "equityAmount": 50000}, {"title": "Utilized Amount", "equityAmount": 10000}, {"title": "Clear Balance", "equityAmount": 40000}]}))
    adapter._access_token = "test"
    adapter._client_id = "cid"

    funds = await adapter.get_funds()
    assert funds.total_margin == 50000
    assert funds.available_margin == 40000
    assert funds.broker == "fyers"


@pytest.mark.asyncio
async def test_get_quotes_falls_back_to_yahoo(adapter: FyersAdapter, monkeypatch):
    adapter._http.request = AsyncMock(return_value=_resp(429, {"s": "error", "message": "rate limited"}))
    adapter._access_token = "test"
    adapter._client_id = "cid"

    async def fake_fetch_quotes(symbols):
        return []
    monkeypatch.setattr("providers.yahoo.fetch_quotes", fake_fetch_quotes)

    quotes = await adapter.get_quotes(["RELIANCE"])
    assert quotes == []


def test_parse_sdk_tick_full_payload_sets_change_pct(adapter: FyersAdapter):
    msg = {
        "symbol": "NSE:NIFTY26AUGFUT",
        "ltp": 24500.0,
        "ch": -100.0,
        "chp": -0.41,
        "bid_price": 24499.5,
        "ask_price": 24500.5,
        "prev_close_price": 24600.0,
        "volume": 1200,
        "oi": 345000,
    }
    tick = adapter._parse_sdk_tick(msg)
    assert tick is not None
    assert tick.symbol == "NSE:NIFTY26AUGFUT"
    assert tick.change == -100.0
    assert tick.change_pct == -0.41
    assert tick.bid == 24499.5
    assert tick.ask == 24500.5
    assert tick.oi == 345000


def test_parse_sdk_tick_litemode_payload_zero_fill(adapter: FyersAdapter):
    msg = {"symbol": "NSE:NIFTY50-INDEX", "ltp": 24471.4, "type": "if"}
    tick = adapter._parse_sdk_tick(msg)
    assert tick is not None
    assert tick.last_price == 24471.4
    assert tick.change_pct == 0.0


def test_subscribe_symbols_adds_to_feed(adapter: FyersAdapter):
    ws = MagicMock()
    adapter._ws_instance = ws
    adapter._running = True
    adapter._subscribed_symbols = ["NSE:NIFTY50-INDEX"]
    adapter._symbol_reverse_map = {"NSE:NIFTY50-INDEX": "NSE:NIFTY50-INDEX"}

    pending = adapter.subscribe_symbols(["NSE:NIFTY50-INDEX", "NSE:NIFTY26AUGFUT"])
    assert pending == []
    ws.subscribe.assert_called_once_with(symbols=["NSE:NIFTY26AUGFUT"])
    assert "NSE:NIFTY26AUGFUT" in adapter._subscribed_symbols
    assert adapter._symbol_reverse_map["NSE:NIFTY26AUGFUT"] == "NSE:NIFTY26AUGFUT"


def test_subscribe_symbols_returns_pending_when_no_socket(adapter: FyersAdapter):
    adapter._ws_instance = None
    adapter._running = True
    pending = adapter.subscribe_symbols(["NSE:NIFTY26AUGFUT"])
    assert pending == ["NSE:NIFTY26AUGFUT"]
