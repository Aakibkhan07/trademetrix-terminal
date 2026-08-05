"""Backtest risk simulation tests.

Covers: simulated rule semantics (mirroring live risk rules), the rejection
payload contract (reason, rule, capital/risk remaining, drawdown, exposure),
position sizing clamp, circuit-breaker halt, analytics shape, and the
risk-on-never-zero / risk-off-parity validation at the manager level.
"""

import pytest

from backtest.execution import BacktestBroker, BacktestExecutionConfig
from backtest.risk import BacktestRiskCheck, BacktestRiskSimulator, NO_LIMIT
from core.models import Exchange, NormalizedOrder, OrderSide, OrderType, ProductType
from risk.models import RiskDecision


def _order(side="BUY", qty=10, price=100.0, symbol="NIFTY"):
    return NormalizedOrder(
        symbol=symbol,
        exchange=Exchange.NSE,
        side=OrderSide(side),
        order_type=OrderType.MARKET,
        product=ProductType.INTRADAY,
        quantity=qty,
        price=price,
    )


class FakeBroker:
    """Minimal duck-typed stand-in for BacktestBroker's risk-read surface."""

    def __init__(self, capital=100000.0):
        self._capital = capital
        self._realized = 0.0
        self._trades: list[dict] = []
        self._positions: dict[str, dict] = {}
        self._last: dict[str, float] = {}

    def equity(self) -> float:
        unreal = 0.0
        for symbol, pos in self._positions.items():
            last = self._last.get(symbol, pos["avg"])
            unreal += (last - pos["avg"]) * pos["qty"]
        return self._capital + self._realized + unreal

    @property
    def cash(self) -> float:
        return self._capital

    @property
    def realized_pnl(self) -> float:
        return self._realized

    @property
    def trades(self) -> list[dict]:
        return self._trades

    def positions(self) -> dict[str, dict]:
        return {
            symbol: {"quantity": pos["qty"], "avg_price": pos["avg"]}
            for symbol, pos in self._positions.items()
        }

    def last_price(self, symbol: str) -> float:
        return self._last.get(symbol, 0.0)

    def last_time(self) -> str:
        return "t0"

    def open_position(self, symbol="NIFTY", qty=10, avg=100.0):
        self._positions[symbol] = {"qty": qty, "avg": avg}
        self._last[symbol] = avg


def _sim(capital=100000.0, overrides=None):
    return BacktestRiskSimulator(capital, overrides)


# ── rule semantics ──

def test_defaults_approve_first_order():
    sim = _sim()
    broker = FakeBroker()
    check = sim.check(broker, _order())
    assert check.decision == RiskDecision.APPROVED
    assert sim.acceptance_count == 1
    assert check.adjusted_quantity is None


def test_max_open_positions_rejects_open_but_allows_reducer():
    sim = _sim(overrides={"max_open_positions": 1})
    broker = FakeBroker()
    broker.open_position("NIFTY", qty=10, avg=100.0)
    assert sim.check(broker, _order("BUY")).decision == RiskDecision.REJECTED
    assert sim.rejections[0].rule == "MAX_OPEN_POSITIONS"
    close = sim.check(broker, _order("SELL", qty=5))
    assert close.decision == RiskDecision.APPROVED


def test_max_quantity_rejects():
    sim = _sim(overrides={"max_quantity": 5})
    check = sim.check(FakeBroker(), _order(qty=10))
    assert check.decision == RiskDecision.REJECTED
    assert check.rule == "MAX_QUANTITY"


def test_max_capital_rejects():
    sim = _sim(overrides={"max_capital": 1000.0})
    check = sim.check(FakeBroker(), _order(qty=20, price=100.0))
    assert check.decision == RiskDecision.REJECTED
    assert check.rule == "MAX_CAPITAL"


def test_max_exposure_rejects_when_post_fill_breaches():
    sim = _sim(overrides={"max_exposure": 1500.0})
    broker = FakeBroker()
    broker.open_position("NIFTY", qty=10, avg=100.0)
    check = sim.check(broker, _order("BUY", qty=10, price=100.0))
    assert check.decision == RiskDecision.REJECTED
    assert check.rule == "MAX_EXPOSURE"
    assert sim.rejections[0].exposure == 1000.0
    close = sim.check(broker, _order("SELL", qty=10))
    assert close.decision == RiskDecision.APPROVED


def test_max_symbol_exposure_rejects_per_symbol():
    sim = _sim(overrides={"max_symbol_exposure": 1500.0})
    broker = FakeBroker()
    broker.open_position("NIFTY", qty=10, avg=100.0)
    check = sim.check(broker, _order("BUY", qty=10, price=100.0))
    assert check.rule == "MAX_SYMBOL_EXPOSURE"
    other = sim.check(broker, _order("BUY", qty=10, price=100.0, symbol="BANKNIFTY"))
    assert other.decision == RiskDecision.APPROVED


def test_max_trades_per_day_rejects():
    sim = _sim(overrides={"max_trades_per_day": 3})
    broker = FakeBroker()
    broker._trades = [{"pnl": 1}, {"pnl": 2}, {"pnl": 3}]
    check = sim.check(broker, _order())
    assert check.decision == RiskDecision.REJECTED
    assert check.rule == "MAX_TRADES_PER_DAY"


def test_daily_loss_limit_rejects_and_engages_circuit_breaker():
    sim = _sim(overrides={"daily_loss_limit": 1000.0})
    broker = FakeBroker()
    broker._realized = -1500.0
    check = sim.check(broker, _order())
    assert check.decision == RiskDecision.REJECTED
    assert check.rule == "DAILY_LOSS_LIMIT"
    assert sim.halted
    blocked = sim.check(broker, _order())
    assert blocked.decision == RiskDecision.REJECTED
    assert blocked.rule == "CIRCUIT_BREAKER"


def test_daily_profit_target_warns_but_allows():
    sim = _sim(overrides={"daily_profit_target": 1000.0})
    broker = FakeBroker()
    broker._realized = 1500.0
    check = sim.check(broker, _order())
    assert check.decision == RiskDecision.APPROVED
    assert sim.warnings


def test_max_drawdown_rejects_and_halts():
    sim = _sim(overrides={"max_drawdown_pct": 10.0, "daily_loss_limit": 0})
    broker = FakeBroker()
    broker._realized = -10000.0
    check = sim.check(broker, _order())
    assert check.decision == RiskDecision.REJECTED
    assert check.rule == "MAX_DRAWDOWN"
    assert sim.halted
    assert sim.rejections[0].drawdown == 10.0


def test_kill_switch_config_rejects():
    sim = _sim(overrides={"kill_switch_enabled": True})
    check = sim.check(FakeBroker(), _order())
    assert check.decision == RiskDecision.REJECTED
    assert check.rule == "KILL_SWITCH"


def test_emergency_stop_config_rejects():
    sim = _sim(overrides={"emergency_stop": True})
    check = sim.check(FakeBroker(), _order())
    assert check.decision == RiskDecision.REJECTED
    assert check.rule == "EMERGENCY_STOP"


# ── position sizing ──

def test_position_sizing_clamps_quantity():
    sim = _sim(overrides={"max_risk_per_trade_pct": 1.0})
    check = sim.check(FakeBroker(), _order(qty=20, price=100.0))
    assert check.decision == RiskDecision.APPROVED
    assert check.adjusted_quantity == 10


def test_position_sizing_skips_reducers():
    sim = _sim(overrides={"max_risk_per_trade_pct": 1.0})
    broker = FakeBroker()
    broker.open_position("NIFTY", qty=10, avg=100.0)
    check = sim.check(broker, _order("SELL", qty=100, price=100.0))
    assert check.decision == RiskDecision.APPROVED
    assert check.adjusted_quantity is None


# ── rejection payload contract ──

def test_rejection_payload_contract():
    sim = _sim(overrides={"max_quantity": 1})
    check = sim.check(FakeBroker(), _order(qty=10, price=100.0))
    assert check.decision == RiskDecision.REJECTED
    rec = sim.rejections[0]
    assert rec.rule == "MAX_QUANTITY"
    assert rec.reason
    assert rec.capital_remaining >= 0
    assert isinstance(rec.risk_remaining, float)
    assert rec.drawdown >= 0
    assert rec.exposure >= 0
    assert rec.symbol == "NIFTY"
    assert rec.quantity == 10


def test_risk_remaining_unlimited_sentinel():
    sim = _sim(overrides={"max_quantity": 1, "daily_loss_limit": 0})
    sim.check(FakeBroker(), _order(qty=10))
    assert sim.rejections[0].risk_remaining == NO_LIMIT


def test_capital_remaining_is_buying_power():
    sim = _sim(overrides={"max_quantity": 1})
    broker = FakeBroker()
    broker.open_position("NIFTY", qty=10, avg=100.0)
    sim.check(broker, _order(qty=10))
    assert sim.rejections[0].capital_remaining == pytest.approx(99000.0)


# ── analytics ──

def test_analytics_shape():
    sim = _sim(overrides={"max_open_positions": 1})
    broker = FakeBroker()
    sim.check(broker, _order())
    broker.open_position("NIFTY", qty=10, avg=100.0)
    sim.check(broker, _order("BUY"))
    sim.snapshot(broker, 0, "t0")
    sim.snapshot(broker, 1, "t1")
    a = sim.analytics()
    assert a.enabled
    assert a.accepted_trades == 1
    assert a.rejected_trades == 1
    assert a.rejection_reasons == {"MAX_OPEN_POSITIONS": 1}
    assert len(a.timeline) == 2
    assert len(a.capital_curve) == 2
    assert len(a.exposure_curve) == 2
    assert a.capital_curve[0].value == pytest.approx(99000.0)
    assert a.exposure_curve[0].value == pytest.approx(1000.0)
    assert a.timeline[1].status == "trading"


def test_analytics_records_halt():
    sim = _sim(overrides={"daily_loss_limit": 1000.0})
    broker = FakeBroker()
    broker._realized = -1500.0
    sim.check(broker, _order())
    sim.snapshot(broker, 0, "t0")
    a = sim.analytics()
    assert a.halt_count == 1
    assert a.timeline[0].status == "halted"


def test_analytics_disabled_by_default():
    from backtest.models import RiskAnalytics

    assert RiskAnalytics().enabled is False


# ── manager integration: risk OFF parity + risk ON never zero ──

def _candles(n=300):
    from datetime import UTC, datetime, timedelta

    start = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
    candles = []
    for i in range(n):
        close = 100.0 + i * 0.4 + (i % 5) * 0.1
        ts = (start + timedelta(minutes=15 * i)).isoformat()
        candles.append({
            "symbol": "NIFTY", "exchange": "NSE", "interval": "15m",
            "open": close - 1, "high": close + 1, "low": close - 1,
            "close": close, "volume": 1000, "timestamp": ts, "oi": 0,
        })
    return candles


async def _run(monkeypatch, config_kwargs):
    from backtest.manager import backtest_manager
    from backtest.models import BacktestConfig

    candles = _candles()

    async def fake_load(symbol="NIFTY", exchange="NSE", interval="15m", days=60,
                        user_id=None, source="auto", file_path=""):
        return candles

    monkeypatch.setattr("backtest.manager.backtest_data_loader.load", fake_load)
    result = await backtest_manager.run(BacktestConfig(**config_kwargs))
    backtest_manager._history.clear()
    backtest_manager._current_run = None
    return result


@pytest.mark.asyncio
async def test_risk_off_has_no_analytics(monkeypatch):
    result = await _run(monkeypatch, {
        "strategy_type": "macd_cross", "symbol": "NIFTY", "interval": "15m",
        "days": 60, "initial_capital": 100000.0, "speed": "MAX",
        "risk_enabled": False,
    })
    assert result.status.value == "COMPLETED"
    assert result.risk_analytics.enabled is False
    assert result.total_trades >= 0


@pytest.mark.asyncio
async def test_risk_on_defaults_never_zero_and_not_above_risk_off(monkeypatch):
    kwargs = {
        "strategy_type": "macd_cross", "symbol": "NIFTY", "interval": "15m",
        "days": 60, "initial_capital": 100000.0, "speed": "MAX",
    }
    off = await _run(monkeypatch, {**kwargs, "risk_enabled": False})
    on = await _run(monkeypatch, {**kwargs, "risk_enabled": True})
    assert on.total_trades >= 1
    assert on.total_trades <= off.total_trades
    assert on.risk_analytics.enabled
    assert on.risk_analytics.accepted_trades >= on.total_trades
    assert on.risk_analytics.timeline


@pytest.mark.asyncio
async def test_risk_on_tight_limits_reduce_trades_and_record_rejections(monkeypatch):
    kwargs = {
        "strategy_type": "macd_cross", "symbol": "NIFTY", "interval": "15m",
        "days": 60, "initial_capital": 100000.0, "speed": "MAX",
    }
    off = await _run(monkeypatch, {**kwargs, "risk_enabled": False})
    on = await _run(monkeypatch, {
        **kwargs, "risk_enabled": True,
        "risk": {"max_trades_per_day": 1},
    })
    assert off.total_trades > 0
    assert on.total_trades <= off.total_trades
    assert on.risk_analytics.rejected_trades > 0
    assert "MAX_TRADES_PER_DAY" in on.risk_analytics.rejection_reasons
    for rec in on.risk_analytics.rejection_reasons.values():
        assert rec > 0


@pytest.mark.asyncio
async def test_replay_speed_path_uses_simulator(monkeypatch):
    from backtest.replay_engine import replay_engine

    async def no_delay(raw: dict, idx: int):
        return None

    monkeypatch.setattr(replay_engine, "_apply_speed_delay", no_delay)
    kwargs = {
        "strategy_type": "macd_cross", "symbol": "NIFTY", "interval": "15m",
        "days": 60, "initial_capital": 100000.0, "speed": "1x",
        "risk_enabled": True, "risk": {"max_trades_per_day": 2},
    }
    result = await _run(monkeypatch, kwargs)
    assert result.status.value == "COMPLETED"
    assert result.risk_analytics.enabled
    assert result.risk_analytics.timeline


# ── broker-level sizing integration ──

@pytest.mark.asyncio
async def test_broker_fills_with_adjusted_quantity():
    candles = [
        {"symbol": "NIFTY", "exchange": "NSE", "interval": "15m",
         "open": 100, "high": 101, "low": 99, "close": 100,
         "volume": 1000, "timestamp": "t0", "oi": 0},
    ]
    broker = BacktestBroker("backtest:test")
    broker.update_config(BacktestExecutionConfig(initial_capital=100000.0))
    broker.set_candles(candles)
    sim = _sim(overrides={"max_risk_per_trade_pct": 1.0})
    await broker.on_candle(0)
    order = _order(qty=20, price=100.0)
    check = sim.check(broker, order)
    assert check.adjusted_quantity == 10
    order.quantity = check.adjusted_quantity
    result = await broker.place_order(order)
    assert result.status == "filled"
    assert result.filled_qty == 10
    assert sim.acceptance_count == 1
