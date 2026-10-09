"""The mmap store must answer exactly what the in-memory dataset answers.

This is the gate for replacing the object graph: parity, not speed and not size. If a
single lookup disagrees, the store is wrong no matter how little memory it uses.

The comparison is against the real production parser and a synthetic master that
exercises the cases that have actually bitten before:

  * security ids above 65,535 (uint16 truncation silently dropped 22,390 contracts)
  * lot sizes above 65,535 (max in the ingested universe is 71,475)
  * strike_price == 0.0, which `value or ""` once turned into a non-numeric
  * negative strikes, which are real in this master
  * one security id appearing under two exchanges, which is why identity is
    (exchange, segment, security_id) and not the id alone
  * duplicate trading symbols, which must stay a display index
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

import pytest

from market.dhan_instruments import DhanInstrumentProvider
from market.instrument_store import MmapInstrumentStore, ReopenRejectedError
from market.instrument_writer import build_from_contracts

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
        "LOT_SIZE": "65.0", "SM_EXPIRY_DATE": "2026-10-06", "STRIKE_PRICE": "22400.0",
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


# A date comfortably in the future, so an expiry-based filter cannot pass by accident.
FUTURE_1 = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()
FUTURE_2 = (datetime.now(UTC) + timedelta(days=60)).date().isoformat()

ROWS = [
    _row(SECURITY_ID="40687"),
    _row(SECURITY_ID="40688", OPTION_TYPE="PE", SYMBOL_NAME="NIFTY-22400-PE"),
    _row(SECURITY_ID="40689", STRIKE_PRICE="22600.0", SYMBOL_NAME="NIFTY-22600-CE"),
    _row(SECURITY_ID="40690", STRIKE_PRICE="22600.0", OPTION_TYPE="PE",
         SYMBOL_NAME="NIFTY-22600-PE"),
    _row(SECURITY_ID="40701", SM_EXPIRY_DATE=FUTURE_1, SYMBOL_NAME="NIFTY-22400-CE-2"),
    _row(SECURITY_ID="40702", SM_EXPIRY_DATE=FUTURE_1, OPTION_TYPE="PE",
         SYMBOL_NAME="NIFTY-22400-PE-2"),
    # strike exactly 0.0 -- the case `value or ""` broke
    _row(SECURITY_ID="40710", STRIKE_PRICE="0.0", SYMBOL_NAME="NIFTY-0-CE"),
    # negative strike -- real in this master, so the field must stay signed
    _row(SECURITY_ID="40711", STRIKE_PRICE="-5.0", SYMBOL_NAME="NIFTY--5-PE"),
    # security id above 65,535 and lot above 65,535
    _row(EXCH_ID="BSE", SECURITY_ID="1162670", UNDERLYING_SYMBOL="IDEA",
         INSTRUMENT="OPTSTK", INSTRUMENT_TYPE="OP", LOT_SIZE="71475.0",
         STRIKE_PRICE="22.0", OPTION_TYPE="PE", SYMBOL_NAME="IDEAOPT",
         DISPLAY_NAME="IDEA 22 PUT"),
    # same security id, different exchange: identity is not the id alone
    _row(SECURITY_ID="40687", EXCH_ID="BSE", UNDERLYING_SYMBOL="SENSEX",
         INSTRUMENT="OPTIDX", LOT_SIZE="20.0", TICK_SIZE="10.0", STRIKE_PRICE="80000.0",
         SYMBOL_NAME="BSXOPT", DISPLAY_NAME="SENSEX 80000 CALL"),
    # duplicate trading symbol across two contracts
    _row(SECURITY_ID="40720", STRIKE_PRICE="23000.0", SYMBOL_NAME="DUP-SYM"),
    _row(SECURITY_ID="40721", STRIKE_PRICE="23100.0", SYMBOL_NAME="DUP-SYM"),
    _row(SECURITY_ID="40722", SM_EXPIRY_DATE=FUTURE_2, STRIKE_PRICE="22400.0",
         SYMBOL_NAME="NIFTY-22400-CE-3"),
]

CSV = _csv_of(ROWS)


@pytest.fixture
def memory_dataset():
    p = DhanInstrumentProvider(fetch=lambda url, body: body)
    return p.parse(CSV)


@pytest.fixture
def mmap_store(tmp_path, memory_dataset):
    store = build_from_contracts(
        tmp_path / "store", "v0001",
        list(memory_dataset.contracts.values()),
        source={"built_at": "test", "count": len(memory_dataset.contracts)},
    )
    return store.open_active()


class TestCountsAndTables:
    def test_same_record_count(self, memory_dataset, mmap_store) -> None:
        assert len(mmap_store) == len(memory_dataset.contracts)

    def test_same_option_underlyings(self, memory_dataset, mmap_store) -> None:
        assert mmap_store.option_underlyings() == memory_dataset.option_underlyings()


class TestSecurityIdentityParity:
    def test_every_contract_resolves_by_exchange_segment_id(self, memory_dataset, mmap_store) -> None:
        checked = 0
        for (exchange, segment, sid), contract in memory_dataset.contracts.items():
            slot = mmap_store.slot_for_security(exchange, segment, sid)
            assert slot is not None, f"{exchange}/{segment}/{sid} missing from the index"
            got = mmap_store.fields(slot)
            assert got["security_id"] == int(contract.security_id)
            assert got["exchange"] == exchange
            assert got["exchange_segment"] == segment
            assert got["underlying_symbol"] == contract.underlying_symbol
            assert got["expiry_date"] == contract.expiry_date
            assert got["option_type"] == (contract.option_type or "")
            assert got["lot_size"] == int(contract.lot_size)
            assert got["trading_symbol"] == (contract.trading_symbol or "")
            checked += 1
        assert checked == len(memory_dataset.contracts)

    def test_unknown_identity_returns_none(self, mmap_store) -> None:
        assert mmap_store.slot_for_security("NSE", "NSE_FNO", "999999999") is None

    def test_bare_security_id_returns_every_exchange(self, mmap_store) -> None:
        """A security id is not globally unique; both candidates must come back."""
        slots = mmap_store.slots_for_security_id("40687")
        assert len(slots) == 2, f"expected NSE and BSE candidates, got {slots}"

    def test_security_id_above_uint16_survives(self, mmap_store) -> None:
        """1,162,670 wrapped at uint16. This is the guard against that regression."""
        slot = mmap_store.slot_for_security("BSE", "BSE_FNO", "1162670")
        assert slot is not None
        assert mmap_store.fields(slot)["security_id"] == 1162670

    def test_lot_size_above_uint16_survives(self, mmap_store) -> None:
        """71,475 is the real ingested maximum."""
        slot = mmap_store.slot_for_security("BSE", "BSE_FNO", "1162670")
        assert mmap_store.fields(slot)["lot_size"] == 71475


class TestOptionIdentityParity:
    def test_every_option_resolves(self, memory_dataset, mmap_store) -> None:
        for (exchange, segment, sid), c in memory_dataset.contracts.items():
            if not c.option_type:
                continue
            slot = mmap_store.slot_for_option(
                c.underlying_symbol, c.expiry_date,
                int(round(float(c.strike_price or 0) * 100)), c.option_type,
            )
            assert slot is not None, f"{c.underlying_symbol} {c.expiry_date} {c.strike_price} {c.option_type}"
            got = mmap_store.fields(slot)
            assert got["security_id"] == int(c.security_id)
            assert got["trading_symbol"] == c.trading_symbol

    def test_ce_and_pe_do_not_collapse(self, mmap_store) -> None:
        ce = mmap_store.slot_for_option("NIFTY", "2026-10-06", 2240000, "CE")
        pe = mmap_store.slot_for_option("NIFTY", "2026-10-06", 2240000, "PE")
        assert ce is not None and pe is not None
        assert ce != pe

    def test_expiry_separates(self, mmap_store) -> None:
        a = mmap_store.slot_for_option("NIFTY", "2026-10-06", 2240000, "CE")
        b = mmap_store.slot_for_option("NIFTY", FUTURE_1, 2240000, "CE")
        c = mmap_store.slot_for_option("NIFTY", FUTURE_2, 2240000, "CE")
        assert len({a, b, c}) == 3

    def test_strike_separates(self, mmap_store) -> None:
        a = mmap_store.slot_for_option("NIFTY", "2026-10-06", 2240000, "CE")
        b = mmap_store.slot_for_option("NIFTY", "2026-10-06", 2260000, "CE")
        assert a is not None and b is not None and a != b

    def test_zero_strike_stays_numeric_zero(self, mmap_store) -> None:
        """A 0.0 strike must decode to 0, not to "" or None."""
        slot = mmap_store.slot_for_option("NIFTY", "2026-10-06", 0, "CE")
        assert slot is not None
        f = mmap_store.fields(slot)
        assert f["strike_scaled"] == 0
        assert f["strike_scaled"] / 100 == 0.0

    def test_negative_strike_stays_negative(self, mmap_store) -> None:
        """strike_price -5.0 at 1/100 scale. Real cases exist in this master, so the
        field must stay signed: an unsigned type would either raise or wrap.

        The fixture row inherits OPTION_TYPE from the base row, which is CE -- the
        symbol name says PE, the CSV column says CE, and the CSV column is what counts.
        """
        slot = mmap_store.slot_for_option("NIFTY", "2026-10-06", -500, "CE")
        assert slot is not None, "a negative strike must be findable"
        f = mmap_store.fields(slot)
        assert f["strike_scaled"] == -500
        assert f["strike_scaled"] / 100 == pytest.approx(-5.0)


class TestSymbolParity:
    def test_unique_symbol_resolves(self, memory_dataset, mmap_store) -> None:
        # by_trading_symbol is keyed by the bare string, not a tuple.
        contract = memory_dataset.by_trading_symbol["NIFTY-22400-CE"]
        slot = mmap_store.slot_for_symbol("NIFTY-22400-CE")
        assert slot is not None
        got = mmap_store.fields(slot)
        assert got["trading_symbol"] == "NIFTY-22400-CE"
        assert got["security_id"] == int(contract.security_id)

    def test_duplicate_symbol_returns_every_candidate(self, mmap_store) -> None:
        """Duplicates are expected data, not corruption, and must all be visible."""
        slots = mmap_store.slots_for_symbol("DUP-SYM")
        assert len(slots) == 2
        strikes = {mmap_store.fields(s)["strike_scaled"] for s in slots}
        assert strikes == {2300000, 2310000}

    def test_ambiguous_symbol_picks_the_lowest_slot(self, mmap_store) -> None:
        """The documented behaviour, measured rather than assumed."""
        picked = mmap_store.slot_for_symbol("DUP-SYM")
        assert picked == min(mmap_store.slots_for_symbol("DUP-SYM"))

    def test_unknown_symbol_returns_none(self, mmap_store) -> None:
        assert mmap_store.slot_for_symbol("NO-SUCH-SYMBOL") is None


class TestUnderlyingScan:
    def test_returns_only_that_underlying(self, mmap_store) -> None:
        slots = list(mmap_store.iter_underlying("NIFTY"))
        assert slots
        assert {mmap_store.fields(s)["underlying_symbol"] for s in slots} == {"NIFTY"}

    def test_every_option_contract_is_reachable(self, memory_dataset, mmap_store) -> None:
        seen = set()
        for u in mmap_store.option_underlyings():
            seen.update(mmap_store.iter_underlying(u))
        expected = {
            i for i, c in enumerate(memory_dataset.contracts.values()) if c.option_type
        }
        assert seen == expected, f"missing {len(expected - seen)} option contracts"


class TestFailsClosed:
    def test_truncated_payload_is_rejected(self, tmp_path, memory_dataset) -> None:
        store = build_from_contracts(tmp_path / "s", "v0001",
                                      list(memory_dataset.contracts.values()),
                                      source={"built_at": "t", "count": 1})
        p = store.root / "v0001" / "records.dat"
        with open(p, "r+b") as fh:
            fh.truncate(p.stat().st_size - 37)
        with pytest.raises(ReopenRejectedError, match="size"):
            store.open_active()

    def test_flipped_payload_byte_is_rejected(self, tmp_path, memory_dataset) -> None:
        store = build_from_contracts(tmp_path / "s", "v0001",
                                      list(memory_dataset.contracts.values()),
                                      source={"built_at": "t", "count": 1})
        p = store.root / "v0001" / "opt.dat"
        with open(p, "r+b") as fh:
            fh.seek(9)
            b = fh.read(1)
            fh.seek(9)
            fh.write(bytes([b[0] ^ 0xFF]))
        with pytest.raises(ReopenRejectedError, match="CRC32"):
            store.open_active()

    def test_missing_index_is_rejected(self, tmp_path, memory_dataset) -> None:
        store = build_from_contracts(tmp_path / "s", "v0001",
                                      list(memory_dataset.contracts.values()),
                                      source={"built_at": "t", "count": 1})
        (store.root / "v0001" / "sym.dat").unlink()
        with pytest.raises(ReopenRejectedError, match="missing"):
            store.open_active()

    def test_dangling_active_pointer_is_rejected(self, tmp_path) -> None:
        store = MmapInstrumentStore(tmp_path / "s")
        import os

        os.symlink("v9999", store.active_link)
        with pytest.raises(ReopenRejectedError, match="missing"):
            store.open_active()

    def test_pointer_traversal_is_rejected(self, tmp_path) -> None:
        store = MmapInstrumentStore(tmp_path / "s")
        import os

        os.symlink("../../etc", store.active_link)
        with pytest.raises(ReopenRejectedError, match="not a version name"):
            store.open_active()