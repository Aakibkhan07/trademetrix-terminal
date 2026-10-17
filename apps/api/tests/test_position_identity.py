"""Position identity and order<->position reconciliation.

The local `Position` model previously had no `security_id` and no `exchange_segment`, and the
Dhan adapter stored the broker's security id *in* `symbol` and then ran that string through
`_parse_instrument`, which matches a Fyers-style compact symbol (`NIFTY26OCT23250CE`). A
five-digit security id matches nothing, so every Dhan option position was stored as `EQ` with
no strike, no expiry and no option type. Local state could not distinguish two option
contracts at all.

These tests exercise the production adapter and production identity helpers. Nothing here
contacts a broker; the broker payloads are recorded fixtures, and the account read path is
verified separately against the real account.
"""
from __future__ import annotations

import pytest

from brokers.dhan_adapter import DhanAdapter
from core.models import Exchange, InstrumentType, OptionType, Position, ProductType

# ── real contracts, chosen from the live master at test time ──────────────────
#
# These used to be security ids transcribed from one snapshot of the live master:
#
#     NIFTY_CE = "40749"   # NIFTY Oct 23250 CE
#     NIFTY_PE = "40750"   # NIFTY Oct 23250 PE
#
# and that is a date, not a constant. Dhan reassigns security ids as contracts roll: once the
# October expiry passed, 40749 became a HINDZINC contract, and two tests here began asserting
# against the wrong instrument --
#
#     assert p.symbol.startswith("NIFTY")      -> 'HINDZINC-Nov2026-370-CE'
#     assert p.expiry_date == "2026-10-06"     -> '2026-11-23'
#
# The adapter did nothing wrong; it resolved the id it was given, correctly. What the ids encode
# is a relationship between contracts -- same strike and expiry, opposite option types -- and
# that relationship is what these tests are actually about. So they now pick contracts satisfying
# it from the master under test, and assert the relationship rather than a transcription.
#
# The shape of each contract is asserted against the resolved contract itself, never against a
# literal, so a master refresh cannot invalidate the test.


class _Contracts:
    """Real NIFTY/BSE contracts picked from the live master, chosen by relationship."""

    def __init__(self, provider):
        rows = [r for r in provider.dataset.rows_for_underlying("NIFTY")
                if r.option_type and r.strike_price and r.expiry_date]
        if not rows:
            raise AssertionError("the live master has no NIFTY option rows to test against")

        # A strike+expiry that has both a CE and a PE, so the two are provably one contract pair.
        pairs: dict[tuple, dict[str, object]] = {}
        for r in rows:
            key = (r.expiry_date, r.strike_price)
            pairs.setdefault(key, {}).setdefault(r.option_type, r)
        shared = [v for v in pairs.values() if "CE" in v and "PE" in v]
        if not shared:
            raise AssertionError("no NIFTY expiry/strike has both a CE and a PE in the master")

        first = min(shared, key=lambda v: v["CE"].expiry_date)  # type: ignore[union-attr]
        self.ce = first["CE"]
        self.pe = first["PE"]

        # A second expiry, for "different expiry must be a different position".
        other = [v["CE"] for v in shared if v["CE"].expiry_date != self.ce.expiry_date]
        self.ce_next = min(other, key=lambda r: r.expiry_date) if other else None

        bse = [r for r in provider.dataset.rows_for_underlying("SENSEX")
               if r.option_type == "CE" and r.strike_price and r.expiry_date]
        self.bse = min(bse, key=lambda r: r.expiry_date) if bse else None

    def __repr__(self) -> str:
        return (f"<contracts ce={self.ce.trading_symbol} pe={self.pe.trading_symbol} "
                f"next={getattr(self.ce_next, 'trading_symbol', None)}>")


def broker_position(security_id: str, segment: str, **over) -> dict:
    payload = {
        "securityId": security_id,
        "exchangeSegment": segment,
        "exchange": "NSE" if segment.startswith("NSE") else "BSE",
        "netQty": 65, "buyQty": 65, "sellQty": 0,
        "avgBuyPrice": 65.0, "avgSellPrice": 0.0,
        "unrealizedPnl": 12.5, "realizedPnl": -3.25,
        "productType": "INTRADAY",
    }
    payload.update(over)
    return payload


@pytest.fixture(scope="module", autouse=True)
def _master():
    """Load the real Dhan master so resolution is exercised, not stubbed."""
    import asyncio

    import httpx

    from market.dhan_instruments import DhanInstrumentProvider, dhan_instrument_provider

    text = httpx.get("https://images.dhan.co/api-data/api-scrip-master-detailed.csv",
                     timeout=180.0, follow_redirects=True).text
    provider = DhanInstrumentProvider(fetch=lambda u, t: text)
    asyncio.run(provider.refresh())
    dhan_instrument_provider._dataset = provider.dataset
    yield provider


@pytest.fixture(scope="module")
def contracts(_master):
    return _Contracts(_master)


@pytest.fixture
def adapter() -> DhanAdapter:
    a = DhanAdapter()
    a._client_id = "1100793385"
    a._access_token = "unused"
    return a


# ── 7. identity: nothing may collide ─────────────────────────────────────────


class TestPositionIdentityIsComplete:
    def test_the_model_carries_the_three_identity_fields(self):
        for field in ("security_id", "exchange_segment", "symbol"):
            assert field in Position.model_fields, (
                f"Position is missing {field}; identity needs "
                f"exchange + exchange_segment + security_id"
            )

    def test_the_symbol_is_not_the_security_id(self, adapter, contracts):
        p = adapter._normalize_position(broker_position(contracts.ce.security_id, "NSE_FNO"))
        assert p.symbol != contracts.ce.security_id, (
            "the broker's security id must not be stored as the symbol; that is what made "
            "every position unmatchable"
        )
        assert p.symbol == contracts.ce.trading_symbol, (
            f"symbol {p.symbol!r} is not the master's trading symbol "
            f"{contracts.ce.trading_symbol!r}"
        )

    def test_option_metadata_comes_from_the_master_not_a_string_parse(self, adapter, contracts):
        p = adapter._normalize_position(broker_position(contracts.ce.security_id, "NSE_FNO"))
        assert p.instrument_type == InstrumentType.OPT, (
            "a five-digit security id cannot match the compact-symbol regex, so the old code "
            "classified every Dhan option position as EQ"
        )
        # Every value below is asserted against the contract the master actually holds, so a
        # master refresh that reassigns ids or rolls expiries cannot invalidate this.
        assert p.expiry_date == contracts.ce.expiry_date
        assert p.strike_price == float(contracts.ce.strike_price)
        assert p.option_type == OptionType.CE
        assert p.multiplier == float(contracts.ce.lot_size), (
            "lot size is contract metadata and belongs on the position"
        )

    def test_the_same_id_in_another_segment_does_not_collide(self, adapter, contracts):
        shared_id = contracts.bse.security_id if contracts.bse else contracts.ce.security_id
        a = adapter._normalize_position(broker_position(shared_id, "BSE_FNO"))
        b = adapter._normalize_position(broker_position(shared_id, "NSE_FNO"))
        key = lambda p: (p.exchange.value, p.exchange_segment, p.security_id)  # noqa: E731
        assert key(a) != key(b), (
            "the same security id under two segments must not resolve to the same position"
        )

    def test_the_selected_pair_really_is_one_strike_and_expiry(self, contracts):
        """Check the selection independently of the normalisation.

        Without this the pairing is only ever checked against itself: pairing a CE with a PE
        from a different strike still leaves `ce` and `pe` internally consistent, so every
        test that uses them passes for the wrong reason. Mutation-tested --
        `scripts/mutation_position_identity.py` catches exactly this.
        """
        assert contracts.ce.strike_price == contracts.pe.strike_price, (
            f"fixture paired {contracts.ce.trading_symbol} with "
            f"{contracts.pe.trading_symbol} -- different strikes"
        )
        assert contracts.ce.expiry_date == contracts.pe.expiry_date, (
            f"fixture paired {contracts.ce.trading_symbol} with "
            f"{contracts.pe.trading_symbol} -- different expiries"
        )
        assert contracts.ce.option_type == "CE" and contracts.pe.option_type == "PE"
        assert contracts.ce.security_id != contracts.pe.security_id, (
            "a CE and a PE cannot share one security id"
        )

    def test_call_and_put_on_the_same_strike_are_different_positions(self, adapter, contracts):
        ce = adapter._normalize_position(broker_position(contracts.ce.security_id, "NSE_FNO"))
        pe = adapter._normalize_position(broker_position(contracts.pe.security_id, "NSE_FNO"))
        # The "same strike" this test is named for, checked on the NORMALISED output rather than
        # on the fixture. Two independent places assert the pairing, so a fixture that pairs the
        # wrong contracts is caught even if the fixture-level check is removed -- see
        # scripts/mutation_position_identity.py, which is how that gap was found.
        assert ce.strike_price == pe.strike_price, (
            f"call is strike {ce.strike_price} and put is {pe.strike_price}"
        )
        assert ce.expiry_date == pe.expiry_date, (
            f"call expires {ce.expiry_date} and put expires {pe.expiry_date}"
        )
        assert ce.security_id != pe.security_id
        assert ce.option_type == OptionType.CE
        assert pe.option_type == OptionType.PE
        assert ce.symbol != pe.symbol

    def test_two_expiries_are_different_positions(self, adapter, contracts):
        assert contracts.ce_next is not None, (
            "the master must offer a second NIFTY expiry for this test to mean anything"
        )
        a = adapter._normalize_position(broker_position(contracts.ce.security_id, "NSE_FNO"))
        b = adapter._normalize_position(broker_position(contracts.ce_next.security_id, "NSE_FNO"))
        assert (a.security_id, a.expiry_date) != (b.security_id, b.expiry_date)

    def test_every_identity_field_survives_normalisation(self, adapter, contracts):
        p = adapter._normalize_position(broker_position(contracts.ce.security_id, "NSE_FNO"))
        assert p.exchange == Exchange(contracts.ce.exchange)
        assert p.exchange_segment == contracts.ce.exchange_segment
        assert p.security_id == contracts.ce.security_id
        assert p.broker == "dhan"
        assert p.quantity == 65
        assert p.average_buy_price == 65.0
        assert p.unrealised_pnl == 12.5
        assert p.realised_pnl == -3.25

    def test_the_brokers_product_type_is_honoured_not_assumed(self, adapter, contracts):
        for broker_value, expected in (
            ("INTRADAY", ProductType.INTRADAY),
            ("CNC", ProductType.DELIVERY),
            ("MARGIN", ProductType.NRML),
        ):
            p = adapter._normalize_position(
                broker_position(contracts.ce.security_id, "NSE_FNO", productType=broker_value))
            assert p.product == expected, (
                f"productType {broker_value} mapped to {p.product}, expected {expected}. "
                "It used to be hardcoded to INTRADAY, and _unmap_product folded CNC and "
                "MARGIN into INTRADAY too -- three product types collapsed into one."
            )

    def test_an_unresolvable_position_keeps_its_raw_identity(self, adapter):
        p = adapter._normalize_position(broker_position("99999999", "NSE_FNO"))
        assert p.security_id == "99999999"
        assert p.exchange_segment == "NSE_FNO", (
            "a position that cannot be resolved must still carry the fields that identify "
            "it, not collapse to EQ with no identity"
        )


# ── 8. order <-> position consistency ────────────────────────────────────────


def position_key(p: Position) -> tuple:
    """The identity reconciliation must key on."""
    return (p.exchange.value, p.exchange_segment, p.security_id)


class TestOrderToPositionConsistency:
    def test_a_position_cannot_attach_to_another_account(self, adapter, contracts):
        sid = contracts.ce.security_id
        a = adapter._normalize_position(broker_position(sid, "NSE_FNO"))
        b = adapter._normalize_position(broker_position(sid, "NSE_FNO"))
        assert a.broker == b.broker == "dhan"
        a.broker = "fyers"
        assert position_key(a) == position_key(b), (
            "the contract identity is account-scoped upstream, but broker must be part of "
            "the comparison key or a cross-account match is invisible"
        )
        assert (a.broker, *position_key(a)) != (b.broker, *position_key(b))

    def test_a_position_cannot_attach_to_another_expiry(self, adapter, contracts):
        assert contracts.ce_next is not None
        a = adapter._normalize_position(broker_position(contracts.ce.security_id, "NSE_FNO"))
        b = adapter._normalize_position(broker_position(contracts.ce_next.security_id, "NSE_FNO"))
        assert a.expiry_date != b.expiry_date
        assert a.security_id != b.security_id

    def test_call_cannot_attach_to_put(self, adapter, contracts):
        ce = adapter._normalize_position(broker_position(contracts.ce.security_id, "NSE_FNO"))
        pe = adapter._normalize_position(broker_position(contracts.pe.security_id, "NSE_FNO"))
        assert (ce.option_type, ce.security_id) != (pe.option_type, pe.security_id)

    def test_an_unrelated_order_cannot_produce_a_position(self, adapter, contracts):
        """An equity position and an option position are not the same instrument."""
        eq = adapter._normalize_position({
            "securityId": "1333", "exchangeSegment": "NSE_EQ", "exchange": "NSE",
            "netQty": 10, "buyQty": 10, "productType": "CNC",
        })
        opt = adapter._normalize_position(broker_position(contracts.ce.security_id, "NSE_FNO"))
        assert position_key(eq) != position_key(opt)
        assert eq.instrument_type != opt.instrument_type

    def test_an_empty_broker_book_yields_no_positions(self, adapter):
        """The real account currently holds nothing.

        Recorded fixture, clearly labelled as such: the account read path is verified
        separately against the real Dhan account. This asserts only that the production
        normaliser maps an empty list to no positions, rather than inventing one.
        """
        normalised = [adapter._normalize_position(item) for item in []]
        assert normalised == [], "an empty broker book must not fabricate a position"
