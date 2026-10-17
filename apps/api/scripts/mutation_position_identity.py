"""Does the position-identity test still catch what it was written to catch?

Two tests in `tests/test_position_identity.py` started failing on 2026-10-18 with no code change.
The cause was pinned ids transcribed from one snapshot of the live Dhan master: Dhan reassigns
security ids as contracts roll, so `40749` became a HINDZINC contract and the tests were
asserting against an instrument they had never named. The fix picks real contracts from the
master at test time, by relationship rather than by id.

That fix trades a hardcoded value for a selection step, and a selection step can quietly pass
for the wrong reason -- pick the wrong contract and the assertion still holds. So each mutation
below puts a specific defect back:

  * pin the ids again -> the tests must fail, which is what they did
  * pair a CE with a PE from *different* strikes -> the pairing assertion must fail
  * pick only one expiry -> the two-expiry test must fail

The last two are mutations of the fixture-selection logic in the test itself. A guard that only
catches the bug it was written for is not a guard.

Read-only apart from a temporary edit to the test module, restored in a `finally`. Needs network
(it loads the real Dhan master), exactly as the test module does.

Run from `apps/api`:

    .venv/bin/python scripts/mutation_position_identity.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "tests" / "test_position_identity.py"
TESTS = "tests/test_position_identity.py"

SELECT_CE = '        self.ce = first["CE"]'
SELECT_PE = '        self.pe = first["PE"]'
SELECT_NEXT = ('        other = [v["CE"] for v in shared '
               'if v["CE"].expiry_date != self.ce.expiry_date]')
SELECT_NEXT_EMPTY = "        other = []"

# The whole pairing-check body, matched as a block: replacing one line of a multi-line assert
# leaves the rest standing, and the mutation "survives" for the wrong reason.
PAIR_BLOCK = '''        assert contracts.ce.strike_price == contracts.pe.strike_price, (
            f"fixture paired {contracts.ce.trading_symbol} with "
            f"{contracts.pe.trading_symbol} -- different strikes"
        )
        assert contracts.ce.expiry_date == contracts.pe.expiry_date, (
            f"fixture paired {contracts.ce.trading_symbol} with "
            f"{contracts.pe.trading_symbol} -- different expiries"
        )'''

#: Selection that pairs a CE with a PE from a different strike/expiry.
SELECT_PE_WRONG = '        self.pe = next(v["PE"] for v in shared if v is not first)'

MUTATIONS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "the security ids are pinned to one snapshot again",
        [(SELECT_CE,
          '        self.ce = first["CE"]\n        self.pe = first["PE"]\n'
          '        self.ce = type("C", (), {"security_id": "40749", "trading_symbol":\n'
          '            "HINDZINC-Nov2026-370-CE", "expiry_date": "2026-11-23",\n'
          '            "strike_price": 370.0, "option_type": "CE", "lot_size": 0,\n'
          '            "exchange": "NSE", "exchange_segment": "NSE_FNO"})()')],
    ),
    (
        "the CE/PE pair is drawn from different strikes",
        [(SELECT_PE, SELECT_PE_WRONG)],
    ),
    # Undetectable by construction, and listed so it is not mistaken for a gap. Deleting an
    # assertion while the data stays correct produces no wrong behaviour for any test to
    # observe, so no suite can catch it. The meaningful version of this mutation -- delete the
    # check AND feed it a wrong pair -- is the next one, and it is caught.
    (
        "UNDETECTABLE: pairing check deleted, data still correct",
        [(PAIR_BLOCK, "        pass")],
    ),
    # The three below are COUPLED: weaken the check AND corrupt the data at the same time.
    # A tautological assertion is indistinguishable from a correct one when the data is
    # correct, so weakening it alone proves nothing -- the mutation has to also feed the
    # weakened check a fixture that a correct check would reject. Getting these wrong is how
    # the first version of this harness reported three survivors that were not real gaps.
    (
        "strike check compares a contract to itself, and the pair is wrong",
        [(PAIR_BLOCK,
          PAIR_BLOCK.replace("contracts.ce.strike_price == contracts.pe.strike_price",
                             "contracts.ce.strike_price == contracts.ce.strike_price")),
         (SELECT_PE, SELECT_PE_WRONG)],
    ),
    (
        "expiry check compares a contract to itself, and the pair is wrong",
        [(PAIR_BLOCK,
          PAIR_BLOCK.replace("contracts.ce.expiry_date == contracts.pe.expiry_date",
                             "contracts.ce.expiry_date == contracts.ce.expiry_date")),
         (SELECT_PE, SELECT_PE_WRONG)],
    ),
    (
        "the whole pairing check is deleted, and the pair is wrong",
        [(PAIR_BLOCK, "        pass"), (SELECT_PE, SELECT_PE_WRONG)],
    ),
    (
        "only one expiry is ever offered",
        [(SELECT_NEXT, SELECT_NEXT_EMPTY)],
    ),
]




def run_tests() -> tuple[int, str]:
    p = subprocess.run(
        [".venv/bin/python", "-m", "pytest", TESTS, "-q", "-W", "ignore::DeprecationWarning",
         "-p", "no:cacheprovider", "--asyncio-mode=auto"],
        cwd=ROOT, capture_output=True, text=True,
    )
    lines = [ln for ln in p.stdout.strip().splitlines() if ln.strip()]
    return p.returncode, (lines[-1] if lines else "(no output)")


def main() -> int:
    original = TARGET.read_text()
    for name, edits in MUTATIONS:
        for old, _new in edits:
            if old not in original:
                print(f"  !! mutation does not apply: {name!r} -- update the harness",
                      file=sys.stderr)
                return 2

    results: list[tuple[str, bool]] = []
    try:
        _, summary = run_tests()
        print(f"  {'baseline (contracts chosen from the master)':52} {summary}")
        print()
        print(f"  {'mutation':52} {'result':40}")
        print(f"  {'-' * 52} {'-' * 40}")

        for name, edits in MUTATIONS:
            mutated = original
            for old, new in edits:
                assert old in mutated, f"{name!r}: second edit no longer applies"
                mutated = mutated.replace(old, new, 1)
            TARGET.write_text(mutated)
            rc, summary = run_tests()
            caught = rc != 0
            results.append((name, caught))
            print(f"  {name:52} {(summary if caught else f'!! SURVIVED -- {summary}'):40}")
    finally:
        TARGET.write_text(original)
        assert TARGET.read_text() == original, "restore failed"

    print()
    expected = [n for n, caught in results if not caught and n.startswith("UNDETECTABLE")]
    unexpected = [n for n, caught in results if not caught and not n.startswith("UNDETECTABLE")]

    for n in expected:
        print(f"  1 expected survivor, by construction: {n}")

    if unexpected:
        print()
        print(f"  {len(unexpected)} UNEXPECTED mutation(s) survived -- real gaps:")
        for n in unexpected:
            print(f"    - {n}")
        return 1

    caught = len(results) - len(expected)
    print()
    print(f"  {caught}/{caught} detectable mutations caught by {TESTS}, "
          f"{len(expected)} undetectable by construction")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())