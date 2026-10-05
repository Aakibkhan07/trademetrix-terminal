"""Tests for the authoritative Dhan instrument master.

The CSV fixtures here reproduce the *observed shape* of Dhan's published detailed
master, including its quirks, because those quirks are what the parser must survive:

* ``LOT_SIZE`` arrives as a float string (``"65.0"``), so a whole-valued float must be
  accepted and narrowed -- while a genuine fractional value must be rejected.
* ``STRIKE_PRICE`` can be negative (currency futures) and has five decimal places, so it
  must not be assumed positive or integral.
* ``OPTION_TYPE`` is ``CE``/``PE`` for options and empty for everything else.
* ``SECURITY_ID`` is **not globally unique**: the same id appears under different
  exchanges and segments. Uniqueness is ``(exchange, exchange_segment, security_id)``.
  Measured against the real file: 14,626 repeated security ids, zero repeated triples.

Every test runs against a local fixture. No network, no database, no broker.
"""

import asyncio
import csv
import io

import pytest

from market.dhan_instruments import (
    DHAN_INSTRUMENT_MASTER_URL,
    DhanInstrumentProvider,
    DhanMasterValidationError,
    compare_with_reference,
    parse_lot_size,
)
from market.instruments import instrument_resolver

HEADER = [
    "EXCH_ID", "SEGMENT", "SECURITY_ID", "ISIN", "INSTRUMENT", "UNDERLYING_SECURITY_ID",
    "UNDERLYING_SYMBOL", "SYMBOL_NAME", "DISPLAY_NAME", "INSTRUMENT_TYPE", "SERIES",
    "LOT_SIZE", "SM_EXPIRY_DATE", "STRIKE_PRICE", "OPTION_TYPE", "TICK_SIZE",
    "EXPIRY_FLAG", "BRACKET_FLAG", "COVER_FLAG",
]


def row(**over) -> dict:
    base = {
        "EXCH_ID": "NSE", "SEGMENT": "D", "SECURITY_ID": "1", "ISIN": "NA",
        "INSTRUMENT": "OPTIDX", "UNDERLYING_SECURITY_ID": "26009",
        "UNDERLYING_SYMBOL": "NIFTY", "SYMBOL_NAME": "NIFTY-Oct2026-24000-CE",
        "DISPLAY_NAME": "NIFTY 28 OCT 24000 CALL", "INSTRUMENT_TYPE": "OP", "SERIES": "NA",
        "LOT_SIZE": "65.0", "SM_EXPIRY_DATE": "2026-10-28", "STRIKE_PRICE": "24000.00000",
        "OPTION_TYPE": "CE", "TICK_SIZE": "5.0000", "EXPIRY_FLAG": "M",
        "BRACKET_FLAG": "N", "COVER_FLAG": "N",
    }
    base.update(over)
    return base


def to_csv(rows: list[dict], header: list[str] | None = None) -> str:
    cols = header or HEADER
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue()


def sample_master() -> list[dict]:
    """A small but structurally complete master: index, BSE, and stock options."""
    return [
        row(SECURITY_ID="40749", UNDERLYING_SYMBOL="NIFTY", UNDERLYING_SECURITY_ID="256",
            SYMBOL_NAME="NIFTY-Oct2026-24000-CE", DISPLAY_NAME="NIFTY 28 OCT 24000 CALL",
            STRIKE_PRICE="24000.00000", OPTION_TYPE="CE", LOT_SIZE="65.0"),
        row(SECURITY_ID="40750", SYMBOL_NAME="NIFTY-Oct2026-24000-PE",
            DISPLAY_NAME="NIFTY 28 OCT 24000 PUT", OPTION_TYPE="PE"),
        row(SECURITY_ID="40751", SYMBOL_NAME="NIFTY-Nov2026-24000-CE",
            DISPLAY_NAME="NIFTY 25 NOV 24000 CALL", SM_EXPIRY_DATE="2026-11-25",
            OPTION_TYPE="CE"),
        row(SECURITY_ID="40760", UNDERLYING_SYMBOL="BANKNIFTY", UNDERLYING_SECURITY_ID="26009",
            SYMBOL_NAME="BANKNIFTY-Oct2026-64000-CE", DISPLAY_NAME="BANKNIFTY 28 OCT 64000 CALL",
            STRIKE_PRICE="64000.00000", LOT_SIZE="30.0", OPTION_TYPE="CE"),
        # BSE index option: must resolve to BSE_FNO, never NSE_EQ.
        row(EXCH_ID="BSE", SECURITY_ID="889114", UNDERLYING_SYMBOL="SENSEX",
            UNDERLYING_SECURITY_ID="1", SYMBOL_NAME="BSX-Oct2026-74000-PE",
            DISPLAY_NAME="SENSEX 28 OCT 74000 PUT", STRIKE_PRICE="74000.00000",
            LOT_SIZE="20.0", OPTION_TYPE="PE"),
        # Stock option, NSE.
        row(INSTRUMENT="OPTSTK", SECURITY_ID="134014", UNDERLYING_SYMBOL="JSWSTEEL",
            UNDERLYING_SECURITY_ID="500", SYMBOL_NAME="JSWSTEEL-Oct2026-1250-CE",
            DISPLAY_NAME="JSWSTEEL 28 OCT 1250 CALL", STRIKE_PRICE="1250.00000",
            LOT_SIZE="675.0", OPTION_TYPE="CE"),
        row(INSTRUMENT="OPTSTK", SECURITY_ID="134015", UNDERLYING_SYMBOL="JSWSTEEL",
            UNDERLYING_SECURITY_ID="500", SYMBOL_NAME="JSWSTEEL-Oct2026-1250-PE",
            DISPLAY_NAME="JSWSTEEL 28 OCT 1250 PUT", STRIKE_PRICE="1250.00000",
            LOT_SIZE="675.0", OPTION_TYPE="PE"),
        # Index future: no option type, no strike.
        row(INSTRUMENT="FUTIDX", SECURITY_ID="49081", UNDERLYING_SYMBOL="NIFTY",
            SYMBOL_NAME="NIFTY28OCTFUT", DISPLAY_NAME="NIFTY 28 OCT FUT",
            LOT_SIZE="65.0", OPTION_TYPE="", STRIKE_PRICE="", SM_EXPIRY_DATE="2026-10-28"),
        # Equity: ingested shape but should be skipped by the family filter.
        row(EXCH_ID="NSE", SEGMENT="E", INSTRUMENT="EQUITY", SECURITY_ID="500325",
            UNDERLYING_SYMBOL="", UNDERLYING_SECURITY_ID="", SYMBOL_NAME="RELIANCE",
            DISPLAY_NAME="RELIANCE", INSTRUMENT_TYPE="EQ", LOT_SIZE="1.0",
            OPTION_TYPE="", STRIKE_PRICE="", SM_EXPIRY_DATE=""),
    ]


def loaded_provider(rows: list[dict] | None = None, **kwargs) -> DhanInstrumentProvider:
    text = to_csv(rows if rows is not None else sample_master())
    provider = DhanInstrumentProvider(fetch=lambda url, timeout: text, **kwargs)
    asyncio.run(provider.refresh())
    return provider


# ──────────────────────────────────────────────────────────────────────────────
# parse_lot_size: the strictness the repair depends on
# ──────────────────────────────────────────────────────────────────────────────


class TestLotSizeParsing:
    @pytest.mark.parametrize(("raw", "expected"), [
        ("65.0", 65), ("30.0", 30), ("1.0", 1), (65, 65), (65.0, 65),
        (" 120.0 ", 120), ("25", 25),
    ])
    def test_accepts_whole_valued_floats(self, raw, expected):
        """Dhan publishes lot sizes as floats. Rejecting them would reject everything."""
        assert parse_lot_size(raw, where="t") == expected

    @pytest.mark.parametrize("raw", [
        None, "", "   ", True, False, 0, -1, -65.0, "abc", "30.5", 30.5,
        float("nan"), float("inf"), float("-inf"), "nan", "inf", [65], {"lot": 65},
    ])
    def test_rejects_anything_that_is_not_a_positive_whole_number(self, raw):
        """Including booleans, which are ints in Python and would become lot size 1."""
        with pytest.raises(DhanMasterValidationError):
            parse_lot_size(raw, where="t")

    def test_a_fractional_lot_size_is_rejected_not_rounded(self):
        with pytest.raises(DhanMasterValidationError, match="fractional"):
            parse_lot_size("30.5", where="t")

    def test_int_is_not_applied_before_validation(self):
        """`int(30.5)` is 30, which would turn bad input into a valid-looking contract."""
        with pytest.raises(DhanMasterValidationError):
            parse_lot_size(30.5, where="t")


# ──────────────────────────────────────────────────────────────────────────────
# Download: an HTTP 200 that is not a master must not install anything
# ──────────────────────────────────────────────────────────────────────────────


class TestDownloadValidation:
    def _provider(self, body: str) -> DhanInstrumentProvider:
        return DhanInstrumentProvider(fetch=lambda url, timeout: body)

    def test_an_html_error_page_is_rejected(self):
        # Large enough to clear the size check, so the HTML check is what fires. A
        # small HTML body trips the size check first, which is also correct but is
        # tested separately.
        body = "<!DOCTYPE html><html><body>502 Bad Gateway</body></html>" + "\n" * 60
        with pytest.raises(DhanMasterValidationError, match="HTML"):
            self._provider(body)._validate_download(body)

    def test_an_empty_body_is_rejected(self):
        with pytest.raises(DhanMasterValidationError, match="empty"):
            self._provider("")._validate_download("")

    def test_the_size_bounds_live_on_the_transport_not_the_parser(self):
        """A byte floor exists to catch a broken HTTP response, so it is enforced there.

        Asserting it is on the transport also documents why a small injected fixture is
        still parseable: there is no HTTP response to have been truncated.
        """
        from market import dhan_instruments as mod

        assert mod.MIN_DOWNLOAD_BYTES > 0
        assert mod.MAX_DOWNLOAD_BYTES > mod.MIN_DOWNLOAD_BYTES
        import inspect

        transport = inspect.getsource(mod.DhanInstrumentProvider._http_fetch)
        assert "MIN_DOWNLOAD_BYTES" in transport and "MAX_DOWNLOAD_BYTES" in transport
        assert "MIN_DOWNLOAD_BYTES" not in inspect.getsource(mod.DhanInstrumentProvider._validate_download)

    def test_a_non_csv_header_is_rejected(self):
        with pytest.raises(DhanMasterValidationError, match="CSV"):
            self._provider("a header with no commas\nand more text\n" * 40)._validate_download(
                "a header with no commas\nand more text\n" * 40)

    def test_http_errors_are_retried_then_raised(self, monkeypatch):
        attempts = {"n": 0}

        def _boom(url, timeout):
            attempts["n"] += 1
            raise DhanMasterValidationError("HTTP 503")

        provider = DhanInstrumentProvider(fetch=_boom)
        monkeypatch.setattr("market.dhan_instruments.DOWNLOAD_ATTEMPTS", 2)
        monkeypatch.setattr("market.dhan_instruments.DOWNLOAD_BACKOFF_SECONDS", 0)
        with pytest.raises(DhanMasterValidationError, match="after 2 attempts"):
            asyncio.run(provider.download())
        assert attempts["n"] == 2

    def test_a_transient_failure_is_retried_and_can_succeed(self, monkeypatch):
        state = {"n": 0}

        def _flaky(url, timeout):
            state["n"] += 1
            if state["n"] == 1:
                raise RuntimeError("connection reset")
            return to_csv(sample_master())

        provider = DhanInstrumentProvider(fetch=_flaky)
        monkeypatch.setattr("market.dhan_instruments.DOWNLOAD_BACKOFF_SECONDS", 0)
        text = asyncio.run(provider.download())
        assert "EXCH_ID" in text
        assert state["n"] == 2

    def test_default_url_is_the_documented_detailed_master(self):
        assert DhanInstrumentProvider()._url == DHAN_INSTRUMENT_MASTER_URL
        assert DHAN_INSTRUMENT_MASTER_URL.endswith("api-scrip-master-detailed.csv")


# ──────────────────────────────────────────────────────────────────────────────
# Parse: required columns, row validation, duplicates
# ──────────────────────────────────────────────────────────────────────────────


class TestParsing:
    def test_a_valid_master_parses(self):
        provider = loaded_provider()
        assert provider.health.validation_status == "ok"
        assert provider.health.row_count == 8  # the equity row is filtered out

    @pytest.mark.parametrize("missing", ["SECURITY_ID", "LOT_SIZE", "OPTION_TYPE",
                                         "SM_EXPIRY_DATE", "STRIKE_PRICE", "SEGMENT",
                                         "EXCH_ID", "INSTRUMENT"])
    def test_a_missing_required_column_fails_the_whole_refresh(self, missing):
        """One absent column invalidates the file; it is not parsed partially.

        refresh() records the failure rather than raising, because its contract is that
        a bad download never destroys the dataset already serving.
        """
        cols = [c for c in HEADER if c != missing]
        provider = DhanInstrumentProvider(fetch=lambda u, t: to_csv(sample_master(), cols))
        asyncio.run(provider.refresh())
        assert provider.health.validation_status == "failed"
        assert "missing required columns" in provider.health.error
        assert provider.dataset is None
        assert provider.health.row_count == 0

    def test_an_empty_dataset_is_refused(self):
        provider = DhanInstrumentProvider(fetch=lambda u, t: to_csv([]))
        asyncio.run(provider.refresh())
        assert provider.health.validation_status == "failed"
        assert "no usable contracts" in provider.health.error
        assert provider.dataset is None

    def test_a_dataset_of_only_unmappable_segments_is_refused(self):
        """Unknown (exchange, segment) pairs must not be guessed at."""
        rows = [row(SEGMENT="Z")]
        provider = DhanInstrumentProvider(fetch=lambda u, t: to_csv(rows))
        asyncio.run(provider.refresh())
        assert provider.health.validation_status == "failed"
        assert provider.dataset is None

    def test_equity_rows_are_excluded(self):
        provider = loaded_provider()
        symbols = set(provider.dataset.by_trading_symbol)
        assert "RELIANCE" not in symbols

    def test_duplicate_contract_keys_are_rejected_not_merged(self):
        """The verified key is (exchange, segment, security id); a repeat is a data fault."""
        rows = sample_master()
        rows.append(row(SECURITY_ID="40749", SYMBOL_NAME="DUPLICATE"))
        provider = DhanInstrumentProvider(fetch=lambda u, t: to_csv(rows))
        asyncio.run(provider.refresh())
        keys = list(provider.dataset.by_trading_symbol)
        assert "DUPLICATE" not in keys
        assert provider.dataset.contracts[("NSE", "NSE_FNO", "40749")].trading_symbol != "DUPLICATE"

    def test_the_same_security_id_under_two_exchanges_is_not_a_duplicate(self):
        """Dhan really does reuse security ids across exchanges. Both must survive."""
        rows = [
            row(EXCH_ID="NSE", SECURITY_ID="513496", SYMBOL_NAME="NSE-CONTRACT"),
            row(EXCH_ID="MCX", SEGMENT="M", SECURITY_ID="513496", INSTRUMENT="OPTFUT",
                UNDERLYING_SYMBOL="GOLD", SYMBOL_NAME="MCX-CONTRACT", OPTION_TYPE="CE"),
        ]
        provider = DhanInstrumentProvider(fetch=lambda u, t: to_csv(rows))
        asyncio.run(provider.refresh())
        assert provider.dataset.contracts[("NSE", "NSE_FNO", "513496")].trading_symbol == "NSE-CONTRACT"
        assert provider.dataset.contracts[("MCX", "MCX_FNO", "513496")].trading_symbol == "MCX-CONTRACT"

    @pytest.mark.parametrize("over", [
        {"SECURITY_ID": ""},
        {"EXCH_ID": ""},
        {"SEGMENT": ""},
        {"LOT_SIZE": "0.0"},
        {"LOT_SIZE": "-65.0"},
        {"LOT_SIZE": "True"},
        {"LOT_SIZE": "30.5"},
        {"LOT_SIZE": "abc"},
        {"OPTION_TYPE": ""},
        {"OPTION_TYPE": "XX"},
        {"UNDERLYING_SYMBOL": ""},
        {"UNDERLYING_SECURITY_ID": ""},
        {"SM_EXPIRY_DATE": ""},
        {"STRIKE_PRICE": ""},
    ])
    def test_invalid_rows_are_dropped_not_ingested(self, over):
        bad = {"SECURITY_ID": "99999", "SYMBOL_NAME": "BAD", **over}
        rows = sample_master() + [row(**bad)]
        provider = DhanInstrumentProvider(fetch=lambda u, t: to_csv(rows))
        asyncio.run(provider.refresh())
        assert "BAD" not in provider.dataset.by_trading_symbol

    def test_a_non_option_row_carrying_an_option_type_is_dropped(self):
        rows = sample_master() + [row(INSTRUMENT="FUTIDX", SECURITY_ID="88888",
                                      SYMBOL_NAME="BADFUT", OPTION_TYPE="CE",
                                      STRIKE_PRICE="")]
        provider = DhanInstrumentProvider(fetch=lambda u, t: to_csv(rows))
        asyncio.run(provider.refresh())
        assert "BADFUT" not in provider.dataset.by_trading_symbol

    def test_negative_strike_is_accepted(self):
        """Currency futures carry negative strikes in the real master."""
        rows = [row(INSTRUMENT="FUTCUR", UNDERLYING_SYMBOL="USDINR", SECURITY_ID="70001",
                    SYMBOL_NAME="USDINR-FUT", OPTION_TYPE="", STRIKE_PRICE="-0.01000",
                    LOT_SIZE="1.0")]
        provider = DhanInstrumentProvider(fetch=lambda u, t: to_csv(rows))
        asyncio.run(provider.refresh())
        assert provider.dataset.by_trading_symbol["USDINR-FUT"].strike_price == pytest.approx(-0.01)


# ──────────────────────────────────────────────────────────────────────────────
# Exact contract resolution
# ──────────────────────────────────────────────────────────────────────────────


class TestContractResolution:
    def test_nifty_call_and_put_resolve_to_distinct_contracts(self):
        p = loaded_provider()
        ce = p.resolve_option("NIFTY", expiry="2026-10-28", strike=24000, option_type="CE")
        pe = p.resolve_option("NIFTY", expiry="2026-10-28", strike=24000, option_type="PE")
        assert ce.security_id == "40749" and pe.security_id == "40750"
        assert ce.lot_size == pe.lot_size == 65
        assert ce.option_type == "CE" and pe.option_type == "PE"

    def test_sensex_resolves_to_the_bse_segment_not_cash_equity(self):
        p = loaded_provider()
        inst = p.resolve_option("SENSEX", expiry="2026-10-28", strike=74000, option_type="PE")
        assert inst is not None
        assert inst.exchange_segment == "BSE_FNO"
        assert inst.lot_size == 20

    def test_stock_option_carries_its_own_lot_size(self):
        p = loaded_provider()
        ce = p.resolve_option("JSWSTEEL", expiry="2026-10-28", strike=1250, option_type="CE")
        pe = p.resolve_option("JSWSTEEL", expiry="2026-10-28", strike=1250, option_type="PE")
        assert ce.lot_size == 675 and pe.lot_size == 675
        assert ce.security_id != pe.security_id

    def test_banknifty_lot_size_comes_from_the_master(self):
        p = loaded_provider()
        inst = p.resolve_option("BANKNIFTY", expiry="2026-10-28", strike=64000, option_type="CE")
        assert inst.lot_size == 30

    def test_expiry_and_strike_are_part_of_identity(self):
        p = loaded_provider()
        oct_c = p.resolve_option("NIFTY", expiry="2026-10-28", strike=24000, option_type="CE")
        nov_c = p.resolve_option("NIFTY", expiry="2026-11-25", strike=24000, option_type="CE")
        assert oct_c.security_id != nov_c.security_id

    @pytest.mark.parametrize(("expiry", "strike", "otype"), [
        ("2026-10-28", 99999, "CE"),
        ("2026-01-01", 24000, "CE"),
        ("2026-10-28", "not-a-number", "CE"),
        ("2026-10-28", 24000, "XX"),
    ])
    def test_an_unmatched_request_resolves_to_nothing(self, expiry, strike, otype):
        p = loaded_provider()
        assert p.resolve_option("NIFTY", expiry=expiry, strike=strike, option_type=otype) is None

    def test_an_expired_contract_is_excluded_from_eligible_expiries(self):
        rows = [row(SM_EXPIRY_DATE="2020-01-16"), row(SECURITY_ID="40752",
                                                      SM_EXPIRY_DATE="2099-12-31")]
        p = loaded_provider(rows)
        eligible = p.expiries("NIFTY", option=True)
        assert eligible == ["2099-12-31"]

    def test_strikes_are_read_from_the_master_not_invented(self):
        p = loaded_provider()
        assert p.strikes("NIFTY", "2026-10-28", option_type="CE") == [24000.0]

    def test_index_option_lot_size_is_read_from_a_real_row(self):
        p = loaded_provider()
        assert p.resolve_index_option_lot_size("NIFTY") == 65
        assert p.resolve_index_option_lot_size("BANKNIFTY") == 30
        assert p.resolve_index_option_lot_size("NOSUCHINDEX") is None

    def test_future_resolution(self):
        p = loaded_provider()
        inst = p.resolve_future("NIFTY", expiry="2026-10-28")
        assert inst is not None and inst.security_id == "49081" and inst.instrument_type == "FUT"

    def test_symbol_entry_point_accepts_the_trading_symbol(self):
        p = loaded_provider()
        assert p.resolve("NIFTY-Oct2026-24000-CE").security_id == "40749"
        assert p.resolve("NSE:NIFTY-Oct2026-24000-CE").security_id == "40749"
        assert p.resolve("40749").security_id == "40749"

    def test_an_unknown_symbol_resolves_to_nothing(self):
        p = loaded_provider()
        assert p.resolve("NSE:RELIANCE-EQ") is None
        assert p.resolve("") is None
        assert p.resolve("nonsense") is None


# ──────────────────────────────────────────────────────────────────────────────
# Lot-size authority
# ──────────────────────────────────────────────────────────────────────────────


class TestLotSizeAuthority:
    def test_lot_size_is_never_a_constant_when_the_master_answers(self):
        from tests.fixtures.lot_size_reference import INDEX_OPTIONS

        p = loaded_provider()
        for underlying, reference in INDEX_OPTIONS.items():
            rows = [row(SECURITY_ID="1", UNDERLYING_SYMBOL=underlying,
                        SYMBOL_NAME=f"{underlying}-CE", LOT_SIZE=f"{reference}.0")]
            one = loaded_provider(rows)
            assert one.resolve_index_option_lot_size(underlying) == reference

    def test_dhan_wins_over_a_reference_that_disagrees(self):
        """A deliberately wrong reference must not overwrite the master."""
        from market.dhan_instruments import dhan_instrument_provider

        p = loaded_provider()
        saved = dhan_instrument_provider._dataset
        try:
            dhan_instrument_provider._dataset = p.dataset
            discrepancies = compare_with_reference({"NIFTY": 999})
            assert discrepancies and discrepancies[0]["dhan"] == 65
            assert discrepancies[0]["reference"] == 999
            # And the master value is unchanged.
            assert dhan_instrument_provider.resolve_index_option_lot_size("NIFTY") == 65
        finally:
            dhan_instrument_provider._dataset = saved

    def test_hardcoded_lot_sizes_stay_absent(self):
        """Owned by test_lot_size_reference_isolation.py.

        An earlier draft of this test grepped for `LOT_SIZES` and tried to skip
        docstring mentions with a hand-written condition. It skipped too much and would
        have passed on a file that both defined and used a table. The tokenising guard in
        the isolation module is the real check; this only asserts it is present.
        """
        import pathlib

        guard = pathlib.Path(__file__).parent / "test_lot_size_reference_isolation.py"
        text = guard.read_text(encoding="utf-8")
        assert "code_line_numbers" in text
        assert "tokenize" in text

    def test_missing_master_metadata_fails_closed(self):
        """No provider data means no lot size, and no order."""
        from market.instruments import InstrumentResolutionError

        p = DhanInstrumentProvider()
        assert p.is_loaded() is False
        # Direct contract lookups raise, so a caller cannot mistake "no master" for
        # "no such contract".
        for call in (
            lambda: p.resolve_index_option_lot_size("NIFTY"),
            lambda: p.resolve_option("NIFTY", expiry="2026-10-28", strike=24000,
                                     option_type="CE"),
            lambda: p.resolve_by_trading_symbol("NIFTY-Oct2026-24000-CE"),
            lambda: p.strikes("NIFTY", "2026-10-28"),
        ):
            with pytest.raises(InstrumentResolutionError):
                call()
        # The symbol-shaped entry point is total: it returns None so the shared resolver
        # reports "unavailable" and the gate blocks with the operator-facing message.
        assert p.resolve("NIFTY-Oct2026-24000-CE") is None

    def test_stale_metadata_blocks_live_but_not_a_read(self):
        p = loaded_provider()
        assert p.health.is_stale_for_live() is False
        # Force staleness by rewriting the refresh stamp.
        p.health.last_successful_refresh = "2020-01-01T00:00:00+00:00"
        assert p.health.is_stale_for_live() is True
        with pytest.raises(Exception, match="stale"):
            p.resolve_option("NIFTY", expiry="2026-10-28", strike=24000,
                             option_type="CE", for_live=True)
        # The same lookup without the live flag still works: paper and backtest do not
        # need a contract that expires tomorrow.
        assert p.resolve_option("NIFTY", expiry="2026-10-28", strike=24000,
                                option_type="CE") is not None


# ──────────────────────────────────────────────────────────────────────────────
# Atomic refresh
# ──────────────────────────────────────────────────────────────────────────────


class TestAtomicRefresh:
    def test_a_failed_refresh_keeps_the_previous_dataset(self):
        state = {"fail": False}

        def _fetch(url, timeout):
            if state["fail"]:
                raise DhanMasterValidationError("HTTP 503")
            return to_csv(sample_master())

        p = DhanInstrumentProvider(fetch=_fetch)
        asyncio.run(p.refresh())
        assert p.health.validation_status == "ok"
        good = p.dataset
        before = p.resolve_option("NIFTY", expiry="2026-10-28", strike=24000,
                                  option_type="CE")

        state["fail"] = True
        asyncio.run(p.refresh())
        assert p.health.validation_status == "failed"
        assert "503" in p.health.error
        assert p.dataset is good, "the dataset was replaced by a failed refresh"
        after = p.resolve_option("NIFTY", expiry="2026-10-28", strike=24000,
                                 option_type="CE")
        assert after == before
        assert p.health.row_count == 8

    def test_a_malformed_refresh_keeps_the_previous_dataset(self):
        state = {"body": to_csv(sample_master())}
        p = DhanInstrumentProvider(fetch=lambda u, t: state["body"])
        asyncio.run(p.refresh())
        good = p.dataset

        for bad in ("", "<html>nope</html>", "EXCH_ID,SEGMENT\nNSE,D\n",
                    to_csv([row(LOT_SIZE="not-a-number")] * 3)):
            state["body"] = bad
            asyncio.run(p.refresh())
            assert p.health.validation_status == "failed", f"accepted {bad[:20]!r}"
            assert p.dataset is good, f"dataset replaced by malformed body {bad[:20]!r}"

    def test_health_reports_counts_and_source(self):
        p = loaded_provider()
        h = p.health.as_dict()
        assert h["provider"] == "dhan"
        assert h["row_count"] == 8
        assert h["option_contract_count"] == 7
        assert h["index_option_count"] == 5
        assert h["stock_option_count"] == 2
        assert h["future_count"] == 1
        assert h["validation_status"] == "ok"
        assert h["error"] == ""
        assert h["stale_for_live"] is False
        assert h["source_url"].endswith("api-scrip-master-detailed.csv")

    def test_a_failure_before_any_success_is_reported_honestly(self):
        p = DhanInstrumentProvider(fetch=lambda u, t: (_ for _ in ()).throw(
            DhanMasterValidationError("HTTP 500")))
        asyncio.run(p.refresh())
        assert p.health.validation_status == "failed"
        assert p.health.row_count == 0
        assert p.health.is_stale_for_live() is True

    def test_install_rejects_an_empty_candidate(self):
        p = loaded_provider()
        with pytest.raises(DhanMasterValidationError, match="empty"):
            p.install(type(p.dataset)(contracts={}))


# ──────────────────────────────────────────────────────────────────────────────
# Registration
# ──────────────────────────────────────────────────────────────────────────────


class TestRegistration:
    def test_dhan_is_registered_as_authoritative(self):
        names = [p.name for p in instrument_resolver.authoritative_providers()]
        assert "dhan-instrument-master" in names

    def test_registration_is_idempotent(self):
        from market.dhan_instruments import register_dhan_provider

        before = len(instrument_resolver.authoritative_providers())
        register_dhan_provider()
        register_dhan_provider()
        assert len(instrument_resolver.authoritative_providers()) == before

    def test_the_shared_resolver_reaches_the_provider(self):
        p = loaded_provider()
        saved = instrument_resolver.authoritative_providers()
        try:
            instrument_resolver._providers = []
            from market.dhan_instruments import register_dhan_provider
            register_dhan_provider()
            instrument_resolver.register(
                "test-data", lambda *a, **k: p.resolve("NIFTY-Oct2026-24000-CE"),
                authoritative=True)
            inst = instrument_resolver.resolve("NIFTY-Oct2026-24000-CE", broker="dhan",
                                               instrument_type="OPT")
            assert inst is not None and inst.lot_size == 65
        finally:
            instrument_resolver._providers = saved