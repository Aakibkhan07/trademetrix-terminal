import pytest

from ai.journal import AIJournal


class _Result:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, name, orders_result=None, trades_result=None, trades_raise=None):
        self.name = name
        self._orders_result = orders_result
        self._trades_result = trades_result
        self._trades_raise = trades_raise

    def select(self, *a, **k):
        return self

    def eq(self, a, b):
        return self

    def gte(self, a, b):
        return self

    def limit(self, n):
        return self

    def order(self, *a, **k):
        return self

    async def execute(self):
        if self.name == "orders":
            return self._orders_result
        if self._trades_raise is not None:
            raise self._trades_raise
        return self._trades_result


class _FakeSupabase:
    def __init__(self, orders_result=_Result([]), trades_result=_Result([]), trades_raise=None):
        self._orders_result = orders_result
        self._trades_result = trades_result
        self._trades_raise = trades_raise

    def table(self, name):
        return _FakeTable(
            name,
            orders_result=self._orders_result,
            trades_result=self._trades_result,
            trades_raise=self._trades_raise,
        )


@pytest.mark.asyncio
async def test_orders_query_wins_when_populated(monkeypatch):
    orders = _Result([{
        "id": "o1", "symbol": "NIFTY", "side": "BUY",
        "filled_quantity": 65, "average_price": 24100,
        "total_value": 1566500, "created_at": "2026-08-01T10:00:00Z",
        "is_paper": True,
    }])
    fake = _FakeSupabase(orders_result=orders, trades_raise=AssertionError("trades must not be queried"))
    monkeypatch.setattr("ai.journal.get_supabase", lambda: fake)
    monkeypatch.setattr("ai.journal.async_supabase", lambda fn: fn())

    journal = AIJournal("user-1")
    result = await journal._get_recent_trades(7)
    assert len(result) == 1
    assert result[0]["symbol"] == "NIFTY"
    assert result[0]["quantity"] == 65
    assert result[0]["value"] == 1566500
    assert result[0]["source"] == "orders"


@pytest.mark.asyncio
async def test_trades_fallback_when_orders_empty(monkeypatch):
    trades = _Result([{
        "id": "t1", "symbol": "BANKNIFTY", "side": "SELL",
        "quantity": 30, "price": 51000, "value": 1530000,
        "created_at": "2026-08-01T10:00:00Z", "is_paper": True,
    }])
    fake = _FakeSupabase(orders_result=_Result([]), trades_result=trades)
    monkeypatch.setattr("ai.journal.get_supabase", lambda: fake)
    monkeypatch.setattr("ai.journal.async_supabase", lambda fn: fn())

    journal = AIJournal("user-1")
    result = await journal._get_recent_trades(7)
    assert len(result) == 1
    assert result[0]["symbol"] == "BANKNIFTY"


@pytest.mark.asyncio
async def test_orders_query_error_falls_back_to_trades(monkeypatch):
    trades = _Result([{
        "id": "t2", "symbol": "FINNIFTY", "side": "BUY",
        "quantity": 10, "price": 21000, "value": 210000,
        "created_at": "2026-08-01T10:00:00Z", "is_paper": True,
    }])
    fake = _FakeSupabase(orders_result=None, trades_result=trades, trades_raise=None)
    monkeypatch.setattr("ai.journal.get_supabase", lambda: fake)
    monkeypatch.setattr("ai.journal.async_supabase", lambda fn: fn())

    journal = AIJournal("user-1")
    result = await journal._get_recent_trades(7)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_schema_drift_returns_empty_not_500(monkeypatch):
    """Both tables failing (e.g. trades.created_at missing) must yield [], never 500."""
    schema_error = type("PGError", (Exception,), {})("PG 42703: column trades.created_at does not exist")
    fake = _FakeSupabase(
        orders_result=None,
        trades_result=None,
        trades_raise=schema_error,
    )
    monkeypatch.setattr("ai.journal.get_supabase", lambda: fake)
    monkeypatch.setattr("ai.journal.async_supabase", lambda fn: fn())

    journal = AIJournal("user-drifting")
    result = await journal._get_recent_trades(7)
    assert result == []


@pytest.mark.asyncio
async def test_analyze_trades_graceful_when_no_trades(monkeypatch):
    fake = _FakeSupabase(orders_result=_Result([]), trades_result=_Result([]))
    monkeypatch.setattr("ai.journal.get_supabase", lambda: fake)
    monkeypatch.setattr("ai.journal.async_supabase", lambda fn: fn())

    journal = AIJournal("user-test")
    result = await journal.analyze_trades(7)
    assert result.get("analysis") == "No trades found in the selected period."
    assert result.get("stats") == {}