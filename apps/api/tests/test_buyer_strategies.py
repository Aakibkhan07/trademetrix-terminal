"""Unit tests for options-buying strategies base and B1 Momentum Breakout Buyer."""
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from strategies.buyer_base import BuyerConfig, Phase


def _make_candle(open_, high, low, close, volume, ts=None):
    from core.models import Candle, Exchange
    return Candle(
        symbol="NIFTY", exchange=Exchange.NSE, interval="5m",
        open=open_, high=high, low=low, close=close,
        volume=volume, timestamp=ts or datetime(2026, 7, 7, 9, 20),
    )


@pytest.fixture(autouse=True)
def _patch_all_deps():
    """Patch all external deps for EVERY test in this module."""
    with (patch("strategies.buyer_base.cache") as c,
          patch("strategies.buyer_base.gate_execute_order") as g,
          patch("strategies.buyer_base.RiskGuard")):
        c.get = AsyncMock(return_value=None)
        c.set = AsyncMock(return_value=True)
        g.return_value = MagicMock(success=True, status="filled")
        yield


@pytest.fixture(autouse=True)
def _patch_instrument_service():
    """Make instrument_service methods controllable."""
    from market.instrument_service import instrument_service
    instrument_service.iv_percentile = MagicMock(return_value=None)
    instrument_service.nearest_weekly_expiry = AsyncMock(return_value="07JUL2026")
    instrument_service.option_ltp = AsyncMock(return_value=105.0)
    instrument_service.option_symbol = MagicMock(
        side_effect=lambda idx, exp, strike, opt: f"NSE:{idx}26JUL{int(strike)}{opt}"
    )
    instrument_service.lot_size = MagicMock(return_value=65)
    instrument_service.strike_step = MagicMock(return_value=50)
    yield


class TestBuyerConfig:
    def test_from_dict_uses_only_valid_fields(self):
        d = {"strategy_id": "s1", "user_id": "u1", "index": "SENSEX",
             "capital": 100000, "sl_pct": 25.0, "bogus": "ignored"}
        bc = BuyerConfig.from_dict(d)
        assert bc.strategy_id == "s1"
        assert bc.user_id == "u1"
        assert bc.index == "SENSEX"
        assert bc.capital == 100000
        assert bc.sl_pct == 25.0

    def test_defaults(self):
        bc = BuyerConfig()
        assert bc.index == "NIFTY"
        assert bc.capital == 0.0
        assert bc.risk_per_trade_pct == 1.0
        assert bc.max_outlay_pct == 10.0
        assert bc.rr_target == 1.5
        assert bc.time_stop_min == 30


class _ConcreteBuyer:
    """Concrete subclass for testing abstract BuyerBase methods."""

    @staticmethod
    def make(config=None):
        from strategies.buyer_base import BuyerBase as BB

        class _T(BB):
            name = "test"
            description = "test"
            async def on_candle(self, candle):
                return None

        b = _T(config or {
            "strategy_id": "b1", "user_id": "u1",
            "capital": 500000, "risk_per_trade_pct": 1.0,
        })
        b.lot_size = 65
        b.step = 50
        return b


@pytest.mark.asyncio
class TestBuyerBase:
    @pytest.fixture
    def buyer(self):
        return _ConcreteBuyer.make()

    async def test_premium_size(self, buyer):
        lots, qty, r = buyer._premium_size(
            entry_premium=100.0, sl_premium=70.0, lot_size=65,
        )
        # risk_amt = 500000 * 0.01 = 5000
        # risk_per_lot = 30 * 65 = 1950
        # lots = floor(5000 / 1950) = 2
        assert lots == 2
        assert qty == 130
        assert r == 30.0

    async def test_premium_size_outlay_cap(self, buyer):
        buyer.bc.capital = 100000
        buyer.bc.risk_per_trade_pct = 50.0
        lots, qty, r = buyer._premium_size(
            entry_premium=100.0, sl_premium=70.0, lot_size=65,
        )
        assert lots > 0
        assert qty * 100.0 <= 100000 * 0.10

    async def test_premium_size_zero_risk(self, buyer):
        lots, qty, r = buyer._premium_size(100.0, 100.0, 65)
        assert lots == 0

    async def test_resolve_strike_atm(self, buyer):
        assert await buyer._resolve_strike(24650.0, "CE") == 24650.0

    async def test_resolve_strike_itm_ce(self, buyer):
        buyer.bc.itm_offset_steps = 1
        assert await buyer._resolve_strike(24650.0, "CE") == 24600.0

    async def test_resolve_strike_itm_pe(self, buyer):
        buyer.bc.itm_offset_steps = 1
        assert await buyer._resolve_strike(24650.0, "PE") == 24700.0

    async def test_phase_initial(self, buyer):
        assert buyer.phase == Phase.BUILDING_OR

    async def test_theta_time_stop_not_before_window(self, buyer):
        buyer.pos = {
            "entry_ts": datetime(2026, 7, 7, 9, 35),
            "r": 30.0, "entry": 100.0,
        }
        buyer._current_premium = 90.0
        bar = _make_candle(0, 0, 0, 0, 0, ts=datetime(2026, 7, 7, 9, 50))
        assert not buyer._check_theta_time_stop(bar)

    async def test_theta_time_stop_after_window_no_progress(self, buyer):
        buyer.pos = {
            "entry_ts": datetime(2026, 7, 7, 9, 35),
            "r": 30.0, "entry": 100.0,
        }
        buyer._current_premium = 90.0
        bar = _make_candle(0, 0, 0, 0, 0, ts=datetime(2026, 7, 7, 10, 10))
        assert buyer._check_theta_time_stop(bar)

    async def test_theta_time_stop_not_with_progress(self, buyer):
        buyer.pos = {
            "entry_ts": datetime(2026, 7, 7, 9, 35),
            "r": 30.0, "entry": 100.0,
        }
        buyer._current_premium = 120.0
        bar = _make_candle(0, 0, 0, 0, 0, ts=datetime(2026, 7, 7, 10, 10))
        assert not buyer._check_theta_time_stop(bar)

    async def test_structure_invalidation_ce_below_or(self, buyer):
        buyer.or_high = 24700.0
        buyer.pos = {"cepe": "CE", "be_armed": False}
        bar = _make_candle(0, 0, 0, 24650.0, 0)
        assert buyer._check_structure_invalidation(bar)

    async def test_structure_invalidation_not_ce_above(self, buyer):
        buyer.or_high = 24700.0
        buyer.pos = {"cepe": "CE", "be_armed": False}
        bar = _make_candle(0, 0, 0, 24750.0, 0)
        assert not buyer._check_structure_invalidation(bar)

    async def test_structure_invalidation_skipped_when_armed(self, buyer):
        buyer.or_high = 24700.0
        buyer.pos = {"cepe": "CE", "be_armed": True}
        bar = _make_candle(0, 0, 0, 24650.0, 0)
        assert not buyer._check_structure_invalidation(bar)

    async def test_trail_breakeven_arms(self, buyer):
        buyer.pos = {
            "entry": 100.0, "r": 30.0, "be_armed": False,
            "sl": 70.0, "peak": 100.0,
        }
        buyer._update_trail(135.0)
        assert buyer.pos["be_armed"]
        # Breakeven moves sl to entry(100), then peak becomes 135
        # so trail = 135 * 0.75 = 101.25 (conservative wins)
        assert buyer.pos["sl"] == 101.25

    async def test_trail_peak_giveback(self, buyer):
        buyer.pos = {
            "entry": 100.0, "r": 30.0, "be_armed": True,
            "sl": 100.0, "peak": 200.0,
        }
        buyer._update_trail(180.0)
        assert buyer.pos["sl"] == 150.0

    async def test_iv_gate_skips_high(self, buyer):
        from market.instrument_service import instrument_service
        instrument_service.iv_percentile = MagicMock(return_value=90.0)
        assert await buyer._check_iv_gate()

    async def test_iv_gate_passes_low(self, buyer):
        from market.instrument_service import instrument_service
        instrument_service.iv_percentile = MagicMock(return_value=30.0)
        assert not await buyer._check_iv_gate()

    async def test_iv_gate_passes_none(self, buyer):
        assert not await buyer._check_iv_gate()

    async def test_to_state(self, buyer):
        buyer.phase = Phase.IN_TRADE
        buyer.or_high = 24700.0
        buyer.or_low = 24400.0
        buyer.vols = [100000, 110000]
        buyer.trades_today = 1
        buyer.traded_dirs = {"CE"}
        buyer.lot_size = 65
        buyer.step = 50
        buyer.pos = {"symbol": "X"}
        s = buyer.to_state()
        assert s["phase"] == "in_trade"
        assert s["trades_today"] == 1
        assert s["traded_dirs"] == ["CE"]

    async def test_from_state(self, buyer):
        buyer.from_state({
            "phase": "in_trade", "or_high": 24700.0, "or_low": 24400.0,
            "vols": [100000], "trades_today": 1, "traded_dirs": ["CE"],
            "lot_size": 65, "step": 50,
            "pos": {"symbol": "X"},
        })
        assert buyer.phase == Phase.IN_TRADE
        assert buyer.trades_today == 1
        assert buyer.traded_dirs == {"CE"}


@pytest.mark.asyncio
class TestMomentumBreakoutBuyer:
    @pytest.fixture
    def strategy(self):
        from strategies.momentum_buyer import MomentumBreakoutBuyer
        s = MomentumBreakoutBuyer({
            "strategy_id": "m1", "user_id": "u1", "capital": 500000,
        })
        s.lot_size = 65
        s.step = 50
        s.phase = Phase.BUILDING_OR
        return s

    async def test_initial_phase(self, strategy):
        assert strategy.phase == Phase.BUILDING_OR

    async def test_build_or_tracks_hl(self, strategy):
        bar = _make_candle(24500, 24700, 24400, 24650, 100000,
                           ts=datetime(2026, 7, 7, 9, 20))
        strategy._build_or(bar, time(9, 20))
        assert strategy.or_high == 24700.0
        assert strategy.or_low == 24400.0

    async def test_build_or_transitions(self, strategy):
        strategy.or_high = 24700.0
        strategy.or_low = 24400.0
        bar = _make_candle(0, 0, 0, 0, 0, ts=datetime(2026, 7, 7, 9, 35))
        strategy._build_or(bar, time(9, 35))
        assert strategy.phase == Phase.ARMED

    async def test_entry_sets_position(self, strategy):
        strategy.phase = Phase.ARMED
        strategy.vols = [100000] * 20
        await strategy._enter("CE", 24800.0)
        assert strategy.trades_today == 1
        assert "CE" in strategy.traded_dirs
        assert strategy.phase == Phase.IN_TRADE
        assert strategy.pos is not None
        assert strategy.pos["entry"] == 105.0
        assert strategy.pos["sl"] == 73.5

    async def test_entry_skipped_high_iv(self, strategy):
        from market.instrument_service import instrument_service
        instrument_service.iv_percentile = MagicMock(return_value=90.0)
        await strategy._enter("CE", 24800.0)
        assert strategy.trades_today == 0

    async def test_entry_skipped_zero_ltp(self, strategy):
        from market.instrument_service import instrument_service
        instrument_service.option_ltp = AsyncMock(return_value=0.0)
        await strategy._enter("CE", 24800.0)
        assert strategy.trades_today == 0

    async def test_flatten_clears(self, strategy):
        strategy.pos = {"symbol": "X", "qty": 65, "r": 30.0}
        strategy.phase = Phase.IN_TRADE
        strategy.trades_today = 1
        with patch.object(strategy.__class__, "_place_order", new=AsyncMock()):
            await strategy._flatten("stop_loss")
        assert strategy.pos is None
        assert strategy.phase == Phase.ARMED

    async def test_flatten_squareoff_done(self, strategy):
        strategy.pos = {"symbol": "X", "qty": 65, "r": 30.0}
        strategy.phase = Phase.IN_TRADE
        with patch.object(strategy.__class__, "_place_order", new=AsyncMock()):
            await strategy._flatten("square_off")
        assert strategy.phase == Phase.DONE

    async def test_max_trades_blocked(self, strategy):
        strategy.phase = Phase.ARMED
        strategy.trades_today = 2
        bar = _make_candle(24600, 24800, 24550, 24800, 200000,
                           ts=datetime(2026, 7, 7, 10, 0))
        await strategy._check_entry(bar)
        assert strategy.trades_today == 2
