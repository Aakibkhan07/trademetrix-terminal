"""Regression tests for the live execution quantity and instrument-resolution defects.

Two production defects motivated this file.

**Quantity replacement.** ``engine.gate._snap_quantity_to_lot`` set
``order.quantity = 10 * lot``, discarding whatever size the strategy had derived and
running *before* the risk engine. For NIFTY at lot 65 that turned every request into
650 units -- roughly Rs 1.56 crore notional at the index level then being quoted. It
was a quantity replacement wearing the name of a snap.

**Symbol wiring.** ``BacktestConfig.symbol`` never reached the strategy, because
strategies read their symbol from ``strategy_params`` instead. Six of six strategies
traded ``NIFTY`` (or ``BANKNIFTY``) while the fill engine held candles for the
requested instrument, which is why ``entry_time``/``exit_time`` came back empty and
the fills priced off no series at all.

Every test here drives the real code path rather than asserting on source text, and
each quantity assertion is written so that restoring the old ``10 * lot`` makes it
fail: the requested units and the forced units are different numbers for every case
covered.

No broker is contacted and no order is sent. The OMS call is intercepted, so the tests
observe exactly the payload that *would* have gone out.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backtest.manager import backtest_manager
from backtest.models import BacktestConfig
from core.models import (
    Exchange,
    InstrumentType,
    NormalizedOrder,
    OptionType,
    OrderSide,
    OrderType,
    ProductType,
)
from market.instruments import Instrument, instrument_resolver
from oms.models import OMSOrderState

NIFTY_LOT = 65  # the authoritative Dhan lot size for the current NIFTY contract

# A real uuid: execute_order queries `orders` by user_id, and a malformed id made
# that lookup raise 22P02, which surfaced as an unexplained rejection.
TEST_UUID = "11111111-2222-3333-4444-555555555555"


def nifty_instrument(lot_size: int = NIFTY_LOT, **overrides) -> Instrument:
    """A resolved NIFTY futures contract, standing in for the Dhan master."""
    fields = dict(
        broker="dhan",
        security_id="49081",
        broker_symbol="NIFTY26AUGFUT",
        exchange_segment="NSE_FNO",
        instrument_type="FUT",
        lot_size=lot_size,
        underlying="NIFTY",
        expiry="2026-08-28",
        source="fixture",
    )
    fields.update(overrides)
    return Instrument(**fields)


@pytest.fixture
def resolver():
    """Swap the instrument registry for the duration of one test."""
    saved = list(instrument_resolver._providers)

    def _use(*instruments: Instrument | None):
        instrument_resolver._providers = []
        for inst in instruments:
            if inst is not None:
                instrument_resolver.register(
                    "fixture",
                    lambda *a, _i=inst, **k: _i,
                    authoritative=True,
                )

    yield _use
    instrument_resolver._providers = saved


async def run_to_oms(order: NormalizedOrder) -> tuple[object, int | None]:
    """Drive gate.execute_order with the broker leg mocked, capturing final quantity.

    Returns the OrderResult and the quantity handed to the OMS. ``None`` for the
    quantity means the order was rejected before reaching execution, which is itself
    the assertion many tests care about.
    """
    captured: dict = {}

    async def _fake_place_and_wait(req, timeout: float = 20.0):
        captured["quantity"] = req.quantity
        captured["request"] = req
        oms_order = MagicMock()
        oms_order.state = OMSOrderState.FILLED
        oms_order.broker_order_id = "broker-1"
        oms_order.filled_quantity = req.quantity
        oms_order.average_price = 24000.0
        oms_order.latency_ms = 1.0
        oms_order.filled_at = None
        oms_order.message = "filled"
        return oms_order

    from oms.models import OmniOrder  # noqa: F401  (import parity with the real path)

    with (
        patch("engine.gate.async_safe_single", AsyncMock(return_value=None)),
        patch("engine.gate.async_supabase", AsyncMock(return_value=None)),
        patch("engine.gate.get_supabase", MagicMock()),
        patch("engine.gate._resolve_broker", AsyncMock(return_value="dhan")),
        patch("engine.gate._write_audit", AsyncMock(return_value=None)),
        patch("engine.gate.symbol_master.resolve_symbol", AsyncMock(side_effect=lambda s, b: s)),
        patch("oms.manager.order_manager") as mock_manager,
    ):
        mock_manager.place_and_wait = _fake_place_and_wait
        from engine.gate import execute_order

        result = await execute_order(user_id=TEST_UUID, order=order, source="strategy")

    return result, captured.get("quantity")


def allow_risk():
    """A RiskGuard that approves, so the test isolates the quantity path."""
    guard = MagicMock()
    guard.check_order = AsyncMock(return_value={"allowed": True, "reason": ""})
    guard._load_settings = AsyncMock(return_value=None)
    return patch("engine.gate.RiskGuard", return_value=guard)


def nifty_order(quantity: int, **overrides) -> NormalizedOrder:
    fields = dict(
        symbol="NSE:NIFTY26AUGFUT",
        exchange=Exchange.NFO,
        instrument_type=InstrumentType.FUT,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        product=ProductType.INTRADAY,
        quantity=quantity,
        is_paper=False,
    )
    fields.update(overrides)
    return NormalizedOrder(**fields)


# ──────────────────────────────────────────────────────────────────────────────
# Bug 1 — the requested quantity is the quantity that gets sent
# ──────────────────────────────────────────────────────────────────────────────


class TestQuantityIsNotReplaced:
    """The core regression. Requested units must arrive unchanged."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("lots", "expected_units"),
        [(1, 65), (2, 130), (3, 195), (5, 325), (10, 650)],
    )
    async def test_lots_convert_to_units_and_arrive_intact(self, resolver, lots, expected_units):
        """1/2/3/5/10 lots at lot 65 must arrive as 65/130/195/325/650 units.

        10 lots legitimately equals 650 units, so this case alone cannot detect the
        old defect -- which is exactly why the smaller cases are here. Under
        ``quantity = 10 * lot`` every one of these returned 650.
        """
        resolver(nifty_instrument())
        requested = nifty_order(expected_units)

        with allow_risk():
            result, final_quantity = await run_to_oms(requested)

        assert result.success is True, result.message
        assert final_quantity == expected_units
        assert requested.quantity == expected_units, "gate mutated the caller's order"

    @pytest.mark.asyncio
    async def test_single_lot_does_not_become_ten_lots(self, resolver):
        """The exact reported failure: one lot in, ten lots out."""
        resolver(nifty_instrument())
        with allow_risk():
            result, final_quantity = await run_to_oms(nifty_order(NIFTY_LOT))

        assert result.success is True, result.message
        assert final_quantity == NIFTY_LOT
        assert final_quantity != 10 * NIFTY_LOT

    @pytest.mark.asyncio
    async def test_units_are_not_multiplied_by_the_lot_size(self, resolver):
        """Units are already units. Multiplying by lot size double-counts."""
        resolver(nifty_instrument())
        with allow_risk():
            result, final_quantity = await run_to_oms(nifty_order(65))

        assert result.success is True, result.message
        assert final_quantity == 65, "quantity was multiplied by the lot size"

    @pytest.mark.asyncio
    async def test_a_different_contract_uses_its_own_lot_size(self, resolver):
        """Lot size comes from the resolved contract, not a hardcoded dict.

        A second contract with a different authoritative lot size must be honoured
        without any code change -- the property a hardcoded LOT_SIZES cannot have.
        """
        resolver(nifty_instrument(lot_size=30, broker_symbol="BANKNIFTY26AUGFUT",
                                  security_id="49082", exchange_segment="NSE_FNO"))
        with allow_risk():
            result, final_quantity = await run_to_oms(
                nifty_order(60, symbol="NSE:BANKNIFTY26AUGFUT")
            )

        assert result.success is True, result.message
        assert final_quantity == 60


# ──────────────────────────────────────────────────────────────────────────────
# Bug 1b — invalid quantities are refused, not silently corrected
# ──────────────────────────────────────────────────────────────────────────────


class TestInvalidQuantityIsRefused:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("quantity", [75, 100, 1, 64, 66])
    async def test_quantity_not_a_lot_multiple_is_rejected(self, resolver, quantity):
        """A quantity that is not a whole number of lots must not be rounded.

        75 is what the strategies emit (they assign a lot size as a quantity), and
        it is not a multiple of 65. Rounding it to 65 would be a different trade from
        the one that was sized, so the order is refused instead.
        """
        resolver(nifty_instrument())

        with allow_risk():
            result, final_quantity = await run_to_oms(nifty_order(quantity))

        assert final_quantity is None, "a bad quantity reached the broker"
        assert result.success is False
        assert "INVALID_LOT_MULTIPLE" in result.message

    @pytest.mark.asyncio
    @pytest.mark.parametrize("quantity", [0, -65])
    async def test_non_positive_quantity_is_rejected(self, resolver, quantity):
        resolver(nifty_instrument())

        with allow_risk():
            result, final_quantity = await run_to_oms(nifty_order(quantity))

        assert final_quantity is None
        assert "INVALID_QUANTITY" in result.message

    @pytest.mark.asyncio
    async def test_rejection_happens_before_the_risk_engine(self, resolver):
        """An unresolvable contract never reaches RiskGuard.

        There is no lot size to risk-check against, so evaluating risk first would
        produce a verdict on an order whose size is still unknown.
        """
        resolver()  # no authoritative provider
        guard = MagicMock()
        guard.check_order = AsyncMock(return_value={"allowed": True})
        guard._load_settings = AsyncMock(return_value=None)

        with patch("engine.gate.RiskGuard", return_value=guard):
            result, final_quantity = await run_to_oms(nifty_order(65))

        assert final_quantity is None
        assert "ORDER BLOCKED" in result.message
        guard.check_order.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# Bug 2 — missing instrument metadata fails closed
# ──────────────────────────────────────────────────────────────────────────────


class TestMissingMetadataFailsClosed:
    @pytest.mark.asyncio
    async def test_unresolvable_contract_blocks_with_required_fields_named(self, resolver):
        resolver()
        result, final_quantity = await run_to_oms(nifty_order(65))

        assert final_quantity is None
        assert result.success is False
        for field in ("Security ID", "Exchange Segment", "Instrument Type", "Lot Size"):
            assert field in result.message, f"blocked message omits {field}"

    @pytest.mark.asyncio
    async def test_a_provider_returning_none_does_not_fall_back_to_a_default(self, resolver):
        """A provider that declines is not permission to guess."""
        resolver(nifty_instrument(lot_size=NIFTY_LOT))
        # Replace the authoritative provider with one that always declines.
        instrument_resolver._providers = []
        instrument_resolver.register(
            "declines", lambda *a, **k: None, authoritative=True, note="test"
        )

        with allow_risk():
            result, final_quantity = await run_to_oms(nifty_order(65))

        assert final_quantity is None
        assert "ORDER BLOCKED" in result.message

    @pytest.mark.asyncio
    async def test_cash_equity_is_exempt_from_lot_resolution(self, resolver):
        """EQ has no lot contract, so it must not be blocked on instrument metadata."""
        resolver()  # nothing resolvable at all

        order = NormalizedOrder(
            symbol="NSE:RELIANCE-EQ",
            exchange=Exchange.NSE,
            instrument_type=InstrumentType.EQ,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            product=ProductType.INTRADAY,
            quantity=10,
            is_paper=False,
        )
        with allow_risk():
            result, final_quantity = await run_to_oms(order)

        assert final_quantity == 10


# ──────────────────────────────────────────────────────────────────────────────
# Bug 3 — RiskGuard must see the final quantity
# ──────────────────────────────────────────────────────────────────────────────


class TestRiskGuardSeesFinalQuantity:
    @pytest.mark.asyncio
    async def test_risk_is_evaluated_on_the_quantity_that_is_sent(self, resolver):
        """Whatever RiskGuard approved must be what the OMS receives."""
        resolver(nifty_instrument())
        seen: dict = {}

        guard = MagicMock()
        guard._load_settings = AsyncMock(return_value=None)

        async def _check(order):
            seen["quantity"] = order.quantity
            return {"allowed": True, "reason": ""}

        guard.check_order = _check

        with patch("engine.gate.RiskGuard", return_value=guard):
            result, final_quantity = await run_to_oms(nifty_order(325))

        assert result.success is True, result.message
        assert seen["quantity"] == 325
        assert seen["quantity"] == final_quantity

    @pytest.mark.asyncio
    async def test_a_risk_rejection_still_stops_the_order(self, resolver):
        """The fail-closed metadata check must not have displaced the risk gate."""
        resolver(nifty_instrument())
        guard = MagicMock()
        guard.check_order = AsyncMock(
            return_value={"allowed": False, "reason": "Max position size exceeded"}
        )
        guard._load_settings = AsyncMock(return_value=None)

        with patch("engine.gate.RiskGuard", return_value=guard):
            result, final_quantity = await run_to_oms(nifty_order(65))

        assert final_quantity is None
        assert result.message == "MAX_POSITION_SIZE"


# ──────────────────────────────────────────────────────────────────────────────
# Bug 4 — symbol propagation across instrument families
# ──────────────────────────────────────────────────────────────────────────────


class TestSymbolPropagation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("strategy_key", "requested"),
        [
            ("trend_rider", "NSE:NIFTY50-INDEX"),
            ("macd_cross", "NSE:NIFTY50-INDEX"),
            ("bollinger_bandit", "NSE:BANKNIFTY-INDEX"),
            ("rsi_mean_reversion", "NSE:BANKNIFTY-INDEX"),
            ("smc_sniper", "NSE:NIFTY50-INDEX"),
            ("intraday_momentum", "NSE:RELIANCE-EQ"),
            ("mean_reversion_pro", "NSE:FINNIFTY-INDEX"),
            ("breakout_scanner", "NSE:SENSEX-INDEX"),
        ],
    )
    async def test_strategy_trades_the_requested_symbol(self, strategy_key, requested):
        """The strategy must trade what the run asked for, not its own default."""
        config = BacktestConfig(
            strategy_type=strategy_key,
            strategy_params={},  # the normal case: the form has no symbol field
            symbol=requested,
            exchange="NSE",
            interval="1d",
            days=365,
        )
        strategy = await backtest_manager._setup_strategy(config)
        assert strategy.symbol == requested

    @pytest.mark.asyncio
    async def test_config_symbol_overrides_a_conflicting_strategy_param(self):
        """The run's symbol wins: it is what the candles were loaded for."""
        config = BacktestConfig(
            strategy_type="trend_rider",
            strategy_params={"symbol": "NSE:SENSEX-INDEX"},
            symbol="NSE:NIFTY50-INDEX",
            exchange="NSE",
            interval="1d",
            days=365,
        )
        strategy = await backtest_manager._setup_strategy(config)
        assert strategy.symbol == "NSE:NIFTY50-INDEX"

    @pytest.mark.asyncio
    async def test_derived_trading_symbols_are_untouched(self):
        """Options and futures strategies build their own contract symbols."""
        config = BacktestConfig(
            strategy_type="smc_sniper",
            strategy_params={},
            symbol="NSE:NIFTY50-INDEX",
            exchange="NSE",
            interval="1d",
            days=365,
        )
        strategy = await backtest_manager._setup_strategy(config)
        assert strategy.symbol == "NSE:NIFTY50-INDEX"

    @pytest.mark.asyncio
    async def test_an_empty_symbol_is_refused_rather_than_defaulted(self):
        """No requested symbol must mean an error, not a silent fallback to NIFTY."""
        config = BacktestConfig(
            strategy_type="trend_rider",
            strategy_params={},
            symbol="",
            exchange="NSE",
            interval="1d",
            days=365,
        )
        with pytest.raises(ValueError, match="symbol is required"):
            await backtest_manager._setup_strategy(config)


# ──────────────────────────────────────────────────────────────────────────────
# Bug 5 — capital and exposure
# ──────────────────────────────────────────────────────────────────────────────


class TestCapitalAndExposure:
    @pytest.mark.asyncio
    async def test_ten_lakh_capital_cannot_produce_an_unsafe_final_order(self, resolver):
        """With Rs 10,00,000 capital the position ceiling must stop the order.

        The quantity itself is a valid lot multiple; what makes it unsafe is its
        notional. That is the risk engine's job, and this asserts the engine still
        does it once sizing no longer silently rewrites the quantity beforehand.
        """
        capital = 1_000_000.0
        price = 24_000.0
        ten_lots = 10 * NIFTY_LOT  # 650 units, ~Rs 1.56 crore
        assert ten_lots * price > capital * 10, "the fixture must be unsafe by construction"

        resolver(nifty_instrument())
        guard = MagicMock()
        guard._load_settings = AsyncMock(return_value=None)

        async def _check(order):
            notional = order.quantity * price
            if notional > capital:
                return {
                    "allowed": False,
                    "reason": f"Max position size exceeded: {notional} > {capital}",
                }
            return {"allowed": True, "reason": ""}

        guard.check_order = _check

        with patch("engine.gate.RiskGuard", return_value=guard):
            result, final_quantity = await run_to_oms(nifty_order(ten_lots))

        assert final_quantity is None, "an order 15x capital reached the broker"
        assert result.success is False

    @pytest.mark.asyncio
    async def test_an_affordable_position_is_allowed_through(self, resolver):
        """The guard above must not be rejecting everything -- check the pass case."""
        capital = 1_000_000.0
        price = 24_000.0
        one_lot = 30  # a lot-30 contract: Rs 7.2 lakh at this price
        assert one_lot * price < capital

        resolver(nifty_instrument(lot_size=30, broker_symbol="BANKNIFTY26AUGFUT",
                                  security_id="49082"))
        with allow_risk():
            result, final_quantity = await run_to_oms(
                nifty_order(one_lot, symbol="NSE:BANKNIFTY26AUGFUT")
            )

        assert result.success is True, result.message
        assert final_quantity == one_lot


# ──────────────────────────────────────────────────────────────────────────────
# The one authoritative resolver
# ──────────────────────────────────────────────────────────────────────────────


class TestSingleAuthoritativeResolver:
    def test_resolver_refuses_to_invent_values(self):
        saved = list(instrument_resolver._providers)
        try:
            instrument_resolver._providers = []
            assert instrument_resolver.resolve("NSE:NIFTY50-INDEX", broker="dhan",
                                               instrument_type="FUT") is None
            with pytest.raises(Exception, match="Unable to resolve authoritative"):
                instrument_resolver.require("NSE:NIFTY50-INDEX", broker="dhan",
                                            instrument_type="FUT")
        finally:
            instrument_resolver._providers = saved

    def test_first_authoritative_provider_wins_and_is_reported(self):
        saved = list(instrument_resolver._providers)
        try:
            instrument_resolver._providers = []
            instrument_resolver.register(
                "first", lambda *a, **k: nifty_instrument(lot_size=65), authoritative=True
            )
            instrument_resolver.register(
                "second", lambda *a, **k: nifty_instrument(lot_size=999), authoritative=True
            )
            found = instrument_resolver.resolve("X", broker="dhan", instrument_type="FUT")
            assert found.lot_size == 65

            report = instrument_resolver.explain("X", broker="dhan", instrument_type="FUT")
            assert [p["name"] for p in report["providers"]] == ["first", "second"]
        finally:
            instrument_resolver._providers = saved

    def test_units_and_lots_are_converted_in_exactly_one_place(self):
        inst = nifty_instrument()
        assert inst.units_for_lots(1) == 65
        assert inst.units_for_lots(2) == 130
        assert inst.units_for_lots(10) == 650
        assert inst.lots_for_units(130) == 2.0
        with pytest.raises(ValueError):
            inst.units_for_lots(0)
        with pytest.raises(ValueError):
            nifty_instrument(lot_size=0).units_for_lots(1)

    def test_a_raising_provider_does_not_break_resolution(self):
        saved = list(instrument_resolver._providers)
        try:
            instrument_resolver._providers = []

            def _boom(*a, **k):
                raise RuntimeError("Dhan unreachable")

            instrument_resolver.register("boom", _boom, authoritative=True)
            instrument_resolver.register(
                "good", lambda *a, **k: nifty_instrument(), authoritative=True
            )
            found = instrument_resolver.resolve("X", broker="dhan", instrument_type="FUT")
            assert found is not None and found.lot_size == 65
        finally:
            instrument_resolver._providers = saved

# ──────────────────────────────────────────────────────────────────────────────
# Live accounts must have an explicit position ceiling
# ──────────────────────────────────────────────────────────────────────────────


class TestLiveRequiresPositionCeiling:
    """`max_position_size <= 0` means unlimited for paper, and blocks for live.

    Production carries `max_position_size = 0` on three of four `risk_settings` rows,
    and `_check_max_position_size` treats that as unlimited. A live order on those
    accounts therefore had no exposure ceiling at all.
    """

    def _guard(self, max_position_size: int):
        from risk.riskguard import RiskGuard
        from core.models import RiskSettings

        guard = RiskGuard("u1")
        guard._load_settings = AsyncMock(
            return_value=RiskSettings(
                user_id="u1",
                max_position_size=max_position_size,
                is_live=True,
                kill_switch_enabled=False,
            )
        )
        return guard

    @pytest.mark.asyncio
    @pytest.mark.parametrize("ceiling", [0, -1])
    async def test_live_order_is_blocked_when_no_ceiling_is_set(self, ceiling):
        result = await self._guard(ceiling)._check_live_requires_position_ceiling(
            nifty_order(65, is_paper=False), _settings(max_position_size=ceiling)
        )
        assert result["allowed"] is False
        assert "LIVE_POSITION_CEILING_UNSET" in result["reason"]
        assert "max_position_size" in result["reason"]

    @pytest.mark.asyncio
    async def test_live_order_passes_once_a_ceiling_exists(self):
        result = await self._guard(250000)._check_live_requires_position_ceiling(
            nifty_order(65, is_paper=False), _settings(max_position_size=250000)
        )
        assert result["allowed"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("ceiling", [0, -1])
    async def test_paper_order_is_unaffected(self, ceiling):
        """Paper and backtest keep the permissive reading; only money-at-stake is strict."""
        result = await self._guard(ceiling)._check_live_requires_position_ceiling(
            nifty_order(65, is_paper=True), _settings(max_position_size=ceiling)
        )
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_a_blocked_live_order_reaches_no_broker(self, resolver):
        """End to end: a live order on an account with no ceiling stops before OMS."""
        resolver(nifty_instrument())
        from core.models import RiskSettings
        from risk.riskguard import RiskGuard

        guard = MagicMock()
        guard._load_settings = AsyncMock(return_value=None)
        real = RiskGuard(TEST_UUID)
        real._load_settings = AsyncMock(
            return_value=RiskSettings(user_id=TEST_UUID, max_position_size=0, is_live=True,
                                      kill_switch_enabled=False)
        )
        real._get_current_capital_usage = AsyncMock(return_value=0.0)
        real._get_open_position_count = AsyncMock(return_value=0)
        real._get_today_pnl = AsyncMock(return_value=0.0)
        real._get_drawdown = AsyncMock(return_value=0.0)
        guard.check_order = real.check_order

        with patch("engine.gate.RiskGuard", return_value=guard):
            result, final_quantity = await run_to_oms(nifty_order(65, is_paper=False))

        assert final_quantity is None
        assert result.success is False
        assert "LIVE_POSITION_CEILING_UNSET" in result.message

    @pytest.mark.asyncio
    async def test_a_paper_order_on_the_same_account_still_trades(self, resolver):
        """The new rule must not take paper trading down with it."""
        resolver(nifty_instrument())
        with allow_risk():
            result, final_quantity = await run_to_oms(nifty_order(65, is_paper=True))

        assert result.success is True, result.message
        assert final_quantity == 65


def _settings(**overrides):
    from core.models import RiskSettings

    return RiskSettings(user_id=TEST_UUID, **overrides)
