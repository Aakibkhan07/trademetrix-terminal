import pytest
from datetime import UTC, datetime

from market.historical import historical_engine


class FakeCandle:
    def __init__(self):
        self.symbol = "NSE:NIFTY50-INDEX"
        self.exchange = "NSE"
        self.interval = "15m"
        self.open = 24000.0
        self.high = 24050.0
        self.low = 23950.0
        self.close = 24020.0
        self.volume = 123456
        self.timestamp = datetime(2026, 7, 1, 9, 15, tzinfo=UTC)
        self.oi = 0


@pytest.mark.asyncio
async def test_yahoo_fallback_when_broker_fetch_fails(monkeypatch):
    called_with = {}

    async def fake_fetch_historical(symbol, interval, period):
        called_with["symbol"] = symbol
        called_with["interval"] = interval
        called_with["period"] = period
        return [FakeCandle()]

    monkeypatch.setattr("core.db.async_supabase", lambda fn: fn())
    monkeypatch.setattr(
        "core.db.get_supabase",
        lambda: type("S", (), {"table": lambda self, t: (_ for _ in ()).throw(Exception("no creds"))})(),
    )
    monkeypatch.setattr("providers.yahoo.fetch_historical", fake_fetch_historical)

    result = await historical_engine._fetch_from_broker("NIFTY", "NSE", "15m", 30, "user-1")

    assert len(result) == 1
    assert result[0]["symbol"] == "NSE:NIFTY50-INDEX"
    assert called_with == {"symbol": "NSE:NIFTY50-INDEX", "interval": "15m", "period": "30d"}


@pytest.mark.asyncio
async def test_no_yahoo_fallback_for_unsupported_symbol(monkeypatch):
    from core.models import Exchange

    class FakeRow:
        data = None

    class FakeQuery:
        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def single(self, *a, **k):
            return self

        async def execute(self):
            return FakeRow()

    monkeypatch.setattr("core.db.async_supabase", lambda fn: fn())
    monkeypatch.setattr("core.db.get_supabase", lambda: type("S", (), {"table": lambda self, t: FakeQuery()})())
    calls = []

    async def fake_fetch_historical(symbol, interval, period):
        calls.append(symbol)
        return []

    monkeypatch.setattr("providers.yahoo.fetch_historical", fake_fetch_historical)

    result = await historical_engine._fetch_from_broker("RELIANCE", "NSE", "15m", 30, "user-1")

    assert result == []
    assert calls == []
