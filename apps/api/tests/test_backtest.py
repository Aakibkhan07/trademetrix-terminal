import pytest
from engine.backtest import BacktestEngine, BacktestResult, _synthesize_candles


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
    candles = _synthesize_candles("NIFTY", days=7, interval="1h")
    assert len(candles) == 7 * 24
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
