"""The mmap backend feature flag, exercised against the real Dhan master.

The flag selects where a refreshed master is held. Both backends serve one API
(`_Dataset`'s accessors), so the risk is not a different result -- it is that the
mapping from flag to backend is wrong in some direction that still looks healthy:
the flag ignored, the flag flipping which contracts are accepted, or the mapped
dataset silently serving fewer rows than the object one.

Every test here runs the real parse path and, where relevant, the real encoder. The
fixtures are the master itself, fetched once per module from Dhan's public endpoint and
skipped if unreachable -- a fabricated CSV cannot prove that a 138,106-row master
round-trips, which is the only thing this file claims.
"""

import hashlib
import asyncio
from pathlib import Path

import pytest

import market.dhan_instruments as di
from market.dhan_instruments import DhanInstrumentProvider

REPO_ROOT = Path(__file__).resolve().parents[3]
MASTER_PATH = REPO_ROOT / "apps" / "api" / "tests" / "fixtures" / "dhan_instrument_master.csv"
MASTER_URL = di.DHAN_INSTRUMENT_MASTER_URL


@pytest.fixture(scope="module")
def master_text() -> str:
    """The real master, from disk if present else fetched once."""
    if MASTER_PATH.exists():
        return MASTER_PATH.read_text()
    try:
        import httpx

        response = httpx.get(MASTER_URL, timeout=120, follow_redirects=True)
        response.raise_for_status()
        return response.text
    except Exception as exc:  # noqa: BLE001 - skip rather than fail without network
        pytest.skip(f"cannot obtain the real Dhan master: {exc}")


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(di.settings, "dhan_master_store_dir", str(tmp_path / "store"))
    return tmp_path / "store"


def _versions(root) -> list[str]:
    """Version directories only.

    Not `iterdir() + is_dir()`: `active` is a symlink to the current version and
    `Path.is_dir()` follows symlinks, so it counts as a second version. The store has
    its own listing that applies the real name rule, and reusing it means the test
    cannot disagree with the store about what a version is.
    """
    from market.instrument_store import MmapInstrumentStore, is_version_name

    return sorted(p.name for p in Path(root).iterdir()
                  if p.is_dir() and is_version_name(p.name))


def _provider() -> DhanInstrumentProvider:
    return DhanInstrumentProvider(fetch=lambda url, timeout: "")


# ── the flag defaults off ──────────────────────────────────────────────────

def test_flag_defaults_to_the_object_backend():
    """An unconfigured deploy must not be the first place the mapped path runs."""
    assert di.settings.dhan_master_use_mmap is False


def test_flag_is_read_from_the_settings_object_not_a_literal(monkeypatch):
    """If refresh read os.environ directly, monkeypatching settings could not flip it."""
    monkeypatch.setattr(di.settings, "dhan_master_use_mmap", True)
    assert di.settings.dhan_master_use_mmap is True


# ── off: the object backend, unchanged ─────────────────────────────────────

def test_flag_off_yields_an_object_dataset(master_text, tmp_store):
    provider = _provider()
    dataset = provider.parse(master_text)
    assert dataset.is_mmap is False
    assert dataset.contract_count > 100_000


def test_flag_off_never_touches_the_store(master_text, tmp_store):
    """With the flag off not a single byte should be written to the store dir."""
    provider = _provider()
    provider.install(provider.parse(master_text))
    assert not tmp_store.exists(), "object backend wrote to the mapped store"


# ── on: the mapped backend ─────────────────────────────────────────────────

def _refresh_mapped(provider: DhanInstrumentProvider, master_text: str) -> None:
    """Drive refresh() without a network, using the real install path."""
    dataset = provider.parse(master_text)
    encoded = provider._encode_as_mmap(dataset)  # noqa: SLF001 - the unit under test
    provider.install(encoded)


def test_flag_on_yields_a_mapped_dataset(master_text, tmp_store, monkeypatch):
    monkeypatch.setattr(di.settings, "dhan_master_use_mmap", True)
    provider = _provider()
    _refresh_mapped(provider, master_text)
    assert provider.dataset.is_mmap is True


def test_flag_on_preserves_the_contract_count(master_text, tmp_store, monkeypatch):
    """The mapped dataset must hold exactly what the object one did."""
    monkeypatch.setattr(di.settings, "dhan_master_use_mmap", True)
    provider = _provider()
    obj = provider.parse(master_text)
    obj_count = obj.contract_count

    mapped = provider._encode_as_mmap(obj)  # noqa: SLF001
    assert mapped.contract_count == obj_count


def test_flag_on_resolves_the_same_contract_by_security_id(master_text, tmp_store, monkeypatch):
    monkeypatch.setattr(di.settings, "dhan_master_use_mmap", True)
    provider = _provider()
    obj = provider.parse(master_text)

    # Sample real identities out of the object dataset rather than inventing one.
    sample_keys = sorted(obj.contracts)[:500] + sorted(obj.contracts)[-200:]
    mapped = provider._encode_as_mmap(obj)  # noqa: SLF001

    for exchange, segment, security_id in sample_keys:
        want = obj.contract_for(exchange, segment, security_id)
        got = mapped.contract_for(exchange, segment, security_id)
        assert got is not None, f"mapped store lost {(exchange, segment, security_id)}"
        assert got.security_id == want.security_id
        assert got.trading_symbol == want.trading_symbol
        assert got.exchange_segment == want.exchange_segment
        assert got.lot_size == want.lot_size
        assert got.tick_size == want.tick_size


def test_flag_on_resolves_the_same_option_by_identity(master_text, tmp_store, monkeypatch):
    """Option identity is (underlying, expiry, strike, option_type)."""
    monkeypatch.setattr(di.settings, "dhan_master_use_mmap", True)
    provider = _provider()
    obj = provider.parse(master_text)
    mapped = provider._encode_as_mmap(obj)  # noqa: SLF001

    checked = 0
    for contract in list(obj.contracts.values()):
        if not contract.option_type or not contract.expiry_date:
            continue
        want = obj.find_option(
            contract.underlying_symbol, contract.expiry_date,
            contract.strike_price, contract.option_type,
        )
        got = mapped.find_option(
            contract.underlying_symbol, contract.expiry_date,
            contract.strike_price, contract.option_type,
        )
        assert (got is None) == (want is None)
        if want is not None:
            assert got.security_id == want.security_id
            assert got.lot_size == want.lot_size
        checked += 1
        if checked >= 3000:
            break
    assert checked > 100, "expected a meaningful number of option contracts to compare"


def test_flag_on_serves_identical_expiry_and_strike_listings(master_text, tmp_store, monkeypatch):
    """`expiries`/`strikes`/lot size are PROVIDER methods, not `_Dataset` accessors.

    So each dataset is installed into its own provider and the public surface is
    compared -- which is also the surface production actually uses. Reading
    `_dataset.rows_for_underlying` directly would test a layer nothing calls.
    """
    monkeypatch.setattr(di.settings, "dhan_master_use_mmap", True)

    object_provider = _provider()
    obj = object_provider.parse(master_text)
    object_provider.install(obj)

    mapped_provider = _provider()
    mapped_provider.install(mapped_provider._encode_as_mmap(obj))  # noqa: SLF001

    underlyings = obj.option_underlyings()[:40]
    assert underlyings, "master should expose option underlyings"

    compared_strikes = 0
    for underlying in underlyings:
        assert mapped_provider.expiries(underlying) == object_provider.expiries(underlying)
        assert (mapped_provider.resolve_index_option_lot_size(underlying)
                == object_provider.resolve_index_option_lot_size(underlying))

        for expiry in object_provider.expiries(underlying)[:3]:
            want = object_provider.strikes(underlying, expiry)
            got = mapped_provider.strikes(underlying, expiry)
            assert got == want, f"strikes differ for {underlying} {expiry}"
            compared_strikes += len(want)

    assert compared_strikes > 0, "no strikes were compared"


def test_flag_on_sweeps_every_security_id_once(master_text, tmp_store, monkeypatch):
    """A full sweep, not a sample: a missing row anywhere is a blanked contract."""
    monkeypatch.setattr(di.settings, "dhan_master_use_mmap", True)
    provider = _provider()
    obj = provider.parse(master_text)
    mapped = provider._encode_as_mmap(obj)  # noqa: SLF001

    missing = 0
    for exchange, segment, security_id in obj.contracts:
        if mapped.contract_for(exchange, segment, security_id) is None:
            missing += 1
    assert missing == 0, f"{missing} contracts missing from the mapped store"
    assert mapped.contract_count == obj.contract_count


# ── version naming ─────────────────────────────────────────────────────────

def test_version_is_content_derived_so_a_retry_reuses_the_directory(master_text, tmp_store, monkeypatch):
    """A clock-based name would fill the store with near-duplicate directories."""
    monkeypatch.setattr(di.settings, "dhan_master_use_mmap", True)
    provider = _provider()
    obj = provider.parse(master_text)
    provider._encode_as_mmap(obj)  # noqa: SLF001
    first = _versions(tmp_store)

    provider2 = _provider()
    provider2._encode_as_mmap(provider2.parse(master_text))  # noqa: SLF001
    second = _versions(tmp_store)
    assert first == second


def test_changing_the_master_changes_the_version(master_text, tmp_store, monkeypatch):
    """A different master must produce a different directory.

    Drops a row that is actually ingested. Dropping the LAST row instead is the obvious
    version and it skips: the master's tail is un-ingested instruments (GIFTNIFTY and
    friends), which never become contracts, so the count is unchanged and the content
    hash -- correctly -- does not move.
    """
    import csv
    import io

    monkeypatch.setattr(di.settings, "dhan_master_use_mmap", True)
    provider = _provider()
    obj = provider.parse(master_text)
    provider._encode_as_mmap(obj)  # noqa: SLF001
    v1 = _versions(tmp_store)[0]

    reader = csv.DictReader(io.StringIO(master_text))
    fieldnames = reader.fieldnames
    rows = list(reader)

    # Select the victim by SYMBOL_NAME, which maps 1:1 onto the parser's trading_symbol.
    #
    # Four earlier versions of this test each asserted nothing while appearing to check
    # the version, all because the chosen row was never a contract:
    #   - INSTRUMENT in INGESTED_INSTRUMENTS is necessary but not sufficient (row 0 is
    #     FUTCUR, an ingested family, and is still rejected);
    #   - (EXCH_ID, SEGMENT, SECURITY_ID) cannot be matched against the parsed set at
    #     all, because the parser NORMALISES the segment -- raw 'D' is stored as
    #     'BSE_FNO', so the two key spaces share nothing (measured intersection: 0);
    #   - a globally-unique SECURITY_ID still belonged to a rejected row;
    #   - giving a row a fresh SECURITY_ID changed nothing either, because that row's
    #     segment ('C' on BSE) is rejected before the id matters.
    # trading_symbol is copied verbatim from SYMBOL_NAME, so it needs no normalisation,
    # and requiring it to be a live contract's symbol means the row really is one.
    sym_counts: dict[str, int] = {}
    for r in rows:
        sym = (r.get("SYMBOL_NAME") or "").strip()
        if sym:
            sym_counts[sym] = sym_counts.get(sym, 0) + 1

    live_symbols = {c.trading_symbol for c in obj.contracts.values() if c.trading_symbol}
    victim = next(
        (i for i, r in enumerate(rows)
         if (r.get("SYMBOL_NAME") or "").strip() in live_symbols
         and sym_counts[(r.get("SYMBOL_NAME") or "").strip()] == 1),
        None,
    )
    assert victim is not None, "master had no uniquely-named live contract row to drop"
    reduced_rows = rows[:victim] + rows[victim + 1:]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(reduced_rows)

    provider2 = _provider()
    obj2 = provider2.parse(buffer.getvalue())
    assert obj2.contract_count == obj.contract_count - 1, \
        f"dropping one live contract row should remove exactly one contract " \
        f"({obj2.contract_count} vs {obj.contract_count})"
    provider2._encode_as_mmap(obj2)  # noqa: SLF001

    versions = _versions(tmp_store)
    assert len(versions) == 2, f"expected 2 versions, got {versions}"
    assert v1 in versions


def test_an_uningested_row_does_not_change_the_version(master_text, tmp_store, monkeypatch):
    """The inverse: content the parser discards must not mint a new version.

    Otherwise every refresh writes a new ~11MB directory for a master whose usable
    contracts are unchanged, and the store grows without bound.
    """
    monkeypatch.setattr(di.settings, "dhan_master_use_mmap", True)
    provider = _provider()
    obj = provider.parse(master_text)
    provider._encode_as_mmap(obj)  # noqa: SLF001

    lines = master_text.rstrip("\n").split("\n")
    provider2 = _provider()
    obj2 = provider2.parse("\n".join(lines[:-1]) + "\n")
    assert obj2.contract_count == obj.contract_count
    provider2._encode_as_mmap(obj2)  # noqa: SLF001

    versions = _versions(tmp_store)
    assert len(versions) == 1, f"expected the version to be reused, got {versions}"


# ── failure handling ───────────────────────────────────────────────────────

def test_an_encode_failure_does_not_install_junk(master_text, tmp_store, monkeypatch):
    """The last known-good dataset must survive a failed encode.

    Exercised through the real `refresh()` with an injected fetcher, because that is
    where the guarantee lives: an exception between parse and install must leave the
    previous dataset serving. A test that only called `_encode_as_mmap` directly would
    never touch the rebinding that provides the guarantee.
    """
    provider = DhanInstrumentProvider(fetch=lambda url, timeout: master_text)

    provider.install(provider.parse(master_text))
    good_count = provider.dataset.contract_count
    assert good_count > 100_000
    assert provider.dataset.is_mmap is False

    monkeypatch.setattr(di.settings, "dhan_master_use_mmap", True)

    def boom(*_args, **_kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr("market.instrument_writer.build_from_contracts", boom)
    asyncio.run(provider.refresh())

    # Health records the failure...
    assert provider.health.validation_status == "failed"
    assert "no space left" in provider.health.error
    # ...and the previously installed dataset is still the one serving.
    assert provider.dataset.contract_count == good_count
    assert provider.dataset.is_mmap is False


def test_refresh_with_the_flag_on_installs_the_mapped_dataset(master_text, tmp_store, monkeypatch):
    """End to end through refresh(): flag on => mapped, and health reports it."""
    monkeypatch.setattr(di.settings, "dhan_master_use_mmap", True)
    provider = DhanInstrumentProvider(fetch=lambda url, timeout: master_text)

    asyncio.run(provider.refresh())

    assert provider.dataset.is_mmap is True
    assert provider.health.validation_status == "ok"
    assert provider.health.row_count == provider.dataset.contract_count
    assert provider.health.row_count > 100_000


# ── parity with the object backend is already covered elsewhere ────────────

def test_this_file_does_not_duplicate_the_parity_suite():
    """The exhaustive object-vs-mapped parity lives in test_provider_backend_parity.py.

    Asserted so the two do not drift into either duplicating or contradicting each
    other; if that file is renamed this fails and the reference is updated deliberately.
    """
    assert (Path(__file__).parent / "test_provider_backend_parity.py").exists()
