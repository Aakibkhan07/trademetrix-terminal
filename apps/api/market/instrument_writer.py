"""Encode parsed Dhan contracts into a versioned, mmap-readable store.

Kept separate from the store so that the writer and the reader can be tested against
each other: the writer's only job is to produce a directory that
``instrument_store.validate`` accepts and that answers the same lookups the in-memory
dataset answered.

Dimensions are interned to small integer codes as contracts stream past, because a
code keeps a 37-byte record a fixed size. The tables are persisted in the header, so
the reader needs no CSV and no parser to turn a code back into a string.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable
from pathlib import Path

from market.instrument_schema import OPT_INDEX, RECORD, SEC_INDEX, SYM_INDEX
from market.instrument_store import (
    MAGIC,
    STRING_TABLES,
    ActivationRejectedError,
    MmapInstrumentStore,
    _fsync,
    crc_of_payload,
    write_header,
)

SCALES = {"strike": 100, "tick": 100_000}


class _Interner:
    """Assigns a stable small integer to each distinct string value.

    Insertion order is the code order, which is deterministic for a given input order,
    so the same master produces byte-identical files and therefore the same CRCs.
    """

    def __init__(self, names: Iterable[str]) -> None:
        self.tables: dict[str, dict[str, int]] = {name: {} for name in names}

    def code(self, name: str, value: object) -> int:
        key = "" if value is None else str(value)
        table = self.tables[name]
        if key not in table:
            table[key] = len(table)
        return table[key]

    def as_int_tables(self) -> dict[str, dict[int, str]]:
        return {name: {code: text for text, code in table.items()}
                for name, table in self.tables.items()}

    def as_json_tables(self) -> dict[str, dict[str, int]]:
        return {name: {str(code): text for text, code in table.items()}
                for name, table in self.tables.items()}


def _scaled(value: object, scale: int) -> int:
    """Scale to an integer. An absent value is 0, never a string.

    `value or ""` on a numeric field turns a legitimate 0.0 into "", which then fails
    the int conversion and silently drops the contract. The None check is explicit for
    exactly that reason.
    """
    if value is None:
        return 0
    return int(round(float(value) * scale))


def encode_version(
    store: MmapInstrumentStore,
    version: str,
    contracts: list,
    *,
    source: dict,
) -> Path:
    """Write a complete, sealed version directory. Does NOT activate it."""
    stage = store.stage(version)
    interner = _Interner(STRING_TABLES)
    pool_len = 0
    n = len(contracts)
    sec_buf = bytearray()
    opt_buf = bytearray()
    sym_buf = bytearray()

    with open(stage / "records.dat", "wb") as rf, open(stage / "strings.dat", "wb") as pf:
        rf.write(MAGIC)
        pf.write(MAGIC)
        for slot, c in enumerate(contracts):
            symbol = str(c.trading_symbol or "").encode("utf-8")
            offset = pool_len
            pf.write(symbol)
            pool_len += len(symbol)
            rf.write(RECORD.pack(
                security_id=int(c.security_id),
                exchange_code=interner.code("exchange", c.exchange),
                exchange_segment_code=interner.code("exchange_segment", c.exchange_segment),
                instrument_type_code=interner.code("instrument_type", c.instrument_type),
                instrument_family_code=interner.code("instrument_family", c.instrument_family),
                option_type_code=interner.code("option_type", c.option_type),
                instrument_status_code=interner.code("instrument_status", c.instrument_status),
                source_code=interner.code("source", c.source),
                lot_size=int(c.lot_size),
                strike_scaled=_scaled(c.strike_price, SCALES["strike"]),
                tick_scaled=_scaled(c.tick_size, SCALES["tick"]),
                expiry_id=interner.code("expiry_date", c.expiry_date),
                underlying_id=interner.code("underlying_symbol", c.underlying_symbol),
                underlying_security_id=int(c.underlying_security_id or 0),
                trading_symbol_offset=offset,
                trading_symbol_length=len(symbol),
            ))
            sec_buf += SEC_INDEX.pack(
                exchange_code=interner.code("exchange", c.exchange),
                exchange_segment_code=interner.code("exchange_segment", c.exchange_segment),
                security_id=int(c.security_id),
                record_slot=slot,
            )
            opt_buf += OPT_INDEX.pack(
                underlying_id=interner.code("underlying_symbol", c.underlying_symbol),
                expiry_id=interner.code("expiry_date", c.expiry_date),
                strike_scaled=_scaled(c.strike_price, SCALES["strike"]),
                option_type_code=interner.code("option_type", c.option_type),
                record_slot=slot,
            )
            sym_buf += SYM_INDEX.pack(
                symbol_offset=offset, symbol_length=len(symbol), record_slot=slot)

    for key, buf in (("sec", sec_buf), ("opt", opt_buf), ("sym", sym_buf)):
        with open(stage / f"{key}.dat", "wb") as fh:
            fh.write(MAGIC)
            fh.write(bytes(buf))

    # fsync the payloads BEFORE measuring: the checksum has to describe what is on disk
    sizes, crcs = {}, {}
    for key, name in (("records", "records.dat"), ("strings", "strings.dat"),
                      ("sec", "sec.dat"), ("opt", "opt.dat"), ("sym", "sym.dat")):
        _fsync(stage / name)
        sizes[key] = (stage / name).stat().st_size
        crcs[key] = crc_of_payload(stage / name)

    write_header(stage, record_count=n, tables=interner.as_int_tables(),
                 sizes=sizes, crcs=crcs, source=source)
    store.publish(stage, version)
    store.seal(stage.parent / version)
    return stage.parent / version


def build_from_contracts(
    root: str | Path,
    version: str,
    contracts: list,
    *,
    source: dict,
    activate: bool = True,
) -> MmapInstrumentStore:
    """Build, validate, and (by default) activate. Returns the store."""
    store = MmapInstrumentStore(root)
    encode_version(store, version, contracts, source=source)
    store.validate_candidate(version)
    if activate:
        store.activate(version)
    return store