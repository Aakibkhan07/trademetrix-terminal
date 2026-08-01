"""Unit tests for the Indian cost model (backtest/costs.py)."""
import pytest

from backtest.costs import (
    BacktestCostConfig,
    CostSegment,
    estimate_cost,
    estimate_round_trip,
    segment_for,
)


def test_segment_mapping():
    assert segment_for("EQ") == CostSegment.EQUITY_INTRADAY
    assert segment_for("EQ", "DELIVERY") == CostSegment.EQUITY_DELIVERY
    assert segment_for("FUT") == CostSegment.FUTURES
    assert segment_for("OPT") == CostSegment.OPTIONS
    assert segment_for("CE") == CostSegment.OPTIONS


def test_equity_delivery_sell_pays_stt_buy_does_not():
    sell = estimate_cost("SELL", 100_000, CostSegment.EQUITY_DELIVERY)
    buy = estimate_cost("BUY", 100_000, CostSegment.EQUITY_DELIVERY)
    assert sell.stt == pytest.approx(100.0)  # 0.1% of 100k
    assert buy.stt == 0.0
    # stamp duty buy side only
    assert buy.stamp_duty == pytest.approx(15.0)  # 0.015%
    assert sell.stamp_duty == 0.0


def test_equity_intraday_both_sides_stt():
    buy = estimate_cost("BUY", 100_000, CostSegment.EQUITY_INTRADAY)
    sell = estimate_cost("SELL", 100_000, CostSegment.EQUITY_INTRADAY)
    assert buy.stt == pytest.approx(25.0)   # 0.025%
    assert sell.stt == pytest.approx(25.0)


def test_futures_stt_sell_only():
    sell = estimate_cost("SELL", 100_000, CostSegment.FUTURES)
    buy = estimate_cost("BUY", 100_000, CostSegment.FUTURES)
    assert sell.stt == pytest.approx(12.5)  # 0.0125%
    assert buy.stt == 0.0


def test_options_brokerage_is_flat():
    small = estimate_cost("BUY", 10_000, CostSegment.OPTIONS)
    large = estimate_cost("BUY", 500_000, CostSegment.OPTIONS)
    assert small.brokerage == 20.0
    assert large.brokerage == 20.0


def test_brokerage_minimum_applies():
    small = estimate_cost("BUY", 5_000, CostSegment.EQUITY_INTRADAY)  # 0.03% = 1.5 → min 20
    assert small.brokerage == 20.0
    large = estimate_cost("BUY", 1_000_000, CostSegment.EQUITY_INTRADAY)  # 0.03% = 300
    assert large.brokerage == pytest.approx(300.0)


def test_slippage_included_in_total():
    c = estimate_cost("BUY", 100_000, CostSegment.FUTURES, slippage_value=75.0)
    assert c.slippage == 75.0
    assert c.total == pytest.approx(75.0 + c.brokerage + c.exchange_tc + c.stamp_duty + c.gst + c.sebi)


def test_all_charges_disabled():
    cfg = BacktestCostConfig(
        stt_enabled=False, exchange_charges_enabled=False, stamp_duty_enabled=False,
        gst_enabled=False, sebi_fees_enabled=False,
    )
    c = estimate_cost("BUY", 100_000, CostSegment.OPTIONS, config=cfg)
    assert c.stt == 0.0
    assert c.exchange_tc == 0.0
    assert c.stamp_duty == 0.0
    assert c.gst == 0.0
    assert c.sebi == 0.0
    assert c.total == pytest.approx(c.brokerage)  # only flat options brokerage


def test_round_trip_totals_both_legs():
    rt = estimate_round_trip(
        "BUY", 100_000, 105_000, CostSegment.EQUITY_INTRADAY,
    )
    assert rt.total == pytest.approx(
        rt.brokerage + rt.exchange_tc + rt.stt + rt.stamp_duty + rt.gst + rt.sebi
    )
    assert rt.stt == pytest.approx(25.0 + 26.25)  # both legs 0.025%


def test_options_premium_never_negative():
    c = estimate_cost("SELL", 500, CostSegment.OPTIONS)
    assert c.total > 0
    assert c.stt > 0  # 0.1% on premium
