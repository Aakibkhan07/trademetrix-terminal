import pytest

from backtest.execution import BacktestBroker, BacktestExecutionConfig, BacktestFillEngine
from core.models import Exchange, NormalizedOrder, OrderSide, OrderType, ProductType


def _candle(ts, open_, high, low, close, symbol="NIFTY"):
    return {
        "symbol": symbol,
        "exchange": "NSE",
        "interval": "15m",
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000,
        "timestamp": ts,
        "oi": 0,
    }


def _order(side="BUY", order_type="MARKET", qty=10, price=0.0, trigger=None, symbol="NIFTY"):
    return NormalizedOrder(
        symbol=symbol,
        exchange=Exchange.NSE,
        side=OrderSide(side),
        order_type=OrderType(order_type),
        product=ProductType.INTRADAY,
        quantity=qty,
        price=price,
        trigger_price=trigger,
    )


def _engine(candles, latency=0, slippage=0.0, seed=42, partial=0.0):
    config = BacktestExecutionConfig(
        slippage_pct=slippage, latency_candles=latency, seed=seed,
        partial_fill_probability=partial,
    )
    engine = BacktestFillEngine(config)
    engine.set_candles(candles)
    return engine


# ── Fill engine ──

def test_market_fill_at_close_with_slippage():
    candles = [_candle("t0", 100, 101, 99, 100), _candle("t1", 101, 102, 100, 101)]
    engine = _engine(candles, slippage=1.0)
    engine.set_index(1)
    buy = engine.simulate_fill(_order("BUY"))
    assert buy.status == "filled"
    assert buy.quantity == 10
    assert buy.price == pytest.approx(101 * 1.01)
    sell = engine.simulate_fill(_order("SELL"))
    assert sell.price == pytest.approx(101 * 0.99)


def test_latency_defers_fill_to_future_candle():
    candles = [_candle("t0", 100, 101, 99, 100), _candle("t1", 101, 102, 100, 101), _candle("t2", 102, 103, 101, 102)]
    engine = _engine(candles, latency=1)
    engine.set_index(0)
    fill = engine.simulate_fill(_order("BUY"))
    assert fill.price == 101.0


def test_limit_fill_when_candle_trades_through():
    candles = [_candle("t0", 105, 106, 99, 100)]
    engine = _engine(candles)
    engine.set_index(0)
    buy = engine.simulate_fill(_order("BUY", "LIMIT", price=100.5))
    assert buy.status == "filled"
    assert buy.price == 100.5


def test_limit_pending_when_not_breached():
    candles = [_candle("t0", 105, 106, 101, 102)]
    engine = _engine(candles)
    engine.set_index(0)
    fill = engine.simulate_fill(_order("BUY", "LIMIT", price=100.5))
    assert fill.status == "pending"
    assert fill.reason == "limit not breached"


def test_slm_fills_at_trigger_with_slippage():
    candles = [_candle("t0", 100, 104, 98, 101)]
    engine = _engine(candles, slippage=1.0)
    engine.set_index(0)
    sell = engine.simulate_fill(_order("SELL", "SLM", trigger=99))
    assert sell.status == "filled"
    assert sell.price == pytest.approx(99 * 0.99)
    buy = engine.simulate_fill(_order("BUY", "SLM", trigger=102))
    assert buy.status == "filled"
    assert buy.price == pytest.approx(102 * 1.01)


def test_slm_pending_when_trigger_not_breached():
    candles = [_candle("t0", 100, 101, 99, 100)]
    engine = _engine(candles)
    engine.set_index(0)
    fill = engine.simulate_fill(_order("BUY", "SLM", trigger=105))
    assert fill.status == "pending"


def test_sll_requires_trigger_and_limit():
    candles = [_candle("t0", 100, 103, 101.5, 102)]
    engine = _engine(candles)
    engine.set_index(0)
    no_fill = engine.simulate_fill(_order("BUY", "SL", price=101, trigger=102))
    assert no_fill.status == "pending"

    candles2 = [_candle("t0", 100, 103, 100.4, 102)]
    engine2 = _engine(candles2)
    engine2.set_index(0)
    fill = engine2.simulate_fill(_order("BUY", "SL", price=101, trigger=102))
    assert fill.status == "filled"
    assert fill.price == 101.0


def test_partial_fill_probability_deterministic():
    candles = [_candle("t0", 100, 101, 99, 100)]
    engine = _engine(candles, seed=7, partial=1.0)
    engine.set_index(0)
    fill = engine.simulate_fill(_order("BUY", qty=100))
    assert fill.status == "partially_filled"
    assert 0 < fill.quantity < 100

    engine2 = _engine(candles, seed=7, partial=0.0)
    engine2.set_index(0)
    fill2 = engine2.simulate_fill(_order("BUY", qty=100))
    assert fill2.status == "filled"
    assert fill2.quantity == 100


# ── Broker accounting ──

@pytest.mark.asyncio
async def test_broker_round_trip_accounting():
    candles = [
        _candle("t0", 100, 101, 99, 100),
        _candle("t1", 101, 102, 100, 101),
        _candle("t2", 104, 105, 103, 104),
    ]
    broker = BacktestBroker("backtest:test")
    broker.update_config(BacktestExecutionConfig(initial_capital=100000.0))
    broker.set_candles(candles)

    await broker.on_candle(0)
    buy_result = await broker.place_order(_order("BUY", qty=10))
    assert buy_result.success
    assert buy_result.status == "filled"
    assert buy_result.avg_price == 100.0

    await broker.on_candle(1)
    assert broker.equity() == pytest.approx(
        100000.0 - 10 * 100.0 + 10 * (101 - 100) - broker.total_costs
    )

    await broker.on_candle(2)
    sell_result = await broker.place_order(_order("SELL", qty=10))
    assert sell_result.success
    assert broker.positions()["NIFTY"]["quantity"] == 0
    assert broker.realized_pnl == pytest.approx(40.0)
    assert broker.total_costs > 0
    assert broker.equity() == pytest.approx(100000.0 + 40.0 - broker.total_costs)


@pytest.mark.asyncio
async def test_resting_limit_fills_on_later_candle():
    candles = [
        _candle("t0", 100, 101, 101, 100),
        _candle("t1", 100, 101, 99.5, 100.5),
    ]
    broker = BacktestBroker("backtest:test")
    broker.set_candles(candles)

    await broker.on_candle(0)
    result = await broker.place_order(_order("BUY", "LIMIT", qty=5, price=100))
    assert result.status == "pending"

    await broker.on_candle(1)
    pos = broker.positions()["NIFTY"]
    assert pos["quantity"] == 5
    assert pos["avg_price"] == 100.0


@pytest.mark.asyncio
async def test_broker_health_and_funds():
    broker = BacktestBroker("backtest:test")
    await broker.connect()
    health = await broker.health()
    assert health["authenticated"] is True
    assert health["backtest"] is True
    funds = await broker.get_funds()
    assert funds.available_margin == pytest.approx(100000.0)


# ── End-to-end manager run ──

@pytest.mark.asyncio
async def test_manager_run_end_to_end(monkeypatch):
    from backtest.manager import backtest_manager
    from backtest.models import BacktestConfig
    from datetime import UTC, datetime, timedelta

    start = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
    candles = []
    for i in range(300):
        close = 100.0 + i * 0.4 + (i % 5) * 0.1
        ts = (start + timedelta(minutes=15 * i)).isoformat()
        candles.append(_candle(ts, close - 1, close + 1, close - 1, close, "NIFTY"))

    async def fake_load(symbol="NIFTY", exchange="NSE", interval="15m", days=60,
                        user_id=None, source="auto", file_path=""):
        return candles

    monkeypatch.setattr("backtest.manager.backtest_data_loader.load", fake_load)

    result = await backtest_manager.run(BacktestConfig(
        strategy_type="trend_rider",
        symbol="NIFTY",
        interval="15m",
        days=60,
        initial_capital=100000.0,
        speed="MAX",
    ))
    assert result.status.value == "COMPLETED"
    assert result.error == ""
    assert result.candles_analyzed == 300
    assert result.equity_curve
    assert result.end_equity > 0
    assert result.total_trades >= 0
    assert result.duration_seconds >= 0
    backtest_manager._history.clear()
    backtest_manager._current_run = None
