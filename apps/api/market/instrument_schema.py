"""Binary schema for the on-disk instrument master. The single source of truth.

Every ``struct.Struct`` used by the store is generated from the field lists below,
and each constructor asserts that ``struct.size`` equals the width computed from the
declared fields. A width mismatch therefore fails at import, not on the third byte of
a file that has already been written.

Widths that were measured wrong once, and why they are what they are:

``security_id`` is **uint32**, not uint16. The real master contains 114,066
contracts whose security id exceeds 65,535 (max observed 1,162,670). At uint16 they
wrapped silently and 22,390 contracts were dropped without an error.

``lot_size`` is **uint32** for the same reason. The ingested universe's largest lot is
71,475; the raw file also contains a 10,000,000 lot outside the ingested families,
which is why 16 bits is not safe even though 71,475 fits.

``underlying_id`` and ``expiry_id`` are **uint16** because they are codes into the
persisted string table, not the strings themselves. 234 distinct underlyings and 66
expiries were measured, so 16 bits is ample; the table is what would break first and
validation catches that as a record-count mismatch.

``strike_scaled`` and ``tick_scaled`` are **signed int32** at 1/100 and 1/100000
scale respectively, so negative strikes (a real case in the master) survive and a
0.00001 tick is not rounded to zero.

Duplication note: ``by_trading_symbol`` is not unique -- 55,702 of 138,106 contracts
share a symbol with another. It is a display and search index only. The canonical
execution identity is ``(exchange, exchange_segment, security_id)`` and the canonical
option identity is ``(underlying, expiry, strike, option_type)``.
"""

from __future__ import annotations

import struct

#: type name -> (struct code, width in bytes)
TYPES: dict[str, tuple[str, int]] = {
    "u8": ("B", 1),
    "u16": ("H", 2),
    "u32": ("I", 4),
    "i32": ("i", 4),
}


class Schema:
    """A named, ordered list of (field_name, binary_type).

    The struct format is derived here and nowhere else, and its size is checked
    against the declared widths on construction.
    """

    def __init__(self, name: str, fields: tuple[tuple, ...]) -> None:
        self.name = name
        self.fields = tuple(fields)
        names = [f[0] for f in self.fields]
        if len(names) != len(set(names)):
            raise ValueError(f"{name}: duplicate field name")
        for field_name, type_name in self.fields:
            if type_name not in TYPES:
                raise ValueError(f"{name}.{field_name}: unknown type {type_name!r}")
        self.fmt = "<" + "".join(TYPES[t][0] for _, t in self.fields)
        self.calculated_size = sum(TYPES[t][1] for _, t in self.fields)
        self._struct = struct.Struct(self.fmt)
        if self._struct.size != self.calculated_size:
            raise ValueError(
                f"{name}: generated format {self.fmt} is {self._struct.size}B but the "
                f"declared fields total {self.calculated_size}B")

    @property
    def size(self) -> int:
        return self._struct.size

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(f[0] for f in self.fields)

    def pack(self, **values: object) -> bytes:
        return self._struct.pack(*(values[n] for n, _ in self.fields))

    def unpack(self, buf: bytes) -> dict[str, object]:
        return dict(zip(self.field_names, self._struct.unpack(buf), strict=True))

    def __repr__(self) -> str:
        return f"<Schema {self.name} fmt={self.fmt} size={self.size}>"


RECORD = Schema("RECORD", (
    ("security_id", "u32"),
    ("exchange_code", "u8"),
    ("exchange_segment_code", "u8"),
    ("instrument_type_code", "u8"),
    ("instrument_family_code", "u8"),
    ("option_type_code", "u8"),
    ("instrument_status_code", "u8"),
    ("source_code", "u8"),
    ("lot_size", "u32"),
    ("strike_scaled", "i32"),
    ("tick_scaled", "i32"),
    ("expiry_id", "u16"),
    ("underlying_id", "u16"),
    ("underlying_security_id", "u32"),
    ("trading_symbol_offset", "u32"),
    ("trading_symbol_length", "u16"),
))

SEC_INDEX = Schema("SEC_INDEX", (
    ("exchange_code", "u8"),
    ("exchange_segment_code", "u8"),
    ("security_id", "u32"),
    ("record_slot", "u32"),
))

SYM_INDEX = Schema("SYM_INDEX", (
    ("symbol_offset", "u32"),
    ("symbol_length", "u16"),
    ("record_slot", "u32"),
))

OPT_INDEX = Schema("OPT_INDEX", (
    ("underlying_id", "u16"),
    ("expiry_id", "u16"),
    ("strike_scaled", "i32"),
    ("option_type_code", "u8"),
    ("record_slot", "u32"),
))

ALL_SCHEMAS = (RECORD, SEC_INDEX, SYM_INDEX, OPT_INDEX)

# Pinned so a change to the record layout cannot land silently. A stored dataset whose
# record size differs is rejected on open by the format/schema checks; these two lines
# make the mismatch visible at import time too.
assert RECORD.size == 37, f"record layout must stay 37 bytes, got {RECORD.size}"
assert SEC_INDEX.size == 10, f"security index must stay 10 bytes, got {SEC_INDEX.size}"
assert SYM_INDEX.size == 10, f"symbol index must stay 10 bytes, got {SYM_INDEX.size}"
assert OPT_INDEX.size == 13, f"option index must stay 13 bytes, got {OPT_INDEX.size}"