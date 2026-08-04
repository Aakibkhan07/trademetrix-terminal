import pytest

from engine.backtest import BacktestEngine, BacktestResult, _synthesize_candles, fetch_historical_data


@pytest.mark.asyncio
async def test_backtest_engine_run():
    candles = _synthesize_candles("NIFTY", days=30, interval="15m")
    assert len(candles) > 0

    engine = BacktestEngine("trend_rider", {"symbol": "NIFTY"}, initial_capital=100000)
    result = await engine.run(candles)

    assert isinstance(result, BacktestResult)
    assert result.total_trades >= 0
    assert result.win_rate >= 0
    assert result.sharpe_ratio >= -10


@pytest.mark.asyncio
async def test_backtest_synthesize_candles():
    candles = _synthesize_candles("NIFTY", days=7, interval="60m")
    assert len(candles) > 0 and len(candles) < 7 * 24
    for c in candles:
        assert c["symbol"] == "NIFTY"
        assert c["high"] >= c["low"]
        assert c["volume"] > 0


@pytest.mark.asyncio
async def test_backtest_result_tracking():
    result = BacktestResult()
    result.record_trade("NIFTY", "BUY", 100, 110, 10, "2024-01-01T00:00:00", "2024-01-01T01:00:00")
    assert result.total_trades == 1
    assert result.winning_trades == 1
    assert result.total_pnl > 0


@pytest.mark.asyncio
async def test_fetch_historical_data_uses_durable_store(monkeypatch):
    real = [
        {"symbol": "TST", "exchange": "NSE", "interval": "15m",
         "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000,
         "timestamp": "2026-01-05T09:15:00+00:00"},
    ]

    async def fake_load(symbol="", exchange="NSE", interval="15m", days=7, user_id=None):
        return real

    monkeypatch.setattr("backtest.historical.backtest_historical.load", fake_load)
    candles = await fetch_historical_data("TST", "NSE", "15m", 7, "u1")
    assert candles == real


@pytest.mark.asyncio
async def test_fetch_historical_data_falls_back_to_synthetic_only_when_empty(monkeypatch):
    async def fake_load(symbol="", exchange="NSE", interval="15m", days=7, user_id=None):
        return []

    monkeypatch.setattr("backtest.historical.backtest_historical.load", fake_load)
    candles = await fetch_historical_data("NIFTY", "NSE", "15m", 7, "u1")
    assert candles
    assert candles[0]["symbol"] == "NIFTY"
