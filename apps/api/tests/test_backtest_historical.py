import pytest

from backtest.historical import backtest_historical
from market.historical import historical_engine


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def gte(self, *a, **k):
        return self

    def lte(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        return FakeResult(self.rows)


class FakeSupabase:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def table(self, name):
        self.calls += 1
        return FakeQuery(self.rows)


async def _passthrough(call, *args, **kwargs):
    return call()


def _candle(ts, close, symbol="TST1"):
    return {
        "symbol": symbol,
        "exchange": "NSE",
        "interval": "15m",
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 1000,
        "timestamp": ts,
        "oi": 500,
    }


def _row(ts, close):
    return {
        "id": f"NSE:TST1:15m:{ts}",
        "symbol": "TST1",
        "exchange": "NSE",
        "interval": "15m",
        "ts": ts,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 1000,
        "oi": 500,
        "source": "db",
    }


@pytest.mark.asyncio
async def test_load_uses_db_first(monkeypatch):
    rows = [
        _row("2026-01-01T09:15:00+00:00", 99.0),
        _row("2026-01-05T09:15:00+00:00", 100.0),
        _row("2026-01-08T09:30:00+00:00", 101.0),
        _row("2026-01-09T09:15:00+00:00", 102.0),
    ]
    fake = FakeSupabase(rows)
    monkeypatch.setattr("backtest.historical.get_supabase", lambda: fake)
    monkeypatch.setattr("backtest.historical.async_supabase", _passthrough)

    async def fake_fetch(symbol, exchange="NSE", interval="15m", days=7, user_id=None):
        raise AssertionError("durable data covers the range — must not fetch")

    monkeypatch.setattr(historical_engine, "get_historical", fake_fetch)

    candles = await backtest_historical.load(
        "TST1", "NSE", "15m", start="2026-01-01", end="2026-01-10"
    )
    assert len(candles) == 4
    assert candles[0]["symbol"] == "TST1"
    assert candles[0]["close"] == 99.0
    assert "+00:00" in candles[0]["timestamp"]
    assert fake.calls == 1


@pytest.mark.asyncio
async def test_load_falls_back_to_broker_and_stores(monkeypatch):
    rows = []
    fake = FakeSupabase(rows)
    monkeypatch.setattr("backtest.historical.get_supabase", lambda: fake)
    monkeypatch.setattr("backtest.historical.async_supabase", _passthrough)

    synthetic = [
        _candle("2026-01-05T09:15:00+00:00", 100.0, "TST2"),
        _candle("2026-01-05T09:30:00+00:00", 101.0, "TST2"),
        _candle("2026-01-05T09:45:00+00:00", 102.0, "TST2"),
    ]

    async def fake_fetch(symbol, exchange="NSE", interval="15m", days=7, user_id=None):
        return synthetic

    monkeypatch.setattr(historical_engine, "get_historical", fake_fetch)
    stored = []

    async def fake_store(candles, source="broker"):
        stored.append((list(candles), source))

    monkeypatch.setattr(backtest_historical, "_store", fake_store)

    candles = await backtest_historical.load(
        "TST2", "NSE", "15m", start="2026-01-01", end="2026-01-10", user_id="u1"
    )
    assert len(candles) == 3
    assert len(stored) == 1
    assert len(stored[0][0]) == 3
    assert stored[0][1] == "broker"


@pytest.mark.asyncio
async def test_load_refetches_when_store_does_not_cover_range(monkeypatch):
    rows = [
        _row("2026-01-05T09:15:00+00:00", 100.0),
        _row("2026-01-05T09:30:00+00:00", 101.0),
    ]
    fake = FakeSupabase(rows)
    monkeypatch.setattr("backtest.historical.get_supabase", lambda: fake)
    monkeypatch.setattr("backtest.historical.async_supabase", _passthrough)

    synthetic = [
        _candle("2026-01-01T09:15:00+00:00", 98.0, "TST4"),
        _candle("2026-01-02T09:15:00+00:00", 99.0, "TST4"),
        _candle("2026-01-03T09:15:00+00:00", 100.0, "TST4"),
    ]

    async def fake_fetch(symbol, exchange="NSE", interval="15m", days=7, user_id=None):
        return synthetic

    monkeypatch.setattr(historical_engine, "get_historical", fake_fetch)
    stored = []

    async def fake_store(candles, source="broker"):
        stored.append((list(candles), source))

    monkeypatch.setattr(backtest_historical, "_store", fake_store)

    candles = await backtest_historical.load(
        "TST4", "NSE", "15m", start="2026-01-01", end="2026-01-10"
    )
    covers = ["2026-01-01T09:15", "2026-01-02T09:15", "2026-01-03T09:15",
              "2026-01-05T09:15", "2026-01-05T09:30"]
    assert [str(c["timestamp"])[:16] for c in candles] == covers
    assert len(stored) == 1


@pytest.mark.asyncio
async def test_load_caches_second_call(monkeypatch):
    async def fake_fetch(symbol, exchange="NSE", interval="15m", days=7, user_id=None):
        return []

    monkeypatch.setattr(historical_engine, "get_historical", fake_fetch)

    rows = [_row("2026-01-05T09:15:00+00:00", 100.0)]
    fake = FakeSupabase(rows)
    monkeypatch.setattr("backtest.historical.get_supabase", lambda: fake)
    monkeypatch.setattr("backtest.historical.async_supabase", _passthrough)

    first = await backtest_historical.load(
        "TST3", "NSE", "15m", start="2026-01-01", end="2026-01-10"
    )
    second = await backtest_historical.load(
        "TST3", "NSE", "15m", start="2026-01-01", end="2026-01-10"
    )
    assert first is second
    assert fake.calls == 1


@pytest.mark.asyncio
async def test_store_fail_open_when_db_unavailable(monkeypatch):
    def boom():
        raise RuntimeError("table missing")

    monkeypatch.setattr("backtest.historical.get_supabase", boom)

    async def boom_call(*a, **k):
        raise RuntimeError("table missing")

    monkeypatch.setattr("backtest.historical.async_supabase", boom_call)

    await backtest_historical._store([_candle("2026-01-05T09:15:00+00:00", 100.0)])
    candles = await backtest_historical._load_from_db(
        "TST1", "NSE", "15m", __import__("datetime").datetime(2026, 1, 1),
        __import__("datetime").datetime(2026, 1, 10),
    )
    assert candles == []


@pytest.mark.asyncio
async def test_continuous_futures_roll_back_adjustment(monkeypatch):
    from datetime import datetime

    months = []

    def fake_contract_symbol(base, month):
        months.append(month.month)
        codes = {1: "JAN", 2: "FEB"}
        return f"NIFTY26{codes[month.month]}FUT" if month.month in codes else ""

    monkeypatch.setattr(backtest_historical, "_contract_symbol", fake_contract_symbol)

    seg_a = [
        _candle("2026-01-05T09:15:00+00:00", 98.0, "NSE:NIFTY26JANFUT"),
        _candle("2026-01-06T09:15:00+00:00", 99.0, "NSE:NIFTY26JANFUT"),
        _candle("2026-01-07T09:15:00+00:00", 100.0, "NSE:NIFTY26JANFUT"),
    ]
    seg_b = [
        _candle("2026-01-08T09:15:00+00:00", 110.0, "NSE:NIFTY26FEBFUT"),
        _candle("2026-01-09T09:15:00+00:00", 111.0, "NSE:NIFTY26FEBFUT"),
        _candle("2026-01-12T09:15:00+00:00", 112.0, "NSE:NIFTY26FEBFUT"),
    ]

    async def fake_load(symbol, exchange="NSE", interval="1d", days=40,
                        start="", end="", user_id=None, force_refresh=False):
        if "JAN" in symbol:
            return seg_a
        if "FEB" in symbol:
            return seg_b
        return []

    monkeypatch.setattr(backtest_historical, "load", fake_load)

    series = await backtest_historical.load_continuous(
        "NIFTY", "NSE", "1d", start="2026-01-01", end="2026-02-15"
    )
    assert len(series) == 6
    assert all(c.get("continuous") is True for c in series)

    closes = [c["close"] for c in series]
    assert closes[:3] == [98.0, 99.0, 100.0]
    assert closes[3] == pytest.approx(100.0)
    assert closes[4] == pytest.approx(100.9091)
    assert closes[5] == pytest.approx(101.8182)

    roll = series[-1].get("roll_dates")
    assert roll and roll[0]["date"] == "2026-01-07"
    assert roll[0]["adjustment"] == pytest.approx(0.909091, abs=1e-5)


@pytest.mark.asyncio
async def test_corporate_action_price_adjustment(monkeypatch):
    actions = [
        {"symbol": "TST6", "action": "SPLIT", "ratio": "1:2",
         "ex_date": "2026-01-06", "dividend_amount": 0.0},
        {"symbol": "TST6", "action": "DIVIDEND", "ratio": "",
         "ex_date": "2026-01-08", "dividend_amount": 5.0},
    ]
    async def fake_actions(symbol):
        return actions

    monkeypatch.setattr(backtest_historical, "_load_actions", fake_actions)

    candles = [
        _candle("2026-01-05T09:15:00+00:00", 100.0, "TST6"),
        _candle("2026-01-06T09:15:00+00:00", 105.0, "TST6"),
        _candle("2026-01-07T09:15:00+00:00", 110.0, "TST6"),
        _candle("2026-01-09T09:15:00+00:00", 120.0, "TST6"),
    ]
    adjusted, applied = await backtest_historical.apply_corporate_actions(candles, "TST6")
    assert adjusted[0]["close"] == 50.0
    assert adjusted[1]["close"] == 105.0
    assert adjusted[2]["close"] == 110.0
    assert adjusted[3]["close"] == 120.0
    assert len(applied) == 2
    assert applied[0]["ratio"] == "1:2"


@pytest.mark.asyncio
async def test_corporate_action_fail_open(monkeypatch):
    async def no_actions(symbol):
        return []

    monkeypatch.setattr(backtest_historical, "_load_actions", no_actions)
    candles = [_candle("2026-01-05T09:15:00+00:00", 100.0, "TST7")]
    adjusted, applied = await backtest_historical.apply_corporate_actions(candles, "TST7")
    assert adjusted is candles
    assert applied == []
