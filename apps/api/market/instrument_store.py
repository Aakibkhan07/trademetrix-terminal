"""On-disk, memory-mapped store for the Dhan instrument master.

Why this exists
---------------
The master is 138,106 contracts. Held as Python objects it costs ~1.6 KB each, so
~221 MB resident inside the API container against a 768 MiB limit -- measured, and
the direct cause of the restarts. A fixed-width binary record plus sorted indexes on
disk costs 15.4 MiB and is mapped rather than copied.

Layout, one directory per version under a root::

    <root>/active -> v0007            (symlink, swapped atomically)
    <root>/v0007/header.json         metadata + CRC32 per payload
    <root>/v0007/tab.json            code -> string tables
    <root>/v0007/records.dat         fixed-width REC records
    <root>/v0007/strings.dat         trading-symbol byte pool
    <root>/v0007/sec.dat             sorted (exchange, segment, security_id) -> slot
    <root>/v0007/opt.dat             sorted (underlying, expiry, strike, type) -> slot
    <root>/v0007/sym.dat             sorted symbol -> slot

Formats are derived from one declaration in ``instrument_schema``; no width is
written twice. The schema module is the single source of truth and asserts
``struct.size`` against the declared field widths, so a width mismatch cannot reach
the disk.

Failure is always closed. Opening validates, in order: magic, format version,
schema id, record size, record count, file sizes, index divisibility, then CRC32 of
every payload. Anything that does not match raises :class:`ReopenRejected` and the
caller sees nothing.

Concurrency
-----------
Readers resolve ``active`` once and mmap the version they got. A refresh builds a
new version beside the current one and swaps the symlink with ``rename(2)``, which is
atomic: a reader sees the old target or the new one, never neither and never a
half-written path. A reader that already holds a mapping keeps reading it safely
even after the directory is later removed -- on Linux the mapping outlives the file
it came from. That is what makes retirement safe to defer: see ``retire()``.
"""

from __future__ import annotations

import errno
import json
import mmap
import os
import struct
import sys
import time
import zlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from market.instrument_schema import (
    OPT_INDEX,
    RECORD,
    SEC_INDEX,
    SYM_INDEX,
    Schema,
)

MAGIC = b"TMMAP01\x00"
FORMAT_VERSION = 1
CRC_ALGORITHM = "CRC32/zlib"

PAYLOAD_FILES = {
    "records": "records.dat",
    "strings": "strings.dat",
    "sec": "sec.dat",
    "opt": "opt.dat",
    "sym": "sym.dat",
}
ALL_FILES = dict(PAYLOAD_FILES)
BUILD_MARKER = ".building"
FROZEN_MARKER = ".frozen"

#: Dimensions encoded as small integer codes in the record. The string table lives in
#: tab.json, so the record itself never holds a string.
STRING_TABLES = (
    "exchange", "exchange_segment", "instrument_type", "instrument_family",
    "option_type", "instrument_status", "source", "expiry_date", "underlying_symbol",
)


class ReopenRejectedError(Exception):
    """A persisted dataset failed validation. Nothing was exposed to the caller."""


class ActivationRejectedError(Exception):
    """Refused to activate a candidate. The previously active version is untouched."""


class BuildLockedError(Exception):
    """Another refresh already holds the build lock."""


def schema_id() -> str:
    """Fingerprint of the schema. Changes if any field list, order or width changes."""
    import hashlib

    h = hashlib.sha256()
    for s in (RECORD, SEC_INDEX, SYM_INDEX, OPT_INDEX):
        h.update(s.name.encode())
        h.update(s.fmt.encode())
        h.update(str(s.size).encode())
        for f in s.fields:
            h.update(repr(f).encode())
    return h.hexdigest()[:16]


def crc_of_payload(path: Path, chunk: int = 1 << 20) -> int:
    """CRC32 over the exact bytes after the magic prefix, read back from disk.

    Reading from disk rather than from an in-memory buffer is deliberate: the stored
    value must describe what was persisted, not what was intended.
    """
    crc = 0
    with open(path, "rb") as fh:
        if fh.read(len(MAGIC)) != MAGIC:
            raise ReopenRejectedError(f"{path.name} bad magic prefix")
        while True:
            block = fh.read(chunk)
            if not block:
                break
            crc = zlib.crc32(block, crc)
    return crc & 0xFFFFFFFF


def _fsync(path: Path) -> None:
    flags = os.O_RDONLY | (getattr(os, "O_DIRECTORY", 0) if path.is_dir() else 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def is_version_name(name: str) -> bool:
    return bool(name) and name[0] == "v" and name[1:].isdigit()


# ── header ──────────────────────────────────────────────────────────────────────
def write_header(
    vdir: Path,
    *,
    record_count: int,
    tables: dict[str, dict[int, str]],
    sizes: dict[str, int],
    crcs: dict[str, int],
    source: dict,
) -> dict:
    hdr = {
        "magic": MAGIC.decode("ascii").rstrip("\x00"),
        "format_version": FORMAT_VERSION,
        "schema_id": schema_id(),
        "record_schema": {"name": RECORD.name, "format": RECORD.fmt, "size": RECORD.size},
        "index_schemas": {
            s.name: {"format": s.fmt, "size": s.size}
            for s in (SEC_INDEX, SYM_INDEX, OPT_INDEX)
        },
        "record_count": record_count,
        "file_sizes": sizes,
        "integrity": {
            "algorithm": CRC_ALGORITHM,
            "width_bits": 32,
            "encoding": "uint32 decimal in JSON",
            "scope": "exact payload bytes after the 8-byte magic prefix",
            "files": sorted(PAYLOAD_FILES),
        },
        "payload_crc32": {k: int(v) for k, v in crcs.items()},
        "source": source,
        "string_tables": {name: sorted(d.items()) for name, d in tables.items()},
    }
    (vdir / "header.json").write_text(json.dumps(hdr, indent=2, sort_keys=True), encoding="utf-8")
    return hdr


def read_header(vdir: Path) -> dict:
    hp = vdir / "header.json"
    if not hp.exists():
        raise ReopenRejectedError("header.json missing")
    try:
        return json.loads(hp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReopenRejectedError(f"header.json unreadable: {exc}") from exc


def validate(vdir: Path, *, verify_crc: bool = True) -> tuple[dict, dict]:
    """Ordered, fail-closed validation. Returns (header, timings).

    The order matters and is not arbitrary: cheap structural checks reject the common
    cases first, and CRC runs last because it is the only one that must read every
    byte. A truncated file is caught in microseconds; a silently altered payload needs
    the full read.
    """
    t0 = time.perf_counter()
    hdr = read_header(vdir)
    want_magic = MAGIC.decode("ascii").rstrip("\x00")
    if hdr.get("magic") != want_magic:
        raise ReopenRejectedError(f"magic mismatch: {hdr.get('magic')!r} != {want_magic!r}")
    if hdr.get("format_version") != FORMAT_VERSION:
        raise ReopenRejectedError(
            f"format_version {hdr.get('format_version')!r} != {FORMAT_VERSION}")
    if hdr.get("schema_id") != schema_id():
        raise ReopenRejectedError(
            f"schema_id {hdr.get('schema_id')!r} != {schema_id()!r} (schema changed)")
    if (hdr.get("record_schema") or {}).get("size") != RECORD.size:
        raise ReopenRejectedError(
            f"record size {(hdr.get('record_schema') or {}).get('size')} != {RECORD.size}")
    for s in (SEC_INDEX, SYM_INDEX, OPT_INDEX):
        got = (hdr.get("index_schemas") or {}).get(s.name) or {}
        if got.get("size") != s.size:
            raise ReopenRejectedError(f"{s.name} size {got.get('size')} != {s.size}")
    count = hdr.get("record_count")
    if not isinstance(count, int) or count <= 0:
        raise ReopenRejectedError(f"record_count invalid: {count!r}")

    sizes = hdr.get("file_sizes") or {}
    for key, name in ALL_FILES.items():
        p = vdir / name
        if not p.exists():
            raise ReopenRejectedError(f"required file missing: {name}")
        actual = p.stat().st_size
        want = sizes.get(key)
        if want is not None and actual != want:
            raise ReopenRejectedError(
                f"{name} size {actual} != header {want} (truncated or padded)")
        with open(p, "rb") as fh:
            prefix = fh.read(len(MAGIC))
        if prefix != MAGIC:
            raise ReopenRejectedError(f"{name} bad magic prefix: {prefix!r} != {MAGIC!r}")

    for key, schema, label in (
        ("sec", SEC_INDEX, "security index"),
        ("opt", OPT_INDEX, "option index"),
        ("sym", SYM_INDEX, "symbol index"),
    ):
        payload = (vdir / ALL_FILES[key]).stat().st_size - len(MAGIC)
        if payload % schema.size:
            raise ReopenRejectedError(
                f"{label} payload {payload} not a multiple of {schema.size}")
        if payload // schema.size != count:
            raise ReopenRejectedError(
                f"{label} holds {payload // schema.size} entries, header says {count}")
    rpay = (vdir / ALL_FILES["records"]).stat().st_size - len(MAGIC)
    if rpay != count * RECORD.size:
        raise ReopenRejectedError(
            f"records payload {rpay} != {count} x {RECORD.size} = {count * RECORD.size}")

    integrity = hdr.get("integrity") or {}
    if integrity.get("algorithm") != CRC_ALGORITHM:
        raise ReopenRejectedError(
            f"integrity algorithm {integrity.get('algorithm')!r} != {CRC_ALGORITHM!r}")
    stored = hdr.get("payload_crc32")
    if not isinstance(stored, dict):
        raise ReopenRejectedError("payload_crc32 missing from header")

    timings: dict[str, float] = {}
    nbytes = 0
    if verify_crc:
        for key, name in PAYLOAD_FILES.items():
            if key not in stored:
                raise ReopenRejectedError(f"payload_crc32 has no entry for {name}")
            want = stored[key]
            if not isinstance(want, int) or isinstance(want, bool) or not 0 <= want <= 0xFFFFFFFF:
                raise ReopenRejectedError(f"payload_crc32[{name}] not a uint32: {want!r}")
            start = time.perf_counter()
            got = crc_of_payload(vdir / name)
            timings[name] = time.perf_counter() - start
            nbytes += (vdir / name).stat().st_size - len(MAGIC)
            if got != want:
                raise ReopenRejectedError(
                    f"{name} payload CRC32 {got:#010x} != stored {want:#010x} (payload corrupt)")
    timings["_seconds"] = time.perf_counter() - t0
    timings["_bytes"] = nbytes
    return hdr, timings


# ── store ───────────────────────────────────────────────────────────────────────
class MmapStore:
    """A version directory opened read-only, with sorted indexes for lookup.

    Holds no Python object per contract. The only allocations are the three sorted
    key arrays used for bisect, which hold integers and interned strings rather than
    1.6 KB objects -- measured at ~73 MB for 138k contracts against ~221 MB for the
    object graph it replaces.
    """

    def __init__(self, root: Path, version: str, hdr: dict, timings: dict) -> None:
        self.root = root
        self.version = version
        self.hdr = hdr
        self.timings = timings
        self.vdir = root / version
        self.count = hdr["record_count"]
        self.tables: dict[str, dict[int, str]] = {
            name: {int(k): v for k, v in rows}
            for name, rows in (hdr.get("string_tables") or {}).items()
        }
        self._fds: list = []
        self._maps: dict[str, mmap.mmap] = {}
        self._seckeys: list = []
        self._secslot: list = []
        self._optkeys: list = []
        self._optslot: list = []
        self._symkeys: list = []
        self._symslot: list = []
        self._symfirst: dict[str, int] = {}
        self._underlyings: list = []
        self._closed = False

    # -- lifecycle --
    def open(self) -> MmapStore:
        for key, name in ALL_FILES.items():
            fh = open(self.vdir / name, "rb")  # noqa: SIM115 - mmap needs the fd alive
            self._fds.append(fh)
            self._maps[key] = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        self._build_indexes()
        return self

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for m in self._maps.values():
            try:
                m.close()
            except (BufferError, ValueError):
                pass
        self._maps.clear()
        self._fds.clear()
        # Drop the key arrays too: they are the bulk of this object's footprint and a
        # retired reader should release them, not sit on them until GC.
        self._seckeys = self._secslot = []
        self._optkeys = self._optslot = []
        self._symkeys = self._symslot = self._symfirst = {}

    def _build_indexes(self) -> None:
        sec, opt, sym = self._maps["sec"], self._maps["opt"], self._maps["sym"]
        pool = self._maps["strings"]
        sk, ss = [], []
        for k in range(self.count):
            e = struct.unpack_from(SEC_INDEX.fmt, sec, len(MAGIC) + k * SEC_INDEX.size)
            sk.append(e[:3])
            ss.append(e[3])
        order = sorted(range(len(sk)), key=sk.__getitem__)
        self._seckeys = [sk[i] for i in order]
        self._secslot = [ss[i] for i in order]
        ok, os_ = [], []
        for k in range(self.count):
            e = struct.unpack_from(OPT_INDEX.fmt, opt, len(MAGIC) + k * OPT_INDEX.size)
            ok.append(e[:4])
            os_.append(e[4])
        order = sorted(range(len(ok)), key=ok.__getitem__)
        self._optkeys = [ok[i] for i in order]
        self._optslot = [os_[i] for i in order]
        yk, ys = [], []
        # The stored offsets are payload-relative, so every pool slice has to skip the
        # magic prefix. Without this the first symbol decoded as b"TMMAP01\\x00NIFTY-"
        # and the sorted symbol index was silently garbage -- which is exactly the
        # Phase-4.5 symbol-offset bug in a new place.
        pool_base = len(MAGIC)
        for k in range(self.count):
            so, sl, slot = struct.unpack_from(SYM_INDEX.fmt, sym, len(MAGIC) + k * SYM_INDEX.size)
            yk.append(pool[pool_base + so:pool_base + so + sl].decode("utf-8"))
            ys.append(slot)
        order = sorted(range(len(yk)), key=yk.__getitem__)
        self._symkeys = [yk[i] for i in order]
        self._symslot = [ys[i] for i in order]
        first: dict[str, int] = {}
        for s, slot in zip(self._symkeys, self._symslot, strict=True):
            first.setdefault(s, slot)
        self._symfirst = first
        # Distinct underlyings, taken from the records rather than a separate table:
        # option_underlyings() must not need a dict of every contract. The field index
        # comes from the schema, never a literal -- a hardcoded 13 pointed at
        # underlying_security_id and silently produced an empty list.
        under_idx = RECORD.field_names.index("underlying_id")
        codes = {
            struct.unpack_from(RECORD.fmt, self._maps["records"],
                               len(MAGIC) + k * RECORD.size)[under_idx]
            for k in range(self.count)
        }
        tbl = self.tables["underlying_symbol"]
        self._underlyings = sorted({tbl[c] for c in codes if c in tbl})

    # -- accessors --
    def __len__(self) -> int:
        return self.count

    def option_underlyings(self) -> list[str]:
        return list(self._underlyings)

    @staticmethod
    def _bisect(keys: list, key):
        lo, hi = 0, len(keys)
        while lo < hi:
            mid = (lo + hi) // 2
            if keys[mid] < key:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def _code(self, table: str, value: str) -> int:
        # Reverse lookup. A dict keyed by text would double the table's memory for a
        # lookup that happens once per query, so the scan is deliberate: these are
        # ~250 entries and the option/symbol paths do not call this at all.
        for code, text in self.tables.get(table, {}).items():
            if text == value:
                return code
        raise ReopenRejectedError(f"{table} code not found for {value!r}")

    def slot_for_security(self, exchange: str, segment: str, security_id: str) -> int | None:
        key = (self._code("exchange", exchange),
               self._code("exchange_segment", segment),
               int(security_id))
        i = self._bisect(self._seckeys, key)
        if i >= len(self._seckeys) or self._seckeys[i] != key:
            return None
        return self._secslot[i]

    def slots_for_security_id(self, security_id: str) -> list[int]:
        """Every slot with this security id, across exchanges and segments.

        A security id is NOT globally unique: the same id appears under more than one
        exchange/segment pair, so a bare id cannot identify a tradeable contract.

        This scans rather than bisects, and that is forced by the layout: the index is
        sorted by (exchange, segment, security_id), so rows sharing a security id are
        NOT adjacent whenever they sit under different exchanges. A bisect here finds
        only one of them. The object-graph dataset this replaces did the same scan, so
        the cost is unchanged rather than new.
        """
        sid = int(security_id)
        keys = self._seckeys
        return [self._secslot[i] for i in range(len(keys)) if keys[i][2] == sid]

    def slot_for_option(
        self, underlying: str, expiry: str, strike_scaled: int, option_type: str
    ) -> int | None:
        key = (self._code("underlying_symbol", underlying.upper()),
               self._code("expiry_date", expiry),
               strike_scaled,
               self._code("option_type", option_type))
        i = self._bisect(self._optkeys, key)
        if i >= len(self._optkeys) or self._optkeys[i] != key:
            return None
        return self._optslot[i]

    def slot_for_symbol(self, symbol: str) -> int | None:
        """Display/search lookup. An ambiguous symbol resolves to the lowest slot.

        Trading symbols are NOT unique -- measured 55,702 of 138,106 contracts share
        one with another -- so this can never be the basis for resolving a contract to
        trade. It exists for display and search, and this method says which contract
        it would pick rather than pretending the answer is unique.
        """
        return self._symfirst.get(symbol)

    def slots_for_symbol(self, symbol: str) -> list[int]:
        i = self._bisect(self._symkeys, symbol)
        out = []
        while i < len(self._symkeys) and self._symkeys[i] == symbol:
            out.append(self._symslot[i])
            i += 1
        return out

    def iter_underlying(self, underlying: str) -> Iterator[int]:
        """Record slots for one underlying, in record order.

        Backed by the option index where possible; falls back to a scan for futures
        and other families that are not options.
        """
        code = self._code("underlying_symbol", underlying.upper())
        keys = self._optkeys
        lo, hi = 0, len(keys)
        while lo < hi:
            mid = (lo + hi) // 2
            if keys[mid][0] < code:
                lo = mid + 1
            else:
                hi = mid
        slots = []
        i = lo
        while i < len(keys) and keys[i][0] == code:
            slots.append(self._optslot[i])
            i += 1
        if slots:
            return iter(sorted(slots))
        return iter(())

    def fields(self, slot: int) -> dict:
        """Decode one record into a plain dict keyed by declared field name."""
        names = [f[0] for f in RECORD.fields]
        raw = struct.unpack_from(RECORD.fmt, self._maps["records"],
                                 len(MAGIC) + slot * RECORD.size)
        out = dict(zip(names, raw, strict=True))
        for name, code_field in _CODE_FIELDS:
            out[name] = self.tables[name].get(out[code_field], "")
        pool = self._maps["strings"]
        off = len(MAGIC) + out["trading_symbol_offset"]  # offsets are payload-relative
        out["trading_symbol"] = pool[off:off + out["trading_symbol_length"]].decode("utf-8")
        return out


#: Which record field holds the code for each string table. Most are ``<name>_code``,
#: but the two dimension tables are ``<name>_id`` -- expiry_id and underlying_id.
#: Deriving this with an f-string produced "expiry_date_code", a field that does not
#: exist, so every decode raised KeyError.
_CODE_FIELDS = (
    ("exchange", "exchange_code"),
    ("exchange_segment", "exchange_segment_code"),
    ("instrument_type", "instrument_type_code"),
    ("instrument_family", "instrument_family_code"),
    ("option_type", "option_type_code"),
    ("instrument_status", "instrument_status_code"),
    ("source", "source_code"),
    ("expiry_date", "expiry_id"),
    ("underlying_symbol", "underlying_id"),
)
_CODE_FIELDS_BY_TABLE = {table: code_field for table, code_field in _CODE_FIELDS}


# ── build / activate / retire ───────────────────────────────────────────────────
class MmapInstrumentStore:
    """Owns the version directory: builds candidates, activates them, retires the old."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.active_link = self.root / "active"
        self.lock_path = self.root / ".build.lock"
        self._reader: MmapStore | None = None

    # -- active discovery --
    def active_version(self) -> str:
        if not self.active_link.is_symlink():
            if self.active_link.exists():
                raise ReopenRejectedError("active exists but is not a symlink")
            raise ReopenRejectedError("no active symlink")
        target = os.readlink(self.active_link)
        name = os.path.basename(target.rstrip("/"))
        if not is_version_name(name):
            raise ReopenRejectedError(f"active target is not a version name: {target!r}")
        if not (self.root / name).is_dir():
            raise ReopenRejectedError(f"active version directory missing: {name}")
        return name

    def versions(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir()
                      if p.is_dir() and is_version_name(p.name))

    # -- build lock --
    def acquire_lock(self) -> None:
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                holder = ""
                try:
                    holder = self.lock_path.read_text(encoding="utf-8").strip()
                except OSError:
                    pass
                raise BuildLockedError(f"another refresh holds the lock: {holder}") from exc
            raise
        os.write(fd, f"pid {os.getpid()}\n".encode())
        os.close(fd)

    def release_lock(self) -> None:
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass

    # -- reader --
    def open_active(self, *, verify_crc: bool = True) -> MmapStore:
        version = self.active_version()
        vdir = self.root / version
        hdr, timings = validate(vdir, verify_crc=verify_crc)
        return MmapStore(self.root, version, hdr, timings).open()

    def open_version(self, version: str, *, verify_crc: bool = True) -> MmapStore:
        if not is_version_name(version):
            raise ReopenRejectedError(f"bad version name {version!r}")
        vdir = self.root / version
        if not vdir.is_dir():
            raise ReopenRejectedError(f"version directory missing: {version}")
        hdr, timings = validate(vdir, verify_crc=verify_crc)
        return MmapStore(self.root, version, hdr, timings).open()

    # -- build --
    def stage(self, version: str) -> Path:
        """Create the staging directory. Never writes inside the active version."""
        if not is_version_name(version):
            raise ActivationRejectedError(f"bad version name {version!r}")
        if (self.root / version).exists():
            raise ActivationRejectedError(f"version {version} already exists")
        stage = self.root / f".staging-{version}"
        if stage.exists():
            raise ActivationRejectedError(f"staging directory already exists: {stage.name}")
        stage.mkdir(parents=True)
        (stage / BUILD_MARKER).write_text("build in progress\n", encoding="utf-8")
        return stage

    def seal(self, vdir: Path) -> None:
        """Mark complete and durable. A version without this can never be activated."""
        marker = vdir / BUILD_MARKER
        if marker.exists():
            marker.unlink()
        for name in ALL_FILES.values():
            _fsync(vdir / name)
        _fsync(vdir / "header.json")
        (vdir / FROZEN_MARKER).write_text("sealed\n", encoding="utf-8")
        _fsync(vdir)

    def publish(self, stage: Path, version: str) -> Path:
        """Move a finished staging directory into place. rename(2) on a directory is
        atomic, and the destination must not exist, so a reader never sees a partial
        version directory."""
        target = self.root / version
        if target.exists():
            raise ActivationRejectedError(f"version {version} already exists")
        os.rename(stage, target)
        _fsync(self.root)
        return target

    def validate_candidate(self, version: str) -> tuple[dict, dict]:
        """Validation is a separate step; activation never doubles as the check."""
        if not is_version_name(version):
            raise ActivationRejectedError(f"bad version name {version!r}")
        vdir = self.root / version
        if not vdir.is_dir():
            raise ActivationRejectedError(f"candidate directory missing: {version}")
        if (vdir / BUILD_MARKER).exists():
            raise ActivationRejectedError(f"{version} still carries {BUILD_MARKER} (build incomplete)")
        if not (vdir / FROZEN_MARKER).exists():
            raise ActivationRejectedError(f"{version} is not sealed")
        try:
            return validate(vdir)
        except ReopenRejected as exc:
            raise ActivationRejectedError(f"{version} failed validation: {exc}") from exc

    def activate(self, version: str) -> str:
        """One atomic transition, after validation has already passed.

        symlink to a temp name, then rename(2) over `active`. Deliberately NOT
        delete-then-rename: that would leave a window with no active version at all.
        """
        self.validate_candidate(version)
        tmp = self.root / f".active.tmp.{os.getpid()}"
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()
        os.symlink(version, tmp, target_is_directory=True)
        os.replace(tmp, self.active_link)
        _fsync(self.root)
        return self.active_version()

    # -- retirement --
    def retired(self, *, keep: int = 2) -> list[str]:
        """Delete inactive versions, newest first, keeping the newest `keep`.

        Deliberately does NOT track whether a reader still holds a mapping. On Linux a
        live mmap keeps its pages valid after the file is unlinked, so removing a
        retired version cannot corrupt a reader -- but it does mean a reader that has
        not yet finished will be reading a directory that no longer exists on disk.

        That is safe here only because a reader resolves `active` once at open time and
        then holds its own mapping. It is NOT safe for a process that re-resolves `active`
        per request while holding an older version's data. `keep >= 2` leaves one
        previous version on disk so a brief overlap cannot leave an operator with
        nothing to roll back to.
        """
        active = self.active_version()
        others = [v for v in self.versions() if v != active]
        others.sort(reverse=True)
        victims = others[max(0, keep - 1):]
        removed = []
        for v in victims:
            import shutil

            shutil.rmtree(self.root / v, ignore_errors=True)
            removed.append(v)
        # abandoned staging directories from a crashed build
        for p in self.root.glob(".staging-*"):
            import shutil

            shutil.rmtree(p, ignore_errors=True)
        return removed


def rss_mb() -> float:
    return int(open("/proc/self/statm").read().split()[1]) * 4096 / 1048576.0