"""Sprint 1 (W1) parity tests — canonical Sharpe + cost model.

Guards the unification work:
  1. The legacy engine (engine/backtest.py) and the canonical analytics path
     (backtest/performance.py) must produce the SAME Sharpe ratio for the
     same equity curve (B1 fix: sample stdev, sqrt(252), equity period
     returns).
  2. The legacy engine's fee math must be exactly the canonical
     estimate_round_trip model (B2 fix), with the old flat-math divergence
     precisely documented.
  3. The paper fill engine must produce identical fills through
     estimate_cost.
"""
import math

import pytest

from backtest.costs import (
    BacktestCostConfig,
    CostSegment,
    estimate_cost,
    estimate_round_trip,
    segment_for,
)
from backtest.performance import PerformanceAnalytics, compute_sharpe_ratio
from backtest.models import BacktestResult as AnalyticsResult, EquityPoint
from core.models import Exchange, InstrumentType, NormalizedOrder, OrderSide, OrderType, ProductType
from engine.backtest import BacktestResult as LegacyResult
from paper.fill_engine import FillEngine
from paper.models import PaperConfig


def _sample_stdev(returns: list[float]) -> float:
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance)


def _population_stdev(returns: list[float]) -> float:
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    return math.sqrt(variance)


def _order(side: OrderSide, symbol: str = "NSE:NIFTY50-INDEX") -> NormalizedOrder:
    return NormalizedOrder(
        symbol=symbol,
        exchange=Exchange.NSE,
        side=side,
        order_type=OrderType.MARKET,
        product=ProductType.INTRADAY,
        quantity=10,
        instrument_type=InstrumentType.EQ,
    )


class TestSharpeParity:
    """B1 — one Sharpe definition across every backtest path."""

    EQUITY_SERIES = [100000.0, 100500.0, 100200.0, 101400.0, 100900.0, 102100.0, 101800.0, 102600.0]

    def test_legacy_engine_sharpe_matches_canonical_formula(self):
        result = LegacyResult()
        for i, eq in enumerate(self.EQUITY_SERIES):
            result.update_equity(eq, f"2026-01-{i + 1:02d}T09:15:00")
        result.finalize(100000.0)

        returns = [
            (self.EQUITY_SERIES[i] - self.EQUITY_SERIES[i - 1]) / self.EQUITY_SERIES[i - 1]
            for i in range(1, len(self.EQUITY_SERIES))
        ]
        expected = round((sum(returns) / len(returns)) / _sample_stdev(returns) * math.sqrt(252), 2)
        assert result.sharpe_ratio == pytest.approx(expected)
        assert result.sharpe_ratio == compute_sharpe_ratio(returns)

    def test_canonical_sharpe_uses_sample_not_population_stdev(self):
        returns = [0.10, 0.05, -0.08, 0.12, -0.03, 0.06, 0.02, -0.01, 0.07, 0.04]
        mean = sum(returns) / len(returns)
        population_sharpe = round((mean / _population_stdev(returns)) * math.sqrt(252), 2)
        canonical = compute_sharpe_ratio(returns)
        assert canonical != population_sharpe
        assert canonical == pytest.approx(
            round((mean / _sample_stdev(returns)) * math.sqrt(252), 2)
        )

    def test_legacy_engine_matches_performance_analytics_on_same_equity_curve(self):
        legacy = LegacyResult()
        points = []
        for i, eq in enumerate(self.EQUITY_SERIES):
            ts = f"2026-01-{i + 1:02d}T09:15:00+00:00"
            legacy.update_equity(eq, ts)
            points.append(EquityPoint(timestamp=ts, equity=round(eq, 2)))

        analytics = AnalyticsResult()
        PerformanceAnalytics().calculate(
            analytics, snapshots=[], initial_capital=100000.0,
            trades=[], candles_analyzed=len(points),
        )
        analytics.equity_curve = points
        PerformanceAnalytics()._compute_ratios(analytics)

        legacy.finalize(100000.0)
        assert legacy.sharpe_ratio == pytest.approx(analytics.sharpe_ratio)

    def test_sharpe_guard_returns_zero_with_single_equity_point(self):
        result = LegacyResult()
        result.update_equity(100000.0, "2026-01-01T09:15:00")
        result.finalize(100000.0)
        assert result.sharpe_ratio == 0.0


class TestCostParity:
    """B2 — legacy /run fees == canonical estimate_round_trip."""

    def test_legacy_apply_costs_equals_canonical_round_trip(self):
        result = LegacyResult(slippage_pct=0.05, brokerage_pct=0.03, stt_pct=0.025, exchange_pct=0.003)
        total, brk_plus_exch = result._apply_costs("BUY", 100.0, 110.0, 10)

        cfg = BacktestCostConfig(
            commission_pct=0.03,
            commission_min=0.0,
            stt_pct_override=0.025,
            exchange_tc_pct_override=0.003,
        )
        est = estimate_round_trip(
            side="BUY",
            entry_value=1000.0,
            exit_value=1100.0,
            segment=CostSegment.EQUITY_INTRADAY,
            qty=10,
            slippage_entry=1000.0 * 0.05 / 100,
            slippage_exit=1100.0 * 0.05 / 100,
            config=cfg,
        )
        assert total == pytest.approx(est.total)
        assert brk_plus_exch == pytest.approx(est.brokerage + est.exchange_tc)

    def test_legacy_fee_now_includes_stamp_gst_sebi(self):
        """The old flat math was slippage+brokerage+stt+exchange only; the
        canonical model adds stamp duty (buy leg), GST and SEBI. Assert the
        new total is exactly the old flat total plus those components."""
        result = LegacyResult(slippage_pct=0.05, brokerage_pct=0.03, stt_pct=0.025, exchange_pct=0.003)
        total, _ = result._apply_costs("BUY", 100.0, 110.0, 10)

        slippage = 1000.0 * 0.05 / 100 + 1100.0 * 0.05 / 100
        brokerage = 1000.0 * 0.03 / 100 + 1100.0 * 0.03 / 100
        exchange = 1000.0 * 0.003 / 100 + 1100.0 * 0.003 / 100
        stt = 1000.0 * 0.025 / 100 + 1100.0 * 0.025 / 100
        stamp = 1000.0 * 0.003 / 100  # buy leg only
        gst = (brokerage + exchange) * 18 / 100
        sebi = 2100.0 / 100_000_000 * 10
        old_flat_total = slippage + brokerage + stt + exchange
        assert total == pytest.approx(round(old_flat_total + stamp + gst + sebi, 2))

    def test_legacy_sell_side_has_stamp_only_on_buy_leg(self):
        result = LegacyResult(slippage_pct=0.05, brokerage_pct=0.03, stt_pct=0.025, exchange_pct=0.003)
        cfg = BacktestCostConfig(
            commission_pct=0.03, commission_min=0.0,
            stt_pct_override=0.025, exchange_tc_pct_override=0.003,
        )
        buy_trip, _ = result._apply_costs("BUY", 100.0, 110.0, 10)
        sell_trip, _ = result._apply_costs("SELL", 100.0, 110.0, 10)
        est_buy = estimate_round_trip(
            side="BUY", entry_value=1000.0, exit_value=1100.0,
            segment=CostSegment.EQUITY_INTRADAY, qty=10,
            slippage_entry=1000.0 * 0.05 / 100, slippage_exit=1100.0 * 0.05 / 100,
            config=cfg,
        )
        est_sell = estimate_round_trip(
            side="SELL", entry_value=1000.0, exit_value=1100.0,
            segment=CostSegment.EQUITY_INTRADAY, qty=10,
            slippage_entry=1000.0 * 0.05 / 100, slippage_exit=1100.0 * 0.05 / 100,
            config=cfg,
        )
        assert buy_trip == pytest.approx(est_buy.total)
        assert sell_trip == pytest.approx(est_sell.total)
        # Stamp duty is buy-side only, and the leg it lands on depends on the trip:
        # BUY → entry leg (1000), SELL → exit leg (1100).
        assert est_buy.stamp_duty == pytest.approx(round(1000.0 * 0.003 / 100, 2))
        assert est_sell.stamp_duty == pytest.approx(round(1100.0 * 0.003 / 100, 2))


class TestPaperFillParity:
    """Paper fills through estimate_cost — identical to the old flat math."""

    def test_zero_fee_default_net_equals_gross(self):
        engine = FillEngine(PaperConfig())
        fill = engine._build_fill(_order(OrderSide.BUY), 10, 100.0)
        assert fill.net_amount == pytest.approx(1000.0)
        assert fill.commission == 0.0
        assert fill.exchange_charges == 0.0
        assert fill.stt == 0.0
        assert fill.stamp_duty == 0.0

    def test_fee_components_match_canonical_estimate(self):
        config = PaperConfig(
            commission_pct=0.05, exchange_charges_pct=0.01,
            stt_pct=0.01, stamp_duty_pct=0.003,
        )
        engine = FillEngine(config)
        fill = engine._build_fill(_order(OrderSide.BUY), 10, 100.0)

        cfg = BacktestCostConfig(
            commission_pct=0.05, commission_min=0.0,
            stt_pct_override=0.01, exchange_tc_pct_override=0.01,
            stamp_duty_pct_override=0.003,
            gst_enabled=False, sebi_fees_enabled=False,
        )
        est = estimate_cost(
            side="BUY", traded_value=1000.0,
            segment=segment_for("EQ"), qty=10, price=100.0,
            slippage_value=0.0, config=cfg,
        )
        assert fill.commission == pytest.approx(est.brokerage)
        assert fill.exchange_charges == pytest.approx(est.exchange_tc)
        assert fill.stt == pytest.approx(est.stt)
        assert fill.stamp_duty == pytest.approx(est.stamp_duty)
        assert fill.net_amount == pytest.approx(round(1000.0 + est.total, 2))

    def test_sell_fill_has_no_stamp_duty(self):
        config = PaperConfig(
            commission_pct=0.05, exchange_charges_pct=0.01,
            stt_pct=0.01, stamp_duty_pct=0.003,
        )
        engine = FillEngine(config)
        fill = engine._build_fill(_order(OrderSide.SELL), 10, 100.0)
        cfg = BacktestCostConfig(
            commission_pct=0.05, commission_min=0.0,
            stt_pct_override=0.01, exchange_tc_pct_override=0.01,
            stamp_duty_pct_override=0.003,
            gst_enabled=False, sebi_fees_enabled=False,
        )
        est = estimate_cost(
            side="SELL", traded_value=1000.0,
            segment=segment_for("EQ"), qty=10, price=100.0,
            slippage_value=0.0, config=cfg,
        )
        assert fill.stamp_duty == 0.0
        assert fill.net_amount == pytest.approx(round(1000.0 - est.total, 2))
