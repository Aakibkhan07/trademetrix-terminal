"""Does the token-expiry test catch the production bug, or just describe it?

The bug is one line of behaviour: a stored `"valid"` was returned without ever looking at
`token_expires_at`. Each mutation below reintroduces it in the shape it actually took, plus the
neighbouring mistakes a "fix the status" change invites.

The last three exist because a derived status can be wrong in ways an echoed one cannot: it can
claim a token is fine when the date is unreadable, it can promote a flagged credential because
its expiry is in the future, and it can promote a revoked one for the same reason. A test suite
that only covers the headline case would pass all three.

Read-only apart from a temporary edit to `engine/token_refresh.py`, restored in a `finally`.

Run from `apps/api`:

    .venv/bin/python scripts/mutation_token_expiry.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "engine" / "token_refresh.py"
TESTS = "tests/test_token_expiry_status.py"

DERIVE = "    status, expired = effective_token_status(r)"
ECHO = '    status, expired = (r.get("token_status", "unknown") or "unknown"), False'
NAIVE_CHECK = "            expires_at = expires_at.replace(tzinfo=UTC)"
SEVERE = '    if stored in ("revoked", "unknown"):\n        return stored, expired'
MISSING_EXP = "    else:\n        expired = False"
RETURN_BOOL = '        return "needs_attention", True'
BOUNDARY = "        expired = expires_at <= datetime.now(UTC)"

# The second consumer. Fixing only `get_token_status` leaves the badge on the `/brokers` page
# still saying "valid" -- the same lie through a different door -- so this one is load-bearing
# for the fix to be complete rather than half-applied.
LIST_DERIVE = "            status, expired = effective_token_status(row)"
LIST_ECHO = '            status, expired = row.get("token_status", "unknown"), False'

MUTATIONS: list[tuple[str, str, str]] = [
    (
        "the original bug: the stored column is echoed",
        DERIVE,
        ECHO,
    ),
    (
        "naive datetimes are compared without pinning UTC (raises)",
        NAIVE_CHECK,
        "            pass",
    ),
    (
        "a flagged credential is upgraded because its expiry is future",
        SEVERE,
        "    if stored == \"unknown\":\n        return stored, expired",
    ),
    (
        "a missing or unreadable expiry is treated as expired",
        MISSING_EXP,
        "    else:\n        expired = True",
    ),
    (
        "an expired token still reports valid",
        RETURN_BOOL,
        '        return "valid", False',
    ),
    (
        "the boundary allows a token to outlive its expiry",
        BOUNDARY,
        "        expired = expires_at < datetime.now(UTC) - timedelta(days=1)",
    ),
]

#: The listing lives in a different file, so it is a second target rather than a second edit.
OTHER_TARGET = ROOT / "infrastructure" / "repositories" / "broker_repository.py"
OTHER_MUTATIONS: list[tuple[Path, str, str, str]] = [
    (
        OTHER_TARGET,
        "the /brokers listing echoes the stored status again",
        LIST_DERIVE,
        LIST_ECHO,
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
    originals = {OTHER_TARGET: OTHER_TARGET.read_text()}
    for name, old, _new in MUTATIONS:
        if old not in original:
            print(f"  !! mutation does not apply: {name!r} -- update the harness",
                  file=sys.stderr)
            return 2
    for _path, name, old, _new in OTHER_MUTATIONS:
        if old not in originals[_path]:
            print(f"  !! mutation does not apply: {name!r} -- update the harness",
                  file=sys.stderr)
            return 2

    results: list[tuple[str, bool]] = []
    try:
        _, summary = run_tests()
        print(f"  {'baseline (status derived from expiry)':52} {summary}")
        print()
        print(f"  {'mutation':52} {'result':40}")
        print(f"  {'-' * 52} {'-' * 40}")

        for name, old, new in MUTATIONS:
            TARGET.write_text(original.replace(old, new, 1))
            rc, summary = run_tests()
            caught = rc != 0
            results.append((name, caught))
            print(f"  {name:52} {(summary if caught else f'!! SURVIVED -- {summary}'):40}")

        for path, name, old, new in OTHER_MUTATIONS:
            TARGET.write_text(original)
            path.write_text(originals[path].replace(old, new, 1))
            rc, summary = run_tests()
            caught = rc != 0
            results.append((name, caught))
            print(f"  {name:52} {(summary if caught else f'!! SURVIVED -- {summary}'):40}")
    finally:
        TARGET.write_text(original)
        assert TARGET.read_text() == original, "restore failed"
        for path, text in originals.items():
            path.write_text(text)
            assert path.read_text() == text, f"restore failed for {path}"

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