"""Is the Dhan master test fixture actually date-independent?

`test_dhan_master_memory.py` failed on 2026-10-13 with no code change: its fixture pinned NIFTY
expiries to 2026-10-06, and `expiries()` filters on `expiry_date >= date.today()`. The fixture is
now built from offsets off today, so it should pass on any date.

A test that passes today proves nothing about a test that failed because of the calendar. This
moves the clock instead: the same assertions must hold at simulated dates a year either side of
now, and the old literal-dated fixture must be shown to fail at today's clock -- otherwise the
fix is a coincidence.

`datetime.date` is immutable and `today` is a C slotmethod, so it cannot be patched. The clock is
moved by shadowing the `date` name in the module that calls it, with a subclass whose `today()`
returns the pinned day.

Run from `apps/api`:

    .venv/bin/python scripts/prove_dhan_master_date_independence.py
"""
import asyncio
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

#: Offsets the fixture uses. Mirrors tests/test_dhan_master_memory.py -- if the fixture's
#: constants ever stop matching these, the test is no longer clock-relative and this proves it.
NEAR_DAYS, FAR_DAYS, SENSEX_DAYS, STOCK_DAYS = 9, 16, 11, 32

#: The assertions `test_expiry_and_strike_listings_stay_consistent` makes, with the strike
#: listings the fixture rows actually define:
#:   _NEAR -> 22400 CE, 22400 PE, 22600 CE, 22600 PE
#:   _FAR  -> 22400 CE, 22400 PE
STRIKE_EXPECTATIONS = [
    ("_NEAR", 22400, "CE", True),
    ("_NEAR", 22600, "CE", True),
    ("_FAR", 22400, "CE", True),
    ("_FAR", 22400, "PE", True),
    ("_FAR", 22600, "CE", False),
    ("_FAR", 22600, "PE", False),
]


class _FakeDate(date):
    """`today()` returns whatever the caller pinned."""

    pinned: date = date(2026, 1, 1)

    @classmethod
    def today(cls) -> "_FakeDate":
        return cls(cls.pinned.year, cls.pinned.month, cls.pinned.day)


def offsets_at(day: date) -> dict[str, str]:
    return {
        "_NEAR": (day + timedelta(days=NEAR_DAYS)).isoformat(),
        "_FAR": (day + timedelta(days=FAR_DAYS)).isoformat(),
        "_SENSEX_EXP": (day + timedelta(days=SENSEX_DAYS)).isoformat(),
        "_STOCK_EXP": (day + timedelta(days=STOCK_DAYS)).isoformat(),
    }


def retime(csv: str, frm: dict[str, str], to: dict[str, str]) -> str:
    """Rewrite one set of expiry dates in the fixture to another.

    Single pass over a substitution table. Replacing one at a time cascades: rewriting
    2026-10-27 -> 2026-11-03 and then 2026-11-03 -> 2026-11-10 clobbers the date just written,
    which showed up as strikes vanishing from an expiry they were on.
    """
    table = {frm[k]: to[k] for k in frm}
    return re.sub("|".join(re.escape(k) for k in sorted(table, key=len, reverse=True)),
                  lambda m: table[m.group(0)], csv)


def with_clock(day: date):
    """Pin the filter clock for the duration of the block. The caller MUST assert inside it.

    Restoring the patch before the assertions run is a silent trap: the provider builds fine
    under the pinned clock and then filters under the real one, so a simulated past date reads
    as "this contract expired long ago".
    """
    import contextlib

    import market.dhan_instruments as di

    @contextlib.contextmanager
    def _cm():
        orig = di.date
        _FakeDate.pinned = day
        di.date = _FakeDate  # type: ignore[assignment]
        try:
            yield
        finally:
            di.date = orig  # type: ignore[assignment]

    return _cm()


def load_provider(csv: str):
    sys.modules.pop("test_dhan_master_memory", None)
    import test_dhan_master_memory as tm

    p = tm.make_provider(csv)
    asyncio.run(p.refresh())
    return p


def fixture_is_clock_relative() -> list[str]:
    """Structural check: are the fixture's dates derived from the clock, or written as literals?

    Read from the AST, not by importing: the constants are computed at import time, so importing
    can only ever tell you what they are *now*, never whether they will move. This is the
    assertion that would catch someone putting a literal date back.
    """
    import ast

    path = Path(__file__).resolve().parent.parent / "tests" / "test_dhan_master_memory.py"
    tree = ast.parse(path.read_text())
    names = {"_NEAR", "_FAR", "_SENSEX_EXP", "_STOCK_EXP"}

    problems: list[str] = []
    found: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in names:
                found.add(target.id)
                src = ast.unparse(node.value)
                if "today()" not in src:
                    problems.append(f"{target.id} = {src}  <- not derived from the clock")
    missing = names - found
    if missing:
        problems.append(f"not found at module level: {sorted(missing)}")
    return problems


def check(day: date) -> tuple[bool, list[str]]:
    """The fixture as it would be built at `day`, asserted against a clock pinned to `day`.

    The CSV is retimed rather than re-imported, because the module computes its constants once at
    import -- against whatever the real clock was. Retiming is what "this fixture, on that date"
    actually means.
    """
    import test_dhan_master_memory as tm

    want = offsets_at(day)
    csv = retime(tm.CSV, offsets_at(date.today()), want)

    failures: list[str] = []
    with with_clock(day):
        p = load_provider(csv)
        for key, strike, otype, present in STRIKE_EXPECTATIONS:
            expiry = want[key]
            got = strike in p.strikes("NIFTY", expiry, option_type=otype)
            if got != present:
                failures.append(f"{strike} {otype}@{expiry}: listed={present}, got {got}")
        for key in ("_NEAR", "_FAR"):
            if want[key] not in p.expiries("NIFTY"):
                failures.append(f"{want[key]} missing from expiries()")
    return not failures, failures


def old_fixture_fails_today() -> bool:
    """The pre-fix literal fixture at the real clock -- the failure being explained."""
    import test_dhan_master_memory as tm

    today = date.today()
    old = {
        "_NEAR": "2026-10-06", "_FAR": "2026-10-13",
        "_SENSEX_EXP": "2026-10-08", "_STOCK_EXP": "2026-10-29",
    }
    csv = retime(tm.CSV, offsets_at(today), old)
    with with_clock(today):
        p = load_provider(csv)
        return "2026-10-06" not in p.expiries("NIFTY")


def main() -> int:
    today = date.today()
    print(f"  real clock: {today.isoformat()}")
    print()

    broken = old_fixture_fails_today()
    print(f"  the OLD literal fixture at today's clock: "
          f"{'fails, as reported' if broken else 'PASSES -- the calendar-rot theory is wrong'}")
    if not broken:
        print("  Stop: the failure is not calendar rot. Investigate before trusting this fix.")
        return 1
    print()

    structural = fixture_is_clock_relative()
    print(f"  fixture dates derived from the clock (AST): "
          f"{'yes, all four' if not structural else 'NO -- ' + '; '.join(structural)}")
    if structural:
        print("  Stop: a literal date is back in the fixture.")
        return 1
    print()

    print(f"  {'simulated clock':22} {'result':7} detail")
    print(f"  {'-' * 22} {'-' * 7} {'-' * 40}")
    failures = 0
    for offset in (-400, -180, -30, -7, 0, 7, 45, 200, 400):
        day = today + timedelta(days=offset)
        ok, msgs = check(day)
        failures += not ok
        print(f"  {day.isoformat():22} {'pass' if ok else 'FAIL':7} {'; '.join(msgs)}")

    print()
    if failures:
        print(f"  {failures} simulated date(s) still fail -- the fixture is date-dependent")
        return 1
    print("  9/9 simulated dates pass, spanning two years either side of today.")
    print("  The fixture follows the clock, so this can no longer rot on a date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())