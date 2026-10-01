import pytest

from market.data_socket import SharedDataSocket
from market.simulator import MarketSimulator


@pytest.mark.asyncio
async def test_shared_data_socket_singleton():
    s1 = SharedDataSocket()
    s2 = SharedDataSocket()
    assert s1 is s2


@pytest.mark.asyncio
async def test_market_simulator_start_stop():
    sim = MarketSimulator()
    await sim.start(["NIFTY", "BANKNIFTY"])
    assert sim._running is True
    await sim.stop()
    assert sim._running is False


@pytest.mark.asyncio
async def test_market_simulator_start_twice():
    sim = MarketSimulator()
    await sim.start(["NIFTY"])
    await sim.start(["RELIANCE"])
    assert len(sim._prices) == 2
    assert "NIFTY" in sim._prices
    assert "RELIANCE" in sim._prices
    await sim.stop()


@pytest.mark.asyncio
async def test_quotes_broker_first_uses_broker_and_yahoo_fill(monkeypatch):
    from core.models import Exchange, Quote, UserProfile
    from routes.v1_marketdata import _quotes_with_broker_first

    class FakeEngine:
        _adapter = None

        async def get_active_broker(self, user_id):
            return "fyers"

        async def _get_engine(self, user_id, broker):
            engine = FakeEngine()
            engine._adapter = FakeAdapter()
            return engine

    class FakeAdapter:
        async def get_quotes(self, symbols):
            return [Quote(symbol="SENSEX2680679000CE", exchange=Exchange.BSE, last_price=106.5, close=110.0, broker="fyers")]

    async def fake_fetch_quotes(symbols):
        return [Quote(symbol="RELIANCE-EQ", exchange=Exchange.NSE, last_price=1280.0, close=1260.0, broker="yahoo")]

    from market.data_socket import shared_socket
    monkeypatch.setattr(shared_socket, "get_broker_adapter", lambda broker: None)
    monkeypatch.setattr("application.services.engine_service.EngineService", lambda: FakeEngine())

    # Prices resolve through `BrokerService.resolve_market_data_broker`, not through
    # `EngineService.get_active_broker`. Patching only the latter let the real credential
    # lookup out, and it answered "column broker_credentials.role does not exist" — the
    # test then passed through as Yahoo-only and failed on the broker assertion. The
    # behaviour under test is unchanged; only the seam moved.
    class FakeBrokerService:
        async def resolve_market_data_broker(self, user_id):
            return "fyers"

    import routes.v1_marketdata as marketdata_module

    monkeypatch.setattr(
        marketdata_module, "_broker_service", FakeBrokerService(), raising=True
    )
    monkeypatch.setattr("providers.yahoo.fetch_quotes", fake_fetch_quotes)

    user = UserProfile(id="u1", email="u@example.com")
    result = await _quotes_with_broker_first(["SENSEX2680679000CE", "RELIANCE-EQ"], user)
    by_symbol = {q.symbol: q for q in result}
    assert by_symbol["SENSEX2680679000CE"].last_price == 106.5
    assert by_symbol["SENSEX2680679000CE"].broker == "fyers"
    assert by_symbol["RELIANCE-EQ"].broker == "yahoo"


@pytest.mark.asyncio
async def test_quotes_broker_first_falls_back_fully_to_yahoo(monkeypatch):
    from core.models import Exchange, Quote, UserProfile
    from routes.v1_marketdata import _quotes_with_broker_first

    class FakeEngine:
        async def get_active_broker(self, user_id):
            return "fyers"

        async def _get_engine(self, user_id, broker):
            return self

    async def fake_fetch_quotes(symbols):
        return [Quote(symbol=s, exchange=Exchange.NSE, last_price=10.0, close=9.0, broker="yahoo") for s in symbols]

    from market.data_socket import shared_socket
    monkeypatch.setattr(shared_socket, "get_broker_adapter", lambda broker: None)
    monkeypatch.setattr("application.services.engine_service.EngineService", lambda: FakeEngine())

    # Same seam as above — see the note in the broker-first test.
    class FakeBrokerService:
        async def resolve_market_data_broker(self, user_id):
            return "fyers"

    import routes.v1_marketdata as marketdata_module

    monkeypatch.setattr(
        marketdata_module, "_broker_service", FakeBrokerService(), raising=True
    )
    monkeypatch.setattr("providers.yahoo.fetch_quotes", fake_fetch_quotes)

    user = UserProfile(id="u1", email="u@example.com")
    result = await _quotes_with_broker_first(["RELIANCE-EQ"], user)
    assert result and result[0].broker == "yahoo"
