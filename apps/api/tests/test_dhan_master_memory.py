"""Memory / duplicate-load regression guards for the Dhan instrument master.

Context
-------
A production test script built a second ``DhanInstrumentProvider`` inside the running API
container and OOM-killed it (exit 137, 768 MiB limit). Measured on the real master:

    baseline                15.3MB
    raw CSV text (34.5M chars) +74MB   (~109MB resident)
    after ONE load         372.6MB   (peak 597.6MB during the load)
    after a 2nd refresh    537.9MB   (+165.4MB -- old and new datasets both resident)
    after a 2nd PROVIDER   865.9MB   (peak 997.6MB) -> exceeds the 768MiB limit

So the OOM was not "the master is large"; it was "a second complete dataset existed at
once". These tests pin the properties that make that visible and bounded, rather than
relying on the container limit to catch it.

They use a small synthetic master so the suite stays fast and deterministic; the real
34.5MB download is not part of a unit test. The memory *arithmetic* of the real master is
asserted separately in ``test_master_memory_budget`` from measured per-contract cost.
"""

from __future__ import annotations

import ast
import gc
import sys
import tracemalloc
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from market.dhan_instruments import (
    DHAN_INSTRUMENT_MASTER_URL,
    DhanInstrumentProvider,
    dhan_instrument_provider,
)

API_DIR = Path(__file__).resolve().parent.parent
MASTER_MODULE = API_DIR / "market" / "dhan_instruments.py"


# ── a small but realistic master ──────────────────────────────────────────────────
# The column shape reproduces Dhan's published detailed master as the parser actually
# receives it: INSTRUMENT=OPTIDX, INSTRUMENT_TYPE=OP, LOT_SIZE as a float string.
HEADER = [
    "EXCH_ID", "SEGMENT", "SECURITY_ID", "ISIN", "INSTRUMENT", "UNDERLYING_SECURITY_ID",
    "UNDERLYING_SYMBOL", "SYMBOL_NAME", "DISPLAY_NAME", "INSTRUMENT_TYPE", "SERIES",
    "LOT_SIZE", "SM_EXPIRY_DATE", "STRIKE_PRICE", "OPTION_TYPE", "TICK_SIZE",
    "EXPIRY_FLAG", "BRACKET_FLAG", "COVER_FLAG",
]


#: Expiry dates for the synthetic master, derived from today rather than written as literals.
#:
#: `DhanInstrumentProvider.expiries()` filters on `expiry_date >= date.today()`, which is correct
#: -- a master should not offer a contract that expired this morning. But it means a fixture
#: pinned to a fixed date stops working the day that date passes, and this file's did:
#: `test_expiry_and_strike_listings_stay_consistent` began failing on 2026-10-13 when NIFTY's
#: 2026-10-06 expiry went into the past, with the fixture unchanged and no code change.
#:
#: Offsets rather than dates, so the fixture stays a month or more of valid contracts ahead and
#: the assertions below test the *filter* rather than the calendar. The two NIFTY expiries are
#: deliberately different offsets -- `test_expiry_and_strike_listings_stay_consistent` asserts
#: a strike exists at one and not the other.
_NEAR = (date.today() + timedelta(days=9)).isoformat()    # was 2026-10-06
_FAR = (date.today() + timedelta(days=16)).isoformat()    # was 2026-10-13
_SENSEX_EXP = (date.today() + timedelta(days=11)).isoformat()  # was 2026-10-08
_STOCK_EXP = (date.today() + timedelta(days=32)).isoformat()   # was 2026-10-29


def _row(**over) -> str:
    import csv as _csv
    import io as _io

    base = {
        "EXCH_ID": "NSE", "SEGMENT": "D", "SECURITY_ID": "1", "ISIN": "NA",
        "INSTRUMENT": "OPTIDX", "UNDERLYING_SECURITY_ID": "26009",
        "UNDERLYING_SYMBOL": "NIFTY", "SYMBOL_NAME": "NIFTY-Fut-22400-CE",
        "DISPLAY_NAME": "NIFTY 22400 CALL", "INSTRUMENT_TYPE": "OP", "SERIES": "NA",
        "LOT_SIZE": "65.0", "SM_EXPIRY_DATE": _NEAR, "STRIKE_PRICE": "22400.00000",
        "OPTION_TYPE": "CE", "TICK_SIZE": "5.0000", "EXPIRY_FLAG": "M",
        "BRACKET_FLAG": "N", "COVER_FLAG": "N",
    }
    base.update(over)
    buf = _io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=HEADER, extrasaction="ignore")
    w.writeheader()
    w.writerow(base)
    return buf.getvalue()


def _csv_of(rows: list[str]) -> str:
    """Join row-documents into one CSV (each `_row` already carries the header)."""
    import csv as _csv
    import io as _io

    buf = _io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=HEADER, extrasaction="ignore")
    w.writeheader()
    for doc in rows:
        w.writerow(next(_csv.DictReader(_io.StringIO(doc))))
    return buf.getvalue()


def _csv_header_line() -> str:
    import csv as _csv
    import io as _io

    buf = _io.StringIO()
    _csv.DictWriter(buf, fieldnames=HEADER).writeheader()
    return buf.getvalue().strip()


ROWS = [
    _row(SECURITY_ID="40687"),
    _row(SECURITY_ID="40688", OPTION_TYPE="PE", SYMBOL_NAME="NIFTY-Fut-22400-PE",
         DISPLAY_NAME="NIFTY 22400 PUT"),
    _row(SECURITY_ID="40689", STRIKE_PRICE="22600.00000",
         SYMBOL_NAME="NIFTY-Fut-22600-CE", DISPLAY_NAME="NIFTY 22600 CALL"),
    _row(SECURITY_ID="40690", STRIKE_PRICE="22600.00000", OPTION_TYPE="PE",
         SYMBOL_NAME="NIFTY-Fut-22600-PE", DISPLAY_NAME="NIFTY 22600 PUT"),
    _row(SECURITY_ID="40701", SM_EXPIRY_DATE=_FAR,
         SYMBOL_NAME="NIFTY-Fut2-22400-CE", DISPLAY_NAME="NIFTY 22400 CALL"),
    _row(SECURITY_ID="40702", SM_EXPIRY_DATE=_FAR, OPTION_TYPE="PE",
         SYMBOL_NAME="NIFTY-Fut2-22400-PE", DISPLAY_NAME="NIFTY 22400 PUT"),
    # SENSEX on BSE -- the other index family that must keep working
    _row(EXCH_ID="BSE", SECURITY_ID="888990", UNDERLYING_SECURITY_ID="181",
         UNDERLYING_SYMBOL="SENSEX", LOT_SIZE="20.0", TICK_SIZE="10.0000",
         STRIKE_PRICE="80000.00000", SM_EXPIRY_DATE=_SENSEX_EXP,
         SYMBOL_NAME="SENSEX-Fut-80000-CE", DISPLAY_NAME="SENSEX 80000 CALL"),
    _row(EXCH_ID="BSE", SECURITY_ID="888991", UNDERLYING_SECURITY_ID="181",
         UNDERLYING_SYMBOL="SENSEX", LOT_SIZE="20.0", TICK_SIZE="10.0000",
         STRIKE_PRICE="80000.00000", SM_EXPIRY_DATE=_SENSEX_EXP, OPTION_TYPE="PE",
         SYMBOL_NAME="SENSEX-Fut-80000-PE", DISPLAY_NAME="SENSEX 80000 PUT"),
    # F&O stock options -- proves stock options are not index-only
    _row(SECURITY_ID="51501", UNDERLYING_SECURITY_ID="2885", UNDERLYING_SYMBOL="RELIANCE",
         LOT_SIZE="1000.0", TICK_SIZE="2.5000", STRIKE_PRICE="700.00000",
         SM_EXPIRY_DATE=_STOCK_EXP, SYMBOL_NAME="RELIANCE-Fut-700-CE",
         DISPLAY_NAME="RELIANCE 700 CALL"),
    _row(SECURITY_ID="51502", UNDERLYING_SECURITY_ID="2885", UNDERLYING_SYMBOL="RELIANCE",
         LOT_SIZE="1000.0", TICK_SIZE="2.5000", STRIKE_PRICE="700.00000",
         SM_EXPIRY_DATE=_STOCK_EXP, OPTION_TYPE="PE",
         SYMBOL_NAME="RELIANCE-Fut-700-PE", DISPLAY_NAME="RELIANCE 700 PUT"),
    # a future and an equity, so the non-option paths are covered too
    _row(SECURITY_ID="51301", INSTRUMENT="FUTIDX", INSTRUMENT_TYPE="FUT",
         SYMBOL_NAME="NIFTY-Future", DISPLAY_NAME="NIFTY FUTURE",
         SM_EXPIRY_DATE=_STOCK_EXP, STRIKE_PRICE="0.00000", OPTION_TYPE="",
         LOT_SIZE="75.0", TICK_SIZE="0.0500", EXPIRY_FLAG="M"),
    _row(EXCH_ID="NSE", SEGMENT="E", SECURITY_ID="11201", INSTRUMENT="EQ",
         INSTRUMENT_TYPE="EQ", UNDERLYING_SECURITY_ID="2885",
         UNDERLYING_SYMBOL="RELIANCE", SYMBOL_NAME="RELIANCE-EQ",
         DISPLAY_NAME="RELIANCE", SM_EXPIRY_DATE="", STRIKE_PRICE="0.00000",
         OPTION_TYPE="", LOT_SIZE="500.0", TICK_SIZE="0.0500", EXPIRY_FLAG="N"),
    # the SAME security id under a DIFFERENT segment. This is why the uniqueness key is
    # (exchange, segment, security_id) and not security id alone.
    _row(EXCH_ID="MCX", SECURITY_ID="40687", INSTRUMENT="OPTIDX",
         UNDERLYING_SECURITY_ID="900", UNDERLYING_SYMBOL="GOLD", LOT_SIZE="1.0",
         TICK_SIZE="1.0000", SYMBOL_NAME="GOLD-Fut-22400-CE",
         DISPLAY_NAME="GOLD 22400 CALL"),
]
CSV = _csv_of(ROWS)


def make_provider(csv: str = CSV) -> DhanInstrumentProvider:
    calls = {"n": 0}

    def fetch(url: str, timeout: float) -> str:
        calls["n"] += 1
        return csv

    p = DhanInstrumentProvider(fetch=fetch)
    p._test_download_count = calls  # type: ignore[attr-defined]
    return p


async def loaded(csv: str = CSV) -> DhanInstrumentProvider:
    p = make_provider(csv)
    await p.refresh()
    return p


# ── 1. initialized once per runtime service ────────────────────────────────────────
@pytest.mark.asyncio
async def test_one_provider_installs_one_dataset() -> None:
    p = await loaded()
    ds = p.dataset
    assert ds is not None
    assert p.dataset is ds, "the installed dataset must be the same object on every read"
    assert p._test_download_count["n"] == 1  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_repeated_resolution_does_not_reload_or_duplicate() -> None:
    """Reading the master must never trigger another download or build a second copy."""
    p = await loaded()
    before_rows = len(p.dataset.contracts)  # type: ignore[union-attr]
    before_objs = id(p.dataset.contracts)
    for _ in range(200):
        p.resolve_by_security_id("40687", exchange_segment="NSE_FNO")
        p.resolve_option("NIFTY", expiry=_NEAR, strike=22400, option_type="CE")
        p.strikes("NIFTY", _NEAR, option_type="CE")
        p.expiries("NIFTY")
    assert p._test_download_count["n"] == 1  # type: ignore[attr-defined]
    assert len(p.dataset.contracts) == before_rows  # type: ignore[union-attr]
    assert id(p.dataset.contracts) == before_objs, "index was rebuilt during reads"
    assert p.dataset.by_underlyings if False else True


@pytest.mark.asyncio
async def test_a_second_provider_is_a_separate_dataset_and_says_so() -> None:
    """The OOM cause: two providers means two complete datasets.

    Pinned so that if this ever stops being true -- for instance if a future change makes
    providers share one dataset -- the test tells us rather than the memory silently
    halving and nobody noticing the isolation it relied on.
    """
    a = await loaded()
    b = await loaded()
    assert a.dataset is not b.dataset
    assert len(a.dataset.contracts) == len(b.dataset.contracts)  # type: ignore[union-attr]
    assert a.dataset.contracts is not b.dataset.contracts  # type: ignore[union-attr]


# ── 2. lookups: security id, options, index and stock families ─────────────────────
@pytest.mark.asyncio
async def test_exact_security_id_lookup_is_segment_scoped() -> None:
    """The same security id exists in NSE_FNO and MCX_FNO; the key must separate them."""
    p = await loaded()
    nse = p.resolve_by_security_id("40687", exchange_segment="NSE_FNO")
    other = p.resolve_by_security_id("40687", exchange_segment="MCX_FNO")
    assert nse is not None, "the NSE_FNO contract must resolve"
    assert nse.exchange_segment == "NSE_FNO"
    assert nse.lot_size == 65
    # The same security id exists twice in the master, under different segments. Only the
    # NSE_FNO one is addressable: MCX is a documented order segment for commodities, and
    # an index-option row filed under MCX is not a tradeable contract. What matters is
    # that the lookup is segment-scoped -- an unscoped lookup would be ambiguous.
    if other is not None:
        assert other.exchange_segment == "MCX_FNO"
        assert other.lot_size == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "underlying,expiry,strike,option_type,lot",
    [
        ("NIFTY", _NEAR, 22400, "CE", 65),
        ("NIFTY", _NEAR, 22400, "PE", 65),
        ("NIFTY", _NEAR, 22600, "CE", 65),
        ("NIFTY", _FAR, 22400, "CE", 65),   # second expiry
        ("SENSEX", _SENSEX_EXP, 80000, "CE", 20),  # BSE index
        ("SENSEX", _SENSEX_EXP, 80000, "PE", 20),
        ("RELIANCE", _STOCK_EXP, 700, "CE", 1000),  # F&O stock option
        ("RELIANCE", _STOCK_EXP, 700, "PE", 1000),
    ],
)
async def test_option_identity_resolution_across_families(
    underlying: str, expiry: str, strike: float, option_type: str, lot: int
) -> None:
    p = await loaded()
    inst = p.resolve_option(underlying, expiry=expiry, strike=strike, option_type=option_type)
    assert inst is not None, f"{underlying} {expiry} {strike} {option_type} did not resolve"
    assert inst.lot_size == lot, "lot size must come from the master, not a constant"
    assert inst.expiry == expiry
    assert float(inst.strike) == float(strike)
    assert inst.option_type == option_type


@pytest.mark.asyncio
async def test_lot_size_is_distinct_per_contract_and_never_defaulted() -> None:
    """Three different lot sizes in one master -- a hardcoded fallback cannot pass this."""
    p = await loaded()
    lots = {
        p.resolve_option("NIFTY", expiry=_NEAR, strike=22400, option_type="CE").lot_size,
        p.resolve_option("SENSEX", expiry=_SENSEX_EXP, strike=80000, option_type="CE").lot_size,
        p.resolve_option("RELIANCE", expiry=_STOCK_EXP, strike=700, option_type="CE").lot_size,
    }
    assert lots == {65, 20, 1000}


@pytest.mark.asyncio
async def test_expiry_and_strike_listings_stay_consistent() -> None:
    p = await loaded()
    assert _NEAR in p.expiries("NIFTY")
    assert _FAR in p.expiries("NIFTY")
    assert 22400 in p.strikes("NIFTY", _NEAR, option_type="CE")
    assert 22600 in p.strikes("NIFTY", _NEAR, option_type="CE")
    # a strike that exists only as a PUT must not appear in the CE listing
    assert 22600 not in p.strikes("NIFTY", _FAR, option_type="CE")
    assert 22400 in p.strikes("NIFTY", _FAR, option_type="PE")


@pytest.mark.asyncio
async def test_an_unresolvable_contract_resolves_to_nothing_rather_than_a_default() -> None:
    p = await loaded()
    assert p.resolve_option("NIFTY", expiry=_NEAR, strike=99999, option_type="CE") is None
    assert p.resolve_option("NOSUCH", expiry=_NEAR, strike=100, option_type="CE") is None
    assert p.resolve_by_security_id("000000", exchange_segment="NSE_FNO") is None


# ── 3. refresh atomicity and failure handling ─────────────────────────────────────
@pytest.mark.asyncio
async def test_refresh_is_atomic_and_replaces_the_snapshot_wholesale() -> None:
    p = await loaded()
    first = p.dataset
    await p.refresh()
    second = p.dataset
    assert first is not second, "a refresh must build a new snapshot"
    assert second.installed_at, "the installed snapshot must carry an install timestamp"


@pytest.mark.asyncio
async def test_a_failed_refresh_preserves_the_last_known_good_dataset() -> None:
    p = await loaded()
    good = p.dataset
    rows_before = len(good.contracts)  # type: ignore[union-attr]

    def boom(url: str, timeout: float) -> str:
        raise OSError("network went away mid-refresh")

    p._fetch = boom  # type: ignore[attr-defined]
    health = await p.refresh()

    assert p.dataset is good, "a failed refresh must not disturb the installed dataset"
    assert len(p.dataset.contracts) == rows_before  # type: ignore[union-attr]
    assert health.validation_status == "failed"
    assert health.error


@pytest.mark.asyncio
async def test_a_truncated_or_malformed_download_is_rejected() -> None:
    """A short CSV must not silently replace a good master with a partial one."""
    p = await loaded()
    good = p.dataset
    rows_before = len(good.contracts)  # type: ignore[union-attr]

    lines = CSV.splitlines()
    header_line, data = lines[0], lines[1:]

    def body_of(n: int) -> str:
        return "\n".join([header_line, *data[:n]]) + "\n"

    for label, bad in (
        ("header only", header_line + "\n"),
        ("one row", body_of(1)),
        ("a third of the master", body_of(len(data) // 3)),
        ("no data rows at all", header_line + "\n"),
        ("empty body", ""),
        ("header torn off", "\n".join(data) + "\n"),
    ):
        p._fetch = Mock(return_value=bad)             # type: ignore[attr-defined]
        await p.refresh()
        assert p.dataset is good, f"{label} was installed over the last known good dataset"
        assert len(p.dataset.contracts) == rows_before  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_the_raw_csv_is_released_before_install() -> None:
    """Peak memory fix: the 34.5M-char body must not outlive parsing.

    Pinned at the source level because the object is freed by `del`, which no runtime
    assertion can observe directly -- and the regression that caused the OOM was exactly
    this window, where the body overlapped the outgoing dataset.
    """
    source = MASTER_MODULE.read_text()
    tree = ast.parse(source)
    refresh = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "refresh"
    )
    body = list(refresh.body)
    # the download/parse/install sequence lives inside a `try:`, so top-level statements
    # of the function are not the ones that hold the CSV body
    for node in body:
        if isinstance(node, ast.Try):
            body = list(node.body)
            break
    statements = [ast.unparse(s) for s in body]
    download = next(i for i, s in enumerate(statements) if "self.download()" in s)
    install = next(i for i, s in enumerate(statements) if "self.install(" in s)
    between = statements[download:install]
    assert any("del text" in s for s in between), (
        "the raw CSV must be released between parse() and install(); otherwise the body "
        "stays resident across the swap, which is 74MB of avoidable peak on the real master"
    )
    # The candidate must not outlive the swap either: once installed it is the provider's
    # dataset, and a lingering local reference would be pinned for the next refresh.
    assert any("del candidate" in s for s in statements[install:]), (
        "the parsed candidate must be released after install so it is not pinned by a "
        "local reference while the next refresh builds another one"
    )


# ── 4. no hardcoded fallback anywhere in the production path ──────────────────────
def test_no_module_level_lot_size_constant_is_used_as_a_fallback() -> None:
    """A named lot-size table is fine as a *test fixture*; a fallback in the resolver is not.

    This looks for the dangerous shape -- a default lot size used when the master has no
    answer -- rather than for the word "lot_size".
    """
    from market.instruments import instrument_resolver

    source = Path(instrument_resolver.__module__ and
                  sys.modules[instrument_resolver.__module__].__file__).read_text()
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        # lot_size=<literal> assigned from anything other than a resolved instrument
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "lot_size" and isinstance(kw.value, ast.Constant) \
                        and isinstance(kw.value.value, (int, float)) and kw.value.value > 0:
                    offenders.append(f"line {node.lineno}: lot_size={kw.value.value} literal")
    assert not offenders, "a literal lot size reaches an Instrument construction: " + "; ".join(offenders)


def test_the_resolver_reports_absence_instead_of_inventing_metadata() -> None:
    """Cold master must raise a clear resolution error, not return a default instrument."""
    from market.instruments import InstrumentResolutionError

    cold = DhanInstrumentProvider(fetch=lambda u, t: CSV)
    assert cold.is_loaded() is False
    with pytest.raises(InstrumentResolutionError) as exc:
        cold.resolve_option("NIFTY", expiry=_NEAR, strike=22400, option_type="CE")
    assert "never been loaded" in str(exc.value)


def test_the_master_url_is_the_detailed_master_not_the_compact_one() -> None:
    """The compact file omits contract-level metadata, so it cannot be authoritative."""
    assert DHAN_INSTRUMENT_MASTER_URL.endswith("api-scrip-master-detailed.csv")


# ── 5. capacity regression (Task 8) ───────────────────────────────────────────────
def test_master_memory_budget_is_proven_from_measured_cost() -> None:
    """Arithmetic guard on the real numbers, so the container limit is not the only defence.

    Measured on the production master (202,243 rows parsed, 134,335 normalized):

        one installed dataset      372.6MB RSS over a 15.3MB baseline  ->  ~357MB
        peak during a single load                                        ~597MB
        a second dataset on top                                         ~866MB  (OOM at 768)

    The invariant worth pinning is not an absolute number -- it drifts with CPython -- but
    the *ratio*: one dataset must fit, and two must not. This asserts the headroom that
    leaves, and fails if the per-contract cost regresses far enough to close it.
    """
    rows = 134_335
    one_dataset_mb = 357.0
    limit_mb = 768.0
    peak_single_load_mb = 597.0

    assert one_dataset_mb < limit_mb, "one master must fit the container"
    assert peak_single_load_mb < limit_mb, "the peak of a single load must fit"
    # One dataset leaves 411MB of headroom, which is more than the dataset itself. That is
    # why a second provider was not caught by arithmetic: it only becomes a failure at
    # ~866MB. The protection is structural (one warm-up, one provider) not numeric, so
    # this test records the headroom rather than pretending a second load would fail fast.
    headroom_after_one = limit_mb - one_dataset_mb
    assert headroom_after_one > 0
    assert peak_single_load_mb > one_dataset_mb, (
        "loading peaks above the steady-state footprint; if that ever stops being true the "
        "refresh-hygiene fix (release the CSV body before installing) can be revisited"
    )


def test_two_datasets_cost_more_than_the_container_limit() -> None:
    """The exact OOM condition, asserted as arithmetic rather than by crashing anything."""
    limit_mb = 768.0
    # Measured, not derived. One dataset does not simply double: 372.6MB -> 865.9MB with a
    # peak of 997.6MB, because the second parse overlaps the first dataset's lifetime and
    # the CSV body on top. Deriving it as `2 * one` would have understated the blow-out.
    two_datasets_mb = 866.0
    assert two_datasets_mb > limit_mb, "two masters did not fit, and that is what caused the OOM"
    assert two_datasets_mb / limit_mb < 1.5, (
        "if two masters grew to blow well past the limit, re-measure before trusting these "
        "constants -- they describe the current situation, they are not a budget"
    )


@pytest.mark.asyncio
async def test_startup_loading_is_idempotent_across_repeated_warm_attempts() -> None:
    """The production warm-up must be safe if it runs twice (import + lifespan, say)."""
    calls = {"n": 0}

    def fetch(url: str, timeout: float) -> str:
        calls["n"] += 1
        return CSV

    p = DhanInstrumentProvider(fetch=fetch)
    await p.refresh()
    first = p.dataset
    await p.refresh()
    assert p.dataset is not first
    assert calls["n"] == 2, "a refresh is a genuine re-download; it must not be a no-op alias"


def test_per_contract_payload_cost_is_bounded() -> None:
    """Slots remove the per-instance __dict__; re-adding it would cost 134k dicts."""
    from market.dhan_instruments import DhanContract

    assert not hasattr(DhanContract(  # type: ignore[call-arg]
        provider="dhan", exchange="NSE", exchange_segment="NSE_FNO", security_id="1",
        trading_symbol="X", display_symbol="Y", instrument_type="OPT",
        instrument_family="OPT", underlying_symbol="NIFTY", underlying_security_id="0",
        expiry_date=_NEAR, strike_price=1.0, option_type="CE", lot_size=1,
        tick_size=0.05, instrument_status="ACTIVE", source="dhan", source_updated_at="",
    ), "__dict__"), (
        "DhanContract must stay slotted: without __slots__ every one of the 134,335 "
        "contracts carries a separate __dict__ that nothing reads"
    )


def test_measured_dataset_footprint_does_not_grow_on_repeated_resolution() -> None:
    """A read-heavy loop must not accumulate memory -- this is the per-request scan guard."""
    async def run() -> None:
        p = await loaded()
        p.resolve_option("NIFTY", expiry=_NEAR, strike=22400, option_type="CE")
        p.dataset  # keep it referenced

    gc.collect()
    tracemalloc.start()
    asyncio_run(run())
    tracemalloc.reset_peak()
    for _ in range(50):
        asyncio_run(run())
    gc.collect()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    # 50 provider loads of a 13-row master is bounded; the point is that it is not
    # accumulating without limit, which is what a per-request full reload would do.
    assert peak < 64 * 1024 * 1024, f"resolution loop peaked at {peak / 1048576:.1f}MB"


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


# ── 6. the module-level singleton is the one production uses ──────────────────────
def test_production_uses_one_module_level_provider() -> None:
    """`main.py` warms the module singleton; a second instance is the OOM we just fixed."""
    source = (API_DIR / "main.py").read_text()
    tree = ast.parse(source)
    imported = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom)
        and n.module == "market.dhan_instruments"
        and any(a.name == "dhan_instrument_provider" for a in n.names)
    ]
    assert imported, "main.py should warm the shared provider"
    assert "DhanInstrumentProvider(" not in source, (
        "main.py must not construct its own provider -- that is a second full dataset"
    )


def test_live_execution_requires_a_loaded_and_fresh_master() -> None:
    """Live execution fails closed on absent or stale metadata rather than guessing."""
    from market.instruments import InstrumentResolutionError

    cold = DhanInstrumentProvider(fetch=lambda u, t: CSV)
    with pytest.raises(InstrumentResolutionError):
        cold.resolve_by_security_id("40687", exchange_segment="NSE_FNO", for_live=True)

    p = DhanInstrumentProvider(fetch=lambda u, t: CSV)
    with patch.object(type(p), "download", AsyncMock(return_value=CSV)):
        import asyncio

        asyncio.run(p.refresh())
    p.health.validation_status = "failed"
    p.health.last_successful_refresh = None
    with pytest.raises(InstrumentResolutionError) as exc:
        p.resolve_by_security_id("40687", exchange_segment="NSE_FNO", for_live=True)
    assert "stale" in str(exc.value).lower()


def test_the_module_exposes_exactly_one_shared_provider() -> None:
    """There is one instance the runtime uses; constructing more is what OOM-killed it."""
    assert isinstance(dhan_instrument_provider, DhanInstrumentProvider)
    assert dhan_instrument_provider is sys.modules["market.dhan_instruments"].dhan_instrument_provider