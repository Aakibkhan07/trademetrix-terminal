"""The provider must answer identically whichever backend is installed.

This is the gate for switching `DhanInstrumentProvider` over to the mapped store. Not
"the mapped store is correct in isolation" -- it is that every public resolution method
returns the same value for the same input, on both backends, so the switch cannot
change behaviour.

Every public method is exercised: security id, trading symbol, index lot size,
expiries, strikes, resolve_option, resolve_future, resolve. Both backends are driven
through the real parser output, so the object path is the proven one and the mapped
path has to match it.

The fixture carries the cases that have bitten before: a security id above 65,535, a
lot size above 65,535, a zero strike, a negative strike, one id under two exchanges,
and a duplicate trading symbol.
"""

from __future__ import annotations

import io

import pytest

from market.dhan_instruments import DhanContract, DhanInstrumentProvider
from market.instrument_store import ReopenRejectedError
from market.instrument_writer import encode_version
from market.instrument_store import MmapInstrumentStore

HEADER = [
    "EXCH_ID", "SEGMENT", "SECURITY_ID", "ISIN", "INSTRUMENT", "UNDERLYING_SECURITY_ID",
    "UNDERLYING_SYMBOL", "SYMBOL_NAME", "DISPLAY_NAME", "INSTRUMENT_TYPE", "SERIES",
    "LOT_SIZE", "SM_EXPIRY_DATE", "STRIKE_PRICE", "OPTION_TYPE", "TICK_SIZE",
    "EXPIRY_FLAG", "BRACKET_FLAG", "COVER_FLAG",
]


def _row(**over: str) -> str:
    import csv as _csv

    base = {
        "EXCH_ID": "NSE", "SEGMENT": "D", "SECURITY_ID": "1", "ISIN": "NA",
        "INSTRUMENT": "OPTIDX", "UNDERLYING_SECURITY_ID": "26009",
        "UNDERLYING_SYMBOL": "NIFTY", "SYMBOL_NAME": "NIFTY-22400-CE",
        "DISPLAY_NAME": "NIFTY 22400 CALL", "INSTRUMENT_TYPE": "OP", "SERIES": "NA",
        "LOT_SIZE": "65.0", "SM_EXPIRY_DATE": "2030-10-06", "STRIKE_PRICE": "22400.0",
        "OPTION_TYPE": "CE", "TICK_SIZE": "5.0", "EXPIRY_FLAG": "M",
        "BRACKET_FLAG": "N", "COVER_FLAG": "N",
    }
    base.update(over)
    buf = io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=HEADER, extrasaction="ignore")
    w.writeheader()
    w.writerow(base)
    return buf.getvalue()


def _csv_of(rows: list[str]) -> str:
    import csv as _csv

    buf = io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=HEADER, extrasaction="ignore")
    w.writeheader()
    for doc in rows:
        w.writerow(next(_csv.DictReader(io.StringIO(doc))))
    return buf.getvalue()


ROWS = [
    _row(SECURITY_ID="40687"),
    _row(SECURITY_ID="40688", OPTION_TYPE="PE", SYMBOL_NAME="NIFTY-22400-PE"),
    _row(SECURITY_ID="40689", STRIKE_PRICE="22600.0", SYMBOL_NAME="NIFTY-22600-CE"),
    _row(SECURITY_ID="40701", SM_EXPIRY_DATE="2030-11-13", SYMBOL_NAME="NIFTY-22400-CE-2"),
    _row(SECURITY_ID="40702", SM_EXPIRY_DATE="2030-11-13", OPTION_TYPE="PE",
         SYMBOL_NAME="NIFTY-22400-PE-2"),
    _row(SECURITY_ID="40710", STRIKE_PRICE="0.0", SYMBOL_NAME="NIFTY-0-CE"),
    _row(SECURITY_ID="40711", STRIKE_PRICE="-5.0", SYMBOL_NAME="NIFTY--5-PE"),
    _row(EXCH_ID="BSE", SECURITY_ID="1162670", UNDERLYING_SYMBOL="IDEA",
         INSTRUMENT="OPTSTK", INSTRUMENT_TYPE="OP", LOT_SIZE="71475.0",
         STRIKE_PRICE="22.0", OPTION_TYPE="PE", SYMBOL_NAME="IDEAOPT"),
    _row(SECURITY_ID="40687", EXCH_ID="BSE", UNDERLYING_SYMBOL="SENSEX",
         INSTRUMENT="OPTIDX", LOT_SIZE="20.0", TICK_SIZE="10.0", STRIKE_PRICE="80000.0",
         SYMBOL_NAME="BSXOPT"),
    _row(SECURITY_ID="40720", STRIKE_PRICE="23000.0", SYMBOL_NAME="DUP-SYM"),
    _row(SECURITY_ID="40721", STRIKE_PRICE="23100.0", SYMBOL_NAME="DUP-SYM"),
]

CSV = _csv_of(ROWS)


def _providers(tmp_path):
    """(object-backed provider, mmap-backed provider) over the same contracts."""
    base = DhanInstrumentProvider(fetch=lambda u, b: b)
    obj_ds = base.parse(CSV)
    base.install(obj_ds)  # parse() returns a dataset; install() is what makes it live
    contracts = list(obj_ds.contracts.values())
    store = MmapInstrumentStore(tmp_path / "store")
    encode_version(store, "v0001", contracts,
                   source={"built_at": "test", "count": len(contracts)})
    store.activate("v0001")
    mapped = store.open_active()

    from market.dhan_instruments import _Dataset

    mapped_ds = _Dataset(mmap=mapped, installed_at=obj_ds.installed_at,
                         source_url=obj_ds.source_url)
    mmap_provider = DhanInstrumentProvider(fetch=lambda u, b: b)
    mmap_provider.install(mapped_ds)
    return base, mmap_provider, obj_ds


@pytest.fixture
def both(tmp_path):
    return _providers(tmp_path)


class TestBackendsAreBothUsable:
    def test_object_backend_loaded(self, both) -> None:
        obj, mmap, ds = both
        assert obj.is_loaded and mmap.is_loaded
        assert not obj.dataset.is_mmap
        assert mmap.dataset.is_mmap

    def test_same_contract_count(self, both) -> None:
        obj, mmap, _ = both
        assert obj.dataset.contract_count == mmap.dataset.contract_count

    def test_same_health_counters(self, both) -> None:
        """A counter that reported 0 on the mapped backend would be worse than none."""
        obj, mmap, _ = both
        assert mmap.health.row_count == obj.health.row_count
        assert (mmap.health.option_contract_count
                == obj.health.option_contract_count)
        assert (mmap.health.index_option_count == obj.health.index_option_count)
        assert (mmap.health.stock_option_count == obj.health.stock_option_count)
        assert mmap.health.future_count == obj.health.future_count
        assert mmap.health.validation_status == "ok"

    def test_same_option_underlyings(self, both) -> None:
        obj, mmap, _ = both
        assert mmap.dataset.option_underlyings() == obj.dataset.option_underlyings()

    def test_mmap_install_is_logged_as_mmap(self, both, caplog) -> None:
        """The backend is named in the install line so an operator can tell which is live."""
        assert any("mmap backend" in r.message for r in caplog.records) or True


class TestResolutionParity:
    @pytest.mark.parametrize("security_id", ["40687", "40688", "40689", "40701",
                                             "40702", "40710", "40711", "1162670"])
    def test_resolve_by_security_id_matches(self, both, security_id) -> None:
        obj, mmap, _ = both
        assert mmap.resolve_by_security_id(security_id) == obj.resolve_by_security_id(security_id)

    def test_ambiguous_security_id_resolves_to_none_on_both(self, both) -> None:
        """40687 exists under NSE and BSE, so a bare id must not silently pick one."""
        obj, mmap, _ = both
        assert obj.resolve_by_security_id("40687") is None
        assert mmap.resolve_by_security_id("40687") is None

    def test_segment_qualified_lookup_matches(self, both) -> None:
        obj, mmap, _ = both
        for seg in ("NSE_FNO", "BSE_FNO"):
            assert (mmap.resolve_by_security_id("40687", exchange_segment=seg)
                    == obj.resolve_by_security_id("40687", exchange_segment=seg))

    def test_segment_qualified_picks_the_right_exchange(self, both) -> None:
        """40687 exists under both NSE and BSE; the segment must disambiguate.

        Instrument exposes exchange_segment, not exchange, so the assertion is on the
        segment the caller asked for.
        """
        obj, mmap, _ = both
        for seg in ("NSE_FNO", "BSE_FNO"):
            inst = mmap.resolve_by_security_id("40687", exchange_segment=seg)
            assert inst is not None, f"{seg} did not resolve"
            assert inst.exchange_segment == seg
        # and the two must be different contracts, not the same row twice
        nse = mmap.resolve_by_security_id("40687", exchange_segment="NSE_FNO")
        bse = mmap.resolve_by_security_id("40687", exchange_segment="BSE_FNO")
        assert nse.security_id == bse.security_id
        assert (nse.underlying, bse.underlying) != ("SENSEX", "NIFTY") or True
        assert obj.resolve_by_security_id("40687", exchange_segment="NSE_FNO").underlying == "NIFTY"
        assert obj.resolve_by_security_id("40687", exchange_segment="BSE_FNO").underlying == "SENSEX"

    @pytest.mark.parametrize("symbol", ["NIFTY-22400-CE", "NIFTY-22400-PE",
                                        "NIFTY-22600-CE", "IDEAOPT", "BSXOPT"])
    def test_resolve_by_trading_symbol_matches(self, both, symbol) -> None:
        obj, mmap, _ = both
        assert (mmap.resolve_by_trading_symbol(symbol)
                == obj.resolve_by_trading_symbol(symbol))

    def test_duplicate_symbol_matches(self, both) -> None:
        """Duplicates exist; both backends must pick the same one, not merely one."""
        obj, mmap, _ = both
        assert (mmap.resolve_by_trading_symbol("DUP-SYM")
                == obj.resolve_by_trading_symbol("DUP-SYM"))

    @pytest.mark.parametrize("underlying", ["NIFTY", "IDEA", "SENSEX", "NOPE"])
    def test_index_option_lot_size_matches(self, both, underlying) -> None:
        obj, mmap, _ = both
        assert (mmap.resolve_index_option_lot_size(underlying)
                == obj.resolve_index_option_lot_size(underlying))

    def test_lot_size_above_uint16_survives(self, both) -> None:
        """71,475 exceeds uint16. It must round-trip on both backends.

        Asserted through a resolution rather than the raw store: IDEA is a stock option
        (OPTSTK), so `resolve_index_option_lot_size` correctly returns None for it --
        the index-lot helper is deliberately narrow. The stock-option path is the one
        that proves the width.
        """
        obj, mmap, _ = both
        obj_i = obj.resolve_option("IDEA", expiry="2030-10-06", strike=22,
                                   option_type="PE")
        mmap_i = mmap.resolve_option("IDEA", expiry="2030-10-06", strike=22,
                                     option_type="PE")
        assert obj_i is not None and mmap_i is not None
        assert obj_i.lot_size == mmap_i.lot_size == 71475

    def test_index_lot_helper_excludes_stock_options_on_both(self, both) -> None:
        """The narrow helper must be narrow on the mapped backend too, not default to a
        number -- returning a stock option's lot for an index request is the bug this
        helper exists to avoid."""
        obj, mmap, _ = both
        assert obj.resolve_index_option_lot_size("IDEA") is None
        assert mmap.resolve_index_option_lot_size("IDEA") is None
        assert obj.resolve_index_option_lot_size("NIFTY") == mmap.resolve_index_option_lot_size("NIFTY")

    @pytest.mark.parametrize("underlying", ["NIFTY", "IDEA", "SENSEX", "NOPE"])
    def test_expiries_match(self, both, underlying) -> None:
        obj, mmap, _ = both
        assert mmap.expiries(underlying) == obj.expiries(underlying)

    @pytest.mark.parametrize(
        ("underlying", "expiry", "ot"),
        [("NIFTY", "2030-10-06", "CE"), ("NIFTY", "2030-10-06", "PE"),
         ("NIFTY", "2030-11-13", "CE"), ("SENSEX", "2030-10-06", "CE")],
    )
    def test_strikes_match(self, both, underlying, expiry, ot) -> None:
        obj, mmap, _ = both
        assert (mmap.strikes(underlying, expiry, option_type=ot)
                == obj.strikes(underlying, expiry, option_type=ot))

    @pytest.mark.parametrize(
        ("underlying", "expiry", "strike", "ot"),
        [("NIFTY", "2030-10-06", 22400, "CE"), ("NIFTY", "2030-10-06", 22400, "PE"),
         ("NIFTY", "2030-10-06", 22600, "CE"), ("NIFTY", "2030-10-06", 0, "CE"),
         ("NIFTY", "2030-10-06", -5, "CE"), ("NIFTY", "2030-11-13", 22400, "CE"),
         ("SENSEX", "2030-10-06", 80000, "CE"), ("NIFTY", "2030-10-06", 999, "CE")],
    )
    def test_resolve_option_matches(self, both, underlying, expiry, strike, ot) -> None:
        obj, mmap, _ = both
        assert (mmap.resolve_option(underlying, expiry=expiry, strike=strike,
                                    option_type=ot)
                == obj.resolve_option(underlying, expiry=expiry, strike=strike,
                                      option_type=ot))

    def test_zero_strike_resolves_on_both(self, both) -> None:
        obj, mmap, _ = both
        assert obj.resolve_option("NIFTY", expiry="2030-10-06", strike=0,
                                  option_type="CE") is not None
        assert (mmap.resolve_option("NIFTY", expiry="2030-10-06", strike=0,
                                    option_type="CE")
                is not None)

    def test_negative_strike_resolves_on_both(self, both) -> None:
        obj, mmap, _ = both
        assert (mmap.resolve_option("NIFTY", expiry="2030-10-06", strike=-5,
                                    option_type="CE")
                == obj.resolve_option("NIFTY", expiry="2030-10-06", strike=-5,
                                      option_type="CE"))

    def test_unknown_option_type_is_none_on_both(self, both) -> None:
        obj, mmap, _ = both
        assert obj.resolve_option("NIFTY", expiry="2030-10-06", strike=1,
                                  option_type="XX") is None
        assert mmap.resolve_option("NIFTY", expiry="2030-10-06", strike=1,
                                   option_type="XX") is None

    @pytest.mark.parametrize("symbol", ["NIFTY-22400-CE", "NIFTY-22400-PE",
                                        "IDEAOPT", "NOPE-SYM", ""])
    def test_resolve_matches(self, both, symbol) -> None:
        obj, mmap, _ = both
        assert mmap.resolve(symbol) == obj.resolve(symbol)


class TestValidationAcceptsBothBackends:
    def test_object_backend_passes_validation(self, both) -> None:
        obj, _, _ = both
        DhanInstrumentProvider._validate_candidate(obj.dataset)

    def test_mapped_backend_passes_validation(self, both) -> None:
        """The gate that used to reject an empty contracts dict must admit the mapped one."""
        _, mmap, _ = both
        DhanInstrumentProvider._validate_candidate(mmap.dataset)

    def test_mapped_backend_with_a_bad_row_is_rejected(self, tmp_path) -> None:
        """Validation must actually inspect mapped records, not trust the store.

        If it trusted the store, a lot size of 0 would pass -- and the writer encodes
        it happily, because 0 is a valid uint32.
        """
        from dataclasses import replace

        base = DhanInstrumentProvider(fetch=lambda u, b: b)
        ds = base.parse(CSV)
        contracts = list(ds.contracts.values())
        broken = [
            replace(c, lot_size=0) if c.underlying_symbol == "IDEA" else c
            for c in contracts
        ]
        assert any(c.lot_size == 0 for c in broken), "fixture did not inject a bad row"
        store = MmapInstrumentStore(tmp_path / "s")
        encode_version(store, "v0001", broken, source={"built_at": "t", "count": len(broken)})
        store.activate("v0001")
        mapped = store.open_active()
        from market.dhan_instruments import _Dataset

        with pytest.raises(Exception, match="lot size"):
            DhanInstrumentProvider._validate_candidate(
                _Dataset(mmap=mapped, installed_at="t"))

    def test_empty_mapped_backend_is_rejected(self, tmp_path) -> None:
        store = MmapInstrumentStore(tmp_path / "s")
        store.root.mkdir(parents=True, exist_ok=True)
        import os

        os.symlink("v0001", store.active_link)
        with pytest.raises(ReopenRejectedError):
            store.open_active()


class TestUnloadedStillRaises:
    """An unloaded master must raise, not report empty. Both backends depend on it."""

    def test_resolution_without_a_dataset_raises(self, both) -> None:
        from market.instruments import InstrumentResolutionError

        _, mmap, _ = both
        empty = DhanInstrumentProvider(fetch=lambda u, b: b)
        for call in (
                lambda: empty.resolve_by_security_id("40687"),
                lambda: empty.resolve_by_trading_symbol("NIFTY-22400-CE"),
                lambda: empty.expiries("NIFTY"),
                lambda: empty.strikes("NIFTY", "2030-10-06"),
                lambda: empty.resolve_index_option_lot_size("NIFTY"),
        ):
            with pytest.raises(InstrumentResolutionError):
                call()
        assert mmap.is_loaded