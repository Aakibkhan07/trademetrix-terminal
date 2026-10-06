"""Mutation check for the OMS derivative-identity regression tests.

Each mutation removes one piece of the fix. If a mutation survives, the corresponding test
cannot see that regression.

The baseline is the unmutated suite, which must be green first -- a mutation harness whose
baseline fails reports nonsense.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

MANAGER = Path("oms/manager.py")
MODELS = Path("oms/models.py")
ADAPTER = Path("brokers/dhan_adapter.py")
TESTS = "tests/test_oms_derivative_identity.py"

MUTATIONS = [
    (
        # The whole derivative block removed from the builder. One mutation rather than four:
        # the four original per-field mutations had to be SKIPped when the rebuild was
        # extracted into `build_execution_request`, because their anchors no longer existed.
        # A skip is not a catch, so this replaces them.
        "N1 the builder stops restoring the derivative identity",
        MANAGER,
        "        instrument_type=order.instrument_type or None,\n"
        "        expiry_date=order.expiry_date or None,\n"
        "        strike_price=order.strike_price,\n"
        "        option_type=order.option_type or None,\n"
        "        validity=order.validity or None,\n",
        "",
    ),
    (
        "N2 the builder stops restoring instrument_type alone",
        MANAGER,
        "        instrument_type=order.instrument_type or None,\n",
        "",
    ),
    (
        "N3 the builder stops restoring expiry_date alone",
        MANAGER,
        "        expiry_date=order.expiry_date or None,\n",
        "",
    ),
    (
        "N4 place_order stops storing instrument_type on the OMS order",
        MANAGER,
        '            instrument_type=_text(req.instrument_type),\n',
        '            instrument_type="",\n',
    ),
    (
        "N5 place_order stops storing expiry_date on the OMS order",
        MANAGER,
        "            expiry_date=_text(req.expiry_date),\n",
        '            expiry_date="",\n',
    ),
    (
        "N6 OmniOrder loses the instrument_type field",
        MODELS,
        '    instrument_type: str = ""\n',
        "",
    ),
    (
        "N11 the worker stops using the extracted builder",
        MANAGER,
        "                req = build_execution_request(order)",
        "                req = ExecutionRequest(user_id=order.user_id, broker=order.broker)\n",
    ),
    (
        # This is the bug that was actually shipped in the first version of the fix: `or None`
        # turns a disclosed quantity of 0 into None, which fails pydantic's int validation and
        # kills the worker for every ordinary order.
        "N10 disclosed_quantity coerced to None instead of 0",
        MANAGER,
        "disclosed_quantity=int(order.disclosed_quantity or 0),",
        "disclosed_quantity=order.disclosed_quantity or None,",
    ),
    (
        # The first attempt at this mutation swapped the getattr for a bare str(), and it
        # SURVIVED -- correctly. `InstrumentType` and `OptionType` are StrEnum, so
        # `str(member)` already yields the value and the two forms are equivalent. That was a
        # bad mutation, not a gap in the tests. This one removes the None handling, which is
        # the genuinely observable part: a null request field must store "" and not the text
        # "None".
        "N8 _text stops handling None",
        MANAGER,
        '    if value is None:\n        return ""\n',
        "",
    ),
    (
        "N9 the adapter derives the segment from the order symbol again",
        ADAPTER,
        "        seg = instrument.exchange_segment\n        security_id = instrument.security_id",
        "        seg = order.exchange.value\n        security_id = order.symbol",
    ),
]


def run_suite() -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", TESTS, "-q", "--no-header", "-p", "no:cacheprovider"],
        capture_output=True, text=True,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-800:]


def main() -> int:
    print("  ── baseline ──")
    ok, out = run_suite()
    print(f"     {'PASS' if ok else 'FAIL'}  suite green on the real code")
    if not ok:
        print(out)
        return 1

    print("\n  ── each mutation must be caught ──")
    survivors = []
    for label, path, old, new in MUTATIONS:
        original = path.read_text()
        if old not in original:
            print(f"     SKIP    {label}: anchor not found")
            survivors.append(label)
            continue
        with tempfile.NamedTemporaryFile("w", delete=False) as fh:
            fh.write(original)
            backup = Path(fh.name)
        try:
            path.write_text(original.replace(old, new, 1))
            ok, out = run_suite()
            caught = not ok
            print(f"     {'caught' if caught else 'SURVIVED'}  {label}")
            if not caught:
                survivors.append(label)
        finally:
            path.write_text(original)
            backup.unlink(missing_ok=True)

    restored, _ = run_suite()
    print(f"\n  ── source restored, suite green again: {restored} ──")
    if survivors:
        print(f"\n  {len(survivors)} mutation(s) SURVIVED:")
        for s in survivors:
            print(f"    - {s}")
        return 1
    print(f"\n  all {len(MUTATIONS)} mutations caught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
