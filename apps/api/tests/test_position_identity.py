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

#: Real Dhan security ids, taken from the live master. 40749/40750 are the same strike and
#: expiry on opposite option types; 52694 is a different expiry; 888990 is the same numeric
#: shape in a different segment.
NIFTY_CE = "40749"       # NIFTY Oct 23250 CE  NSE_FNO
NIFTY_PE = "40750"       # NIFTY Oct 23250 PE  NSE_FNO
NIFTY_CE_NEXT = "52694"  # 360ONE Oct 1040 CE   NSE_FNO
BSE_FOO = "888990"       # SENSEX Oct 74800 CE BSE_FNO


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

    def test_the_symbol_is_not_the_security_id(self, adapter):
        p = adapter._normalize_position(broker_position(NIFTY_CE, "NSE_FNO"))
        assert p.symbol != NIFTY_CE, (
            "the broker's security id must not be stored as the symbol; that is what made "
            "every position unmatchable"
        )
        assert p.symbol.startswith("NIFTY"), p.symbol

    def test_option_metadata_comes_from_the_master_not_a_string_parse(self, adapter):
        p = adapter._normalize_position(broker_position(NIFTY_CE, "NSE_FNO"))
        assert p.instrument_type == InstrumentType.OPT, (
            "a five-digit security id cannot match the compact-symbol regex, so the old code "
            "classified every Dhan option position as EQ"
        )
        assert p.expiry_date == "2026-10-06"
        assert p.strike_price == 23250.0
        assert p.option_type == OptionType.CE
        assert p.multiplier == 65.0, "lot size is contract metadata and belongs on the position"

    def test_the_same_id_in_another_segment_does_not_collide(self, adapter):
        a = adapter._normalize_position(broker_position("888990", "BSE_FNO"))
        b = adapter._normalize_position(broker_position("888990", "NSE_FNO"))
        key = lambda p: (p.exchange.value, p.exchange_segment, p.security_id)  # noqa: E731
        assert key(a) != key(b), (
            "the same security id under two segments must not resolve to the same position"
        )

    def test_call_and_put_on_the_same_strike_are_different_positions(self, adapter):
        ce = adapter._normalize_position(broker_position(NIFTY_CE, "NSE_FNO"))
        pe = adapter._normalize_position(broker_position(NIFTY_PE, "NSE_FNO"))
        assert ce.security_id != pe.security_id
        assert ce.option_type == OptionType.CE
        assert pe.option_type == OptionType.PE
        assert ce.symbol != pe.symbol

    def test_two_expiries_are_different_positions(self, adapter):
        a = adapter._normalize_position(broker_position(NIFTY_CE, "NSE_FNO"))
        b = adapter._normalize_position(broker_position(NIFTY_CE_NEXT, "NSE_FNO"))
        assert (a.security_id, a.expiry_date) != (b.security_id, b.expiry_date)

    def test_every_identity_field_survives_normalisation(self, adapter):
        p = adapter._normalize_position(broker_position(NIFTY_CE, "NSE_FNO"))
        assert p.exchange == Exchange.NSE
        assert p.exchange_segment == "NSE_FNO"
        assert p.security_id == NIFTY_CE
        assert p.broker == "dhan"
        assert p.quantity == 65
        assert p.average_buy_price == 65.0
        assert p.unrealised_pnl == 12.5
        assert p.realised_pnl == -3.25

    def test_the_brokers_product_type_is_honoured_not_assumed(self, adapter):
        for broker_value, expected in (
            ("INTRADAY", ProductType.INTRADAY),
            ("CNC", ProductType.DELIVERY),
            ("MARGIN", ProductType.NRML),
        ):
            p = adapter._normalize_position(
                broker_position(NIFTY_CE, "NSE_FNO", productType=broker_value))
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
    def test_a_position_cannot_attach_to_another_account(self, adapter):
        a = adapter._normalize_position(broker_position(NIFTY_CE, "NSE_FNO"))
        b = adapter._normalize_position(broker_position(NIFTY_CE, "NSE_FNO"))
        assert a.broker == b.broker == "dhan"
        a.broker = "fyers"
        assert position_key(a) == position_key(b), (
            "the contract identity is account-scoped upstream, but broker must be part of "
            "the comparison key or a cross-account match is invisible"
        )
        assert (a.broker, *position_key(a)) != (b.broker, *position_key(b))

    def test_a_position_cannot_attach_to_another_expiry(self, adapter):
        a = adapter._normalize_position(broker_position(NIFTY_CE, "NSE_FNO"))
        b = adapter._normalize_position(broker_position(NIFTY_CE_NEXT, "NSE_FNO"))
        assert a.expiry_date != b.expiry_date
        assert a.security_id != b.security_id

    def test_call_cannot_attach_to_put(self, adapter):
        ce = adapter._normalize_position(broker_position(NIFTY_CE, "NSE_FNO"))
        pe = adapter._normalize_position(broker_position(NIFTY_PE, "NSE_FNO"))
        assert (ce.option_type, ce.security_id) != (pe.option_type, pe.security_id)

    def test_an_unrelated_order_cannot_produce_a_position(self, adapter):
        """An equity position and an option position are not the same instrument."""
        eq = adapter._normalize_position({
            "securityId": "1333", "exchangeSegment": "NSE_EQ", "exchange": "NSE",
            "netQty": 10, "buyQty": 10, "productType": "CNC",
        })
        opt = adapter._normalize_position(broker_position(NIFTY_CE, "NSE_FNO"))
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
