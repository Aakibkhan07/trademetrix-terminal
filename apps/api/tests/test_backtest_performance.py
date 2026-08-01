from datetime import UTC, datetime, timedelta

import pytest

from backtest.models import BacktestResult, TradeRecord
from backtest.performance import performance_analytics


def _trade(pnl, entry_time, symbol="NIFTY"):
    return TradeRecord(
        symbol=symbol,
        side="BUY",
        entry_price=100.0,
        exit_price=100.0 + pnl / 10,
        quantity=10,
        pnl=pnl,
        entry_time=entry_time,
        exit_time=entry_time,
    )


def _snapshots(equities):
    start = datetime(2026, 1, 5, 9, 15, tzinfo=UTC)
    return [
        {"index": i, "timestamp": (start + timedelta(minutes=15 * i)).isoformat(),
         "equity": eq, "positions": [], "pnl": {}}
        for i, eq in enumerate(equities)
    ]


def _candles(n=100, base=100.0, step=1.0):
    start = datetime(2026, 1, 5, 9, 15, tzinfo=UTC)
    return [
        {"symbol": "NIFTY", "exchange": "NSE", "interval": "15m",
         "open": base + step * i, "high": base + step * i + 1,
         "low": base + step * i - 1, "close": base + step * i,
         "volume": 1000, "timestamp": (start + timedelta(minutes=15 * i)).isoformat(),
         "oi": 0}
        for i in range(n)
    ]


def test_expectancy_and_risk_reward_ratios():
    result = BacktestResult()
    trades = [
        _trade(200, "2026-01-05T10:00:00+00:00"),
        _trade(-100, "2026-01-05T11:00:00+00:00"),
        _trade(300, "2026-01-06T10:00:00+00:00"),
        _trade(-100, "2026-01-06T11:00:00+00:00"),
        _trade(100, "2026-01-07T10:00:00+00:00"),
    ]
    result = performance_analytics.calculate(
        result, _snapshots([100000.0]), 100000.0, trades, candles_analyzed=100,
    )
    assert result.expectancy == 80.0
    assert result.expectancy_per_r == 0.8
    assert result.avg_risk_reward_ratio == 2.0
    assert result.median_risk_reward_ratio == 1.0


def test_zero_trades_no_crash():
    result = BacktestResult()
    result = performance_analytics.calculate(
        result, _snapshots([100000.0]), 100000.0, [], candles_analyzed=10,
    )
    assert result.expectancy == 0.0
    assert result.avg_risk_reward_ratio == 0.0
    assert result.weekday_distribution == {}


def test_weekday_and_hour_distributions():
    result = BacktestResult()
    trades = [
        _trade(100, "2026-01-05T09:15:00+00:00"),   # Monday 09
        _trade(-50, "2026-01-06T14:45:00+00:00"),   # Tuesday 14
        _trade(25, "2026-01-07T09:15:00+00:00"),    # Wednesday 09
    ]
    result = performance_analytics.calculate(
        result, _snapshots([100000.0]), 100000.0, trades, candles_analyzed=10,
    )
    assert result.weekday_distribution["MON"] == 100.0
    assert result.weekday_distribution["TUE"] == -50.0
    assert result.weekday_distribution["WED"] == 25.0
    assert result.hour_distribution["09"] == 125.0
    assert result.hour_distribution["14"] == -50.0
    assert result.month_distribution["2026-01"] == 75.0


def test_benchmark_beta_alpha_and_excess():
    candles = _candles(n=100, base=100.0, step=1.0)  # 100 → 199
    equities = [100000.0 * (1 + i * 1.0 / 100.0) for i in range(100)]  # mirrors benchmark
    result = BacktestResult()
    result = performance_analytics.calculate(
        result, _snapshots(equities), 100000.0, [], candles_analyzed=100,
        benchmark_candles=candles,
    )
    assert result.benchmark_return_pct == pytest.approx(99.0)
    assert result.excess_return_pct == pytest.approx(0.0, abs=0.1)
    assert result.beta == pytest.approx(1.0, abs=0.01)
    assert result.alpha == pytest.approx(0.0, abs=0.1)
    assert result.benchmark_max_drawdown_pct == 0.0


def test_benchmark_flat_strategy_has_zero_beta():
    candles = _candles(n=100, base=100.0, step=1.0)
    equities = [100000.0] * 100
    result = BacktestResult()
    result = performance_analytics.calculate(
        result, _snapshots(equities), 100000.0, [], candles_analyzed=100,
        benchmark_candles=candles,
    )
    assert result.benchmark_return_pct == pytest.approx(99.0)
    assert result.beta == 0.0
    assert result.excess_return_pct == pytest.approx(-99.0)
