import pytest

from backtest.manager import backtest_manager
from backtest.models import BacktestResult, BacktestStatus, TradeRecord
from backtest.optimizer import OptimizationSpec, backtest_optimizer


def _fake_result(net_pnl=100.0, trades=5, candles=300):
    r = BacktestResult(
        status=BacktestStatus.COMPLETED,
        start_equity=100000.0,
        end_equity=100000.0 + net_pnl,
        net_pnl=net_pnl,
        return_pct=net_pnl / 1000,
        total_trades=trades,
        win_rate=60.0,
        profit_factor=1.5,
        max_drawdown_pct=5.0,
        sharpe_ratio=1.2,
        sortino_ratio=1.5,
        calmar_ratio=0.8,
        expectancy=net_pnl / max(1, trades),
        candles_analyzed=candles,
    )
    r.trades = [TradeRecord(
        symbol="NIFTY", side="BUY", entry_price=100, exit_price=101,
        quantity=1, pnl=net_pnl / max(1, trades) / 2,
        entry_time="2026-01-05T10:00:00+00:00",
        exit_time="2026-01-05T10:15:00+00:00",
    ) for _ in range(trades)]
    return r


@pytest.mark.asyncio
async def test_grid_search_best_params(monkeypatch):
    seen = []

    async def fake_fast_run(config):
        seen.append(dict(config.strategy_params))
        net = config.strategy_params.get("fast_period", 1) * 10
        return _fake_result(net_pnl=net)

    monkeypatch.setattr(backtest_manager, "_fast_run", fake_fast_run)

    out = await backtest_optimizer.run(OptimizationSpec(
        strategy_type="trend_rider",
        method="grid",
        param_ranges={"fast_period": [5, 10], "slow_period": [13, 26]},
    ))
    assert out.status == "COMPLETED"
    assert out.combos_total == 4
    assert out.combos_completed == 4
    assert len(out.results) == 4
    assert out.best["params"] == {"fast_period": 10, "slow_period": 13}
    assert out.best["metrics"]["net_pnl"] == 100.0


@pytest.mark.asyncio
async def test_grid_too_many_combos_fails(monkeypatch):
    async def fake_fast_run(config):
        return _fake_result()

    monkeypatch.setattr(backtest_manager, "_fast_run", fake_fast_run)

    out = await backtest_optimizer.run(OptimizationSpec(
        strategy_type="trend_rider",
        method="grid",
        param_ranges={"a": [1, 2, 3, 4, 5], "b": [1, 2, 3, 4, 5], "c": [1, 2, 3, 4, 5]},
        max_combos=10,
    ))
    assert out.status == "FAILED"
    assert "Too many" in out.error


@pytest.mark.asyncio
async def test_walk_forward_windows(monkeypatch):
    async def fake_fast_run(config):
        if config.candle_slice:
            return _fake_result(net_pnl=50.0, candles=config.candle_slice[1] - config.candle_slice[0])
        return _fake_result(candles=120)

    monkeypatch.setattr(backtest_manager, "_fast_run", fake_fast_run)

    out = await backtest_optimizer.run(OptimizationSpec(
        strategy_type="trend_rider",
        method="walk_forward",
        windows=6,
        param_ranges={"fast_period": [5, 10]},
    ))
    assert out.status == "COMPLETED"
    assert out.combos_total == 6
    assert len(out.results) == 6
    assert all("window" in r.params for r in out.results)
    assert out.best["metrics"]["net_pnl"] == 50.0


@pytest.mark.asyncio
async def test_monte_carlo_distribution(monkeypatch):
    async def fake_fast_run(config):
        return _fake_result(net_pnl=100.0, trades=20)

    monkeypatch.setattr(backtest_manager, "_fast_run", fake_fast_run)

    out = await backtest_optimizer.run(OptimizationSpec(
        strategy_type="trend_rider",
        method="monte_carlo",
        mc_paths=500,
        seed=1,
    ))
    assert out.status == "COMPLETED"
    d = out.distribution
    for key in ("p5", "p25", "p50", "p75", "p95", "mean", "probability_of_profit_pct", "paths"):
        assert key in d
    assert d["paths"] == 500
    assert 0 <= d["probability_of_profit_pct"] <= 100


@pytest.mark.asyncio
async def test_sensitivity_ofat(monkeypatch):
    async def fake_fast_run(config):
        fp = config.strategy_params.get("fast_period", 5)
        return _fake_result(net_pnl=fp)

    monkeypatch.setattr(backtest_manager, "_fast_run", fake_fast_run)

    out = await backtest_optimizer.run(OptimizationSpec(
        strategy_type="trend_rider",
        method="sensitivity",
        strategy_params={"fast_period": 5},
        param_ranges={"fast_period": [5]},
    ))
    assert out.status == "COMPLETED"
    assert out.combos_total == 3
    factors = {r.params.get("factor") for r in out.results if "factor" in r.params}
    assert factors == {0.8, 1.2}
    assert out.results[0].params == {}


@pytest.mark.asyncio
async def test_optimize_route_and_status(client, auth_headers, monkeypatch):
    async def fake_fast_run(config):
        return _fake_result(net_pnl=42.0)

    monkeypatch.setattr(backtest_manager, "_fast_run", fake_fast_run)

    resp = await client.post(
        "/api/v1/backtests/optimize",
        json={
            "strategy_type": "trend_rider",
            "method": "grid",
            "param_ranges": {"fast_period": [5]},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["combos_total"] == 1

    run_id = data["run_id"]
    status_resp = await client.get(f"/api/v1/backtests/optimize/{run_id}", headers=auth_headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["run_id"] == run_id


@pytest.mark.asyncio
async def test_optimize_route_unauth_403_csrf(client):
    resp = await client.post("/api/v1/backtests/optimize", json={})
    assert resp.status_code == 403
