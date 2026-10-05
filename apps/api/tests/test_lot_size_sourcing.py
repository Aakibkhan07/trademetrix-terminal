"""Position sizing must come from the instrument master, and fail closed without it.

Every one of these sites previously sized a position from a hardcoded literal:

    strategies/*.py (14 files)      LOT_SIZES.get(self.symbol, 75)   -> 1 lot, 2 lots, ...
    market/instrument_service.py    LOT_SIZES.get(index.upper(), 65)
    engine/strategy_compiler.py     LOT_SIZES.get(symbol, 65)
    engine/user_strategy_*.py       LOT_SIZES.get(strategy.index_symbol, 65)
    strategies/buyer_base.py        self.lot_size = 0
    strategies/hero_zero.py         qty = 10 * self.lot_size
    core/constants.py               the LOT_SIZES table itself
    market/option_chain.py          a duplicate of that table, never referenced

The themes are uniform and each test below names which of them it covers, because
"the lot size is wrong somewhere" is not an actionable bug report.

The lot-size *reference* (October 2026 values) lives in
`tests/fixtures/lot_size_reference.py` and is used here as a sanity fixture only.
A test asserting a strategy sizes to 65 proves the reference agrees with the code;
it never proves 65 is correct. Only the instrument master can.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from market.instruments import (
    Instrument,
    instrument_resolver,
    resolve_future_contract,
    resolve_lot_size,
    resolve_option_contract,
)

NIFTY_REFERENCE_LOT = 65


def nifty_opt(strike: float = 24000, expiry: str = "2026-08-28", otype: str = "CE",
              lot_size: int = NIFTY_REFERENCE_LOT) -> Instrument:
    return Instrument(
        broker="dhan",
        security_id=f"sec-{underlying_of(strike)}-{expiry}-{strike}-{otype}",
        broker_symbol=f"NIFTY{expiry}{strike}{otype}",
        exchange_segment="NSE_FNO",
        instrument_type="OPT",
        lot_size=lot_size,
        underlying="NIFTY",
        expiry=expiry,
        strike=strike,
        option_type=otype,
        source="fixture",
    )


def underlying_of(_strike: float) -> str:
    return "NIFTY"


@pytest.fixture
def resolver():
    saved = list(instrument_resolver._providers)

    def _register(fn=None):
        instrument_resolver._providers = []
        if fn is not None:
            instrument_resolver.register("fixture", fn, authoritative=True)

    yield _register
    instrument_resolver._providers = saved


# ──────────────────────────────────────────────────────────────────────────────
# Strategies: lots x lot_size, and nothing when the lot size is unknown
# ──────────────────────────────────────────────────────────────────────────────


class TestStrategySizing:
    """BaseStrategy owns the conversion. No strategy may recompute it."""

    STRATEGIES = [
        "trend_rider", "macd_cross", "bollinger_bandit", "rsi_mean_reversion",
        "smc_sniper", "intraday_momentum", "mean_reversion_pro", "breakout_scanner",
        "arbitrage_hunter", "orb_pro", "gap_up_express", "expiry_hunter",
        "option_wheel", "vwap_band",
    ]

    @pytest.mark.parametrize("key", STRATEGIES)
    def test_no_strategy_hardcodes_a_lot_size(self, key):
        """The 14 scattered fallbacks are gone, not merely unused."""
        import inspect

        from strategies import get_strategy

        source = inspect.getsource(get_strategy(key))
        assert "LOT_SIZES" not in source, f"{key} still reads a hardcoded lot-size table"

    @pytest.mark.parametrize("key", STRATEGIES)
    def test_quantity_is_lots_times_the_injected_lot_size(self, key):
        from strategies import get_strategy

        strategy = get_strategy(key)({"symbol": "NSE:NIFTY50-INDEX", "lots": 2,
                                      "lot_size": NIFTY_REFERENCE_LOT})
        assert strategy.lots == 2
        assert strategy.lot_size == NIFTY_REFERENCE_LOT
        assert strategy.quantity == 2 * NIFTY_REFERENCE_LOT

    @pytest.mark.parametrize("key", STRATEGIES)
    def test_quantity_is_zero_when_the_lot_size_is_unresolved(self, key):
        """Absent metadata yields 0, which downstream blocks -- never a guess."""
        from strategies import get_strategy

        strategy = get_strategy(key)({"symbol": "NSE:NIFTY50-INDEX"})
        assert strategy.lot_size is None
        assert strategy.quantity == 0
        assert strategy.has_resolved_lot_size is False

    @pytest.mark.parametrize("junk", [0, -5, "", "abc", None, 1.5])
    def test_a_malformed_lot_size_is_unresolved_not_defaulted(self, junk):
        """A form value that will not parse must not become a contract size."""
        from strategies.trend_rider import TrendRider

        strategy = TrendRider({"symbol": "NSE:NIFTY50-INDEX", "lot_size": junk})
        assert strategy.lot_size is None
        assert strategy.quantity == 0

    def test_an_explicit_unit_quantity_still_wins(self):
        """A caller that genuinely means units is honoured."""
        from strategies.trend_rider import TrendRider

        strategy = TrendRider({"symbol": "NSE:NIFTY50-INDEX", "lot_size": 65, "quantity": 200})
        assert strategy.quantity == 200


# ──────────────────────────────────────────────────────────────────────────────
# instrument_service: None, never 65
# ──────────────────────────────────────────────────────────────────────────────


class TestInstrumentService:
    def test_returns_none_when_unresolved(self, resolver):
        from market.instrument_service import InstrumentService

        resolver()
        assert InstrumentService().lot_size("NIFTY") is None

    def test_returns_the_resolved_value(self, resolver):
        from market.instrument_service import InstrumentService

        resolver(lambda symbol, **k: nifty_opt())
        assert InstrumentService().lot_size("NIFTY") == NIFTY_REFERENCE_LOT

    def test_strips_the_exchange_prefix(self, resolver):
        """`NSE:NIFTY50-INDEX` and `NIFTY` must reach the resolver as one key."""
        from market.instrument_service import InstrumentService

        seen: list[str] = []
        resolver(lambda symbol, **k: (seen.append(symbol), nifty_opt())[1])
        InstrumentService().lot_size("NSE:NIFTY50-INDEX")
        assert seen == ["NIFTY50-INDEX"]


# ──────────────────────────────────────────────────────────────────────────────
# strategy_compiler: refuses to build a plan it cannot size
# ──────────────────────────────────────────────────────────────────────────────


class TestCompilerRefusesToGuess:
    def test_compile_raises_without_a_lot_size(self, resolver):
        from engine.strategy_compiler import compile_user_strategy
        from tests.test_user_strategies import SAMPLE_OPTION_CHAIN, make_leg, make_strategy

        resolver()
        plan_input = make_strategy(legs=[make_leg(lots=1)])
        with pytest.raises(ValueError, match="no authoritative lot size"):
            compile_user_strategy(plan_input, spot_price=24200.0,
                                  option_chain=SAMPLE_OPTION_CHAIN)

    def test_compile_uses_the_resolved_lot_size(self, resolver):
        from engine.strategy_compiler import compile_user_strategy
        from tests.test_user_strategies import SAMPLE_OPTION_CHAIN, make_leg, make_strategy

        resolver(lambda symbol, **k: nifty_opt())
        plan = compile_user_strategy(make_strategy(legs=[make_leg(lots=3)]),
                                     spot_price=24200.0, option_chain=SAMPLE_OPTION_CHAIN)
        assert plan.orders[0].quantity == 3 * NIFTY_REFERENCE_LOT


# ──────────────────────────────────────────────────────────────────────────────
# BuyerBase: the risk-budget sizing was already right; the input was not
# ──────────────────────────────────────────────────────────────────────────────


class TestBuyerBaseFailsClosed:
    def _buyer(self):
        from strategies.buyer_base import BuyerBase

        class _Concrete(BuyerBase):
            """BuyerBase is abstract; this exercises only its sizing and state logic."""

            async def _on_15m(self, candle):  # pragma: no cover - unused here
                return None

        return _Concrete({"strategy_id": "test", "index": "NIFTY", "capital": 500000})

    def test_starts_with_no_lot_size(self):
        assert self._buyer().lot_size is None

    def test_premium_size_refuses_an_unresolved_lot(self):
        """`lots * None` must not be the answer when metadata is missing."""
        lots, qty, r = self._buyer()._premium_size(entry_premium=100.0, sl_premium=70.0,
                                                   lot_size=None)
        assert (lots, qty) == (0, 0)
        assert r == 0.0

    def test_premium_size_derives_units_from_risk_budget(self):
        """The correct shape: lots from risk and outlay cap, units = lots x lot."""
        buyer = self._buyer()
        capital = buyer.bc.capital
        lots, qty, _ = buyer._premium_size(entry_premium=100.0, sl_premium=90.0,
                                           lot_size=NIFTY_REFERENCE_LOT)
        assert lots >= 1
        assert qty == lots * NIFTY_REFERENCE_LOT
        # Risk per lot is 10 points x lot size; total risk must fit the budget.
        assert lots * 10 * NIFTY_REFERENCE_LOT <= capital * buyer.bc.risk_per_trade_pct / 100.0
        # Outlay must respect the cap.
        assert qty * 100.0 <= capital * buyer.bc.max_outlay_pct / 100.0 + 1e-6

    def test_on_start_aborts_when_the_lot_size_cannot_be_resolved(self, resolver):
        """No lot size means no trading, rather than sizing on an assumption."""
        resolver()
        buyer = self._buyer()
        with patch("strategies.buyer_base.instrument_service") as svc:
            svc.lot_size.return_value = None
            svc.strike_step.return_value = 50
            with patch("strategies.buyer_base.cache") as cache:
                cache.get = AsyncMock(return_value=None)
                with patch("strategies.buyer_base.datetime") as _dt:
                    import asyncio
                    asyncio.run(buyer.on_start())
        assert buyer.lot_size is None

    def test_a_cached_lot_size_is_revalidated_not_trusted(self, resolver):
        """Lot sizes are revised on expiry cycles, so yesterday's value can be wrong.

        A restored cache value is therefore re-resolved. Trusting it would let a
        contract-size revision silently mis-size a position the next day.
        """
        resolver(lambda symbol, **k: nifty_opt(lot_size=120))
        buyer = self._buyer()
        with patch("strategies.buyer_base.instrument_service") as svc:
            svc.lot_size.return_value = 120
            svc.strike_step.return_value = 50
            buyer.from_state({"lot_size": 75, "step": 50})
        assert buyer.lot_size == 120, "a stale cached lot size was accepted"

    def test_a_zero_cached_lot_size_is_discarded(self, resolver):
        resolver(lambda symbol, **k: nifty_opt(lot_size=65))
        buyer = self._buyer()
        with patch("strategies.buyer_base.instrument_service") as svc:
            svc.lot_size.return_value = 65
            buyer.from_state({"lot_size": 0, "step": 50})
        assert buyer.lot_size == 65


# ──────────────────────────────────────────────────────────────────────────────
# Exact contract resolution
# ──────────────────────────────────────────────────────────────────────────────


class TestExactContractResolution:
    """Stock option lot sizes vary per underlying, so a symbol lookup is not enough."""

    def test_option_contract_is_identified_by_underlying_expiry_strike_and_type(self, resolver):
        resolver(_OptionMaster())
        found = resolve_option_contract("NIFTY", expiry="2026-08-28", strike=24000,
                                        option_type="CE")
        assert found is not None
        assert found.lot_size == NIFTY_REFERENCE_LOT
        assert found.security_id

    def test_a_different_contract_carries_its_own_lot_size(self, resolver):
        """Two strikes of the same underlying can differ; both must resolve cleanly."""
        resolver(_OptionMaster())
        at = resolve_option_contract("NIFTY", expiry="2026-08-28", strike=24000,
                                    option_type="CE")
        away = resolve_option_contract("NIFTY", expiry="2026-08-28", strike=25000,
                                       option_type="CE")
        assert at.lot_size == 65
        assert away.lot_size == 30
        assert at.security_id != away.security_id

    def test_unresolvable_option_contract_is_none(self, resolver):
        resolver(_OptionMaster(knows=False))
        assert resolve_option_contract("NIFTY", expiry="2026-08-28", strike=24000,
                                       option_type="CE") is None

    def test_an_invalid_option_type_is_refused(self, resolver):
        resolver(_OptionMaster())
        assert resolve_option_contract("NIFTY", expiry="2026-08-28", strike=24000,
                                       option_type="XX") is None

    def test_future_contract_resolution(self, resolver):
        resolver(_FutureMaster())
        found = resolve_future_contract("NSE:NIFTY50-INDEX", expiry="2026-08-28")
        assert found is not None and found.lot_size == NIFTY_REFERENCE_LOT
        assert resolve_future_contract("NSE:NIFTY50-INDEX", expiry="2026-09-25") is None


# ──────────────────────────────────────────────────────────────────────────────
# The reference is a fixture, not a source
# ──────────────────────────────────────────────────────────────────────────────


class TestReferenceIsNeverTheSource:
    def test_resolve_lot_size_returns_none_without_a_provider(self, resolver):
        resolver()
        assert resolve_lot_size("NIFTY") is None

    def test_resolve_lot_size_returns_the_masters_value_not_the_reference(self, resolver):
        """Deliberate disagreement: the master says 99, the reference says 65."""
        resolver(lambda symbol, **k: nifty_opt(lot_size=99))
        assert resolve_lot_size("NIFTY") == 99

    def test_the_removed_tables_are_gone(self):
        """`core.constants.LOT_SIZES` and the option_chain duplicate no longer exist."""
        import core.constants as constants
        import market.option_chain as option_chain

        assert not hasattr(constants, "LOT_SIZES")
        assert not hasattr(option_chain, "LOT_SIZES")

    def test_strike_intervals_survive_the_constants_change(self):
        """Only the lot-size table was removed; the rest of constants must be intact."""
        import core.constants as constants

        assert isinstance(constants.STRIKE_INTERVALS, dict) and constants.STRIKE_INTERVALS
        assert constants.get_weekly_expiry("NIFTY") is not None

# ──────────────────────────────────────────────────────────────────────────────
# Master-shaped providers
# ──────────────────────────────────────────────────────────────────────────────


class _OptionMaster:
    """An object-style provider: a symbol lookup plus exact-contract resolution.

    A bare callable cannot answer "which contract is NIFTY 24000 CE expiring
    2026-08-28", so the resolver accepts an object exposing ``resolve_option``.
    """

    def __init__(self, knows: bool = True):
        self.knows = knows

    def resolve(self, symbol, *, broker, instrument_type):
        return nifty_opt()

    def resolve_option(self, underlying, *, expiry, strike, option_type, broker):
        if not self.knows or underlying != "NIFTY" or expiry != "2026-08-28":
            return None
        # Different strikes, deliberately different lot sizes, to prove the value comes
        # from the contract rather than from the underlying.
        return nifty_opt(strike=strike, expiry=expiry, otype=option_type,
                         lot_size=65 if strike == 24000 else 30)


class _FutureMaster:
    def resolve(self, symbol, *, broker, instrument_type):
        return self.resolve_future(symbol.split(":")[-1], expiry="2026-08-28", broker=broker)

    def resolve_future(self, underlying, *, expiry, broker):
        if underlying in ("NIFTY", "NIFTY50-INDEX") and expiry == "2026-08-28":
            return Instrument(
                broker="dhan", security_id="49081", broker_symbol="NIFTY26AUGFUT",
                exchange_segment="NSE_FNO", instrument_type="FUT",
                lot_size=NIFTY_REFERENCE_LOT, underlying="NIFTY",
                expiry=expiry, source="fixture",
            )
        return None
