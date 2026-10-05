"""Mutation harness for the Dhan Live Market Feed defects.

Each mutation reintroduces one historical defect and asserts at least one test fails.
A surviving mutation means the tests cannot see that defect, which is worse than no
test at all -- it reports coverage that does not exist.

Two of these mutations in an earlier draft were inert rather than caught, which is why
the harness distinguishes SURVIVED from caught and why SKIP is treated as a failure:

* one anchored on a code path that was never taken, so the defect did not occur
* one mutated a name that no longer existed, so nothing changed

Run from apps/api:

    .venv/bin/python scripts/mutation_check_dhan_feed.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

API = Path(__file__).resolve().parents[1]
SUITE = ["tests/test_dhan_feed.py"]

TARGET = "market/dhan_feed.py"

MUTATIONS: list[tuple[str, str, str]] = [
    # 1. The original cause: httpx cannot perform a WebSocket protocol upgrade.
    (
        "F1. use httpx streaming instead of a real WebSocket client",
        "        import websockets\n\n        return await websockets.connect(",
        "        import httpx\n\n        return await httpx.AsyncClient().stream(",
    ),
    # 2. A derivative feed defaulting to cash equity.
    (
        "F2. default a derivative subscription segment to NSE_EQ",
        "        exchange_segment=segment,",
        '        exchange_segment="NSE_EQ",  # MUTATION',
    ),
    # 3. A display/trading symbol sent where Dhan wants a security id.
    (
        "F3. send the trading symbol instead of the security id",
        "        security_id=str(instrument.security_id),",
        "        security_id=str(instrument.broker_symbol),  # MUTATION",
    ),
    # 4. Identity collapsed to the security id alone.
    (
        "F4. key the quote cache on security id alone",
        "        return self._quotes.get((exchange_segment, str(security_id)))",
        "        for key, value in self._quotes.items():\n"
        "            if key[1] == str(security_id):\n"
        "                return value\n"
        "        return None  # MUTATION",
    ),
    # 5. Reconnect that silently forgets the subscription set.
    (
        "F5. do not resubscribe after a reconnect",
        "        self.acknowledged = {sub.identity for sub in self._subscriptions.values()}",
        "        pass  # MUTATION",
    ),
    # 6. Staleness ignored, so execution could use an old price.
    (
        "F6. treat a stale quote as fresh",
        "        if event is None or event.age_seconds > max_age:\n            return None",
        "        if event is None:\n            return None  # MUTATION",
    ),
    # 7. One subscription lost on reconnect.
    (
        "F7. drop one subscription during reconnect",
        "        frames = build_subscribe_frame(self._subscriptions.values())",
        "        _dropped = list(self._subscriptions.values())[:-1]  # MUTATION\n"
        "        frames = build_subscribe_frame(_dropped)",
    ),
    # 8. Fabricated zeros for fields Dhan never sent.
    (
        "F8. fabricate zero for fields Dhan did not send",
        '        packet_type="ticker", timestamp=_epoch_to_datetime(ltt), ltp=float(ltp),\n    )',
        '        packet_type="ticker", timestamp=_epoch_to_datetime(ltt), ltp=float(ltp),\n'
        "        volume=0, open_interest=0, bid=0.0, ask=0.0,  # MUTATION\n    )",
    ),
]


def run_suite() -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *SUITE, "-q", "--no-header", "--tb=no"],
        cwd=API, capture_output=True, text=True,
    )
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    return proc.returncode == 0, tail


def main() -> int:
    print(f"  baseline: {' '.join(SUITE)}")
    ok, summary = run_suite()
    if not ok:
        print(f"  BASELINE IS RED: {summary}")
        return 2
    print(f"  baseline green ({summary})\n")

    target = API / TARGET
    survivors: list[str] = []
    for label, original, mutated in MUTATIONS:
        text = target.read_text(encoding="utf-8")
        if original not in text:
            print(f"  SKIP     {label}\n          anchor not found -- untested, not passing")
            survivors.append(label)
            continue
        backup = tempfile.NamedTemporaryFile(delete=False, suffix=".py")
        backup.write(text.encode())
        backup.close()
        try:
            target.write_text(text.replace(original, mutated, 1), encoding="utf-8")
            passed, _ = run_suite()
            if passed:
                print(f"  SURVIVED {label}  <-- no test caught this")
                survivors.append(label)
            else:
                print(f"  caught   {label}")
        finally:
            shutil.copyfile(backup.name, target)
            Path(backup.name).unlink(missing_ok=True)

    print()
    if survivors:
        print(f"  {len(survivors)} of {len(MUTATIONS)} mutations survived: {survivors}")
        return 1
    print(f"  all {len(MUTATIONS)} mutations caught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())