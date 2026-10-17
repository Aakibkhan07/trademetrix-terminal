"""Does the paper-restore test file catch the three things it names?

A green suite against a fix is evidence about nothing on its own. Each mutation below breaks
one fix in one specific way; the table is worth reading only if every row fails.

Two of these mutations are the ones that got this wrong before. A test asserting "two
concurrent restores double the position" passes with the serialisation deleted, because two
restores never doubled anything -- the replay loop has no suspension point. That is recorded
here as a mutation so the stale expectation cannot quietly return.

Note the third group is a guard on a multi-writer table rather than a measured defect: the real
`ExecutionManager.place_order` path produces one audit row per fill. Its mutation is here so
the guard stays load-bearing, not because the doubling was ever traced to it.

Read-only apart from a temporary edit to `paper/paper_broker.py`, restored in a `finally`.
Run from `apps/api`:

    .venv/bin/python scripts/mutation_restore_lock.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "paper" / "paper_broker.py"
TESTS = "tests/test_paper_position_double_restore.py"

RESET_BODY = (
    "        self._account = PaperAccount(\n"
    "            user_id=self.user_id,\n"
    "            initial_capital=self._config.initial_capital,\n"
    "            total_margin=self._config.initial_capital,\n"
    "            available_margin=self._config.initial_capital,\n"
    "            current_value=self._config.initial_capital,\n"
    "        )"
)
# The original defect, verbatim in shape: four fields reset in place, `used_margin` -- the one
# the restore adds to -- never touched.
RESET_IN_PLACE = (
    "        self._account.initial_capital = self._config.initial_capital\n"
    "        self._account.total_margin = self._config.initial_capital\n"
    "        self._account.available_margin = self._config.initial_capital\n"
    "        self._account.current_value = self._config.initial_capital"
)
RESET_CALL_IN_RESTORE = "            self._positions = {}\n            self._orders = {}\n            self._reset_account()"
PERSIST_CALL = "            self._persist_order(order, fill)\n\n        paper_metrics.record_fill()"
DEDUPE_CALL = "            rows = self._one_row_per_fill(rows)\n"
FILL_LOCK = "        async with self._positions_lock:\n            self._update_position(order, fill)"

# name -> (old, new)
MUTATIONS: list[tuple[str, str, str]] = [
    (
        "_reset_account mutates in place, leaving used_margin (the original bug)",
        RESET_BODY,
        RESET_IN_PLACE,
    ),
    (
        "the restore rebuilds positions but never resets the account",
        RESET_CALL_IN_RESTORE,
        "            self._positions = {}\n            self._orders = {}",
    ),
    (
        "fill drops the lock the rebuild holds",
        FILL_LOCK,
        "        if True:\n            self._update_position(order, fill)",
    ),
    (
        "audit write moves back outside the critical section",
        PERSIST_CALL,
        "        self._persist_order(order, fill)\n\n        paper_metrics.record_fill()",
    ),
    (
        "duplicate audit rows replay as separate fills",
        DEDUPE_CALL,
        "",
    ),
    (
        "dedupe keys on broker_order_id alone, erasing real partial fills",
        "            key = (\n"
        "                row.get(\"broker_order_id\", \"\"),\n"
        "                row.get(\"filled_quantity\", row.get(\"quantity\", 0)),\n"
        "                row.get(\"average_price\", 0.0),\n"
        "            )",
        "            key = (row.get(\"broker_order_id\", \"\"),)",
    ),
    (
        "restore and fill take different locks",
        FILL_LOCK,
        "        async with asyncio.Lock():\n            self._update_position(order, fill)",
    ),
]

# Mutations that target the file but not via a simple call-site rewrite: the two stale
# expectations that would otherwise be believed.
SOURCE_MUTATIONS: list[tuple[str, str, str]] = [
    (
        "restore stops taking the lock at all",
        "        async with self._positions_lock:\n            await self._restore_positions_locked()",
        "        await self._restore_positions_locked()",
    ),
]


def run_tests() -> tuple[int, str]:
    p = subprocess.run(
        [".venv/bin/python", "-m", "pytest", TESTS, "-q", "-W", "ignore::DeprecationWarning",
         "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True,
    )
    lines = [ln for ln in p.stdout.strip().splitlines() if ln.strip()]
    return p.returncode, (lines[-1] if lines else "(no output)")


def main() -> int:
    original = TARGET.read_text()
    all_mutations = MUTATIONS + SOURCE_MUTATIONS
    for name, old, _new in all_mutations:
        if old not in original:
            print(f"  !! mutation does not apply: {name!r} -- update the harness",
                  file=sys.stderr)
            return 2

    results: list[tuple[str, bool]] = []
    try:
        _, summary = run_tests()
        print(f"  {'baseline (all three fixes present)':52} {summary}")
        print()
        print(f"  {'mutation':52} {'result':52}")
        print(f"  {'-' * 52} {'-' * 52}")

        for name, old, new in all_mutations:
            TARGET.write_text(original.replace(old, new, 1))
            rc, summary = run_tests()
            caught = rc != 0
            results.append((name, caught))
            print(f"  {name:52} {(summary if caught else f'!! SURVIVED -- {summary}'):52}")
    finally:
        TARGET.write_text(original)
        assert TARGET.read_text() == original, "restore failed"

    print()
    survived = [n for n, caught in results if not caught]
    if survived:
        print(f"  {len(survived)}/{len(results)} mutations SURVIVED -- the suite misses them:")
        for n in survived:
            print(f"    - {n}")
        return 1
    print(f"  {len(results)}/{len(results)} mutations caught by {TESTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())