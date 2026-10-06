"""Mutation check for the single-Dhan-websocket-implementation regression tests.

Each mutation reintroduces one specific defect from the duplicate implementation and
asserts that at least one test in `test_dhan_feed_single_implementation.py` fails.

A mutation that survives means the guard cannot see that defect. Running the suite green
against the real code is not evidence on its own -- this is.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ADAPTER = Path("brokers/dhan_adapter.py")
DATA_SOCKET = Path("market/data_socket.py")
TESTS = "tests/test_dhan_feed_single_implementation.py"

# (id, file, the old text to restore, the new text that reintroduces the defect)
MUTATIONS = [
    (
        "M1 use httpx client.stream() for the socket",
        ADAPTER,
        "from market.dhan_feed import DhanMarketFeed, FeedMode, subscription_for_instrument",
        "import httpx\n        from market.dhan_feed import DhanMarketFeed, FeedMode, subscription_for_instrument\n"
        "        await httpx.AsyncClient().stream('GET', self._ws_url)",
    ),
    (
        "M2 subscribe with RequestCode 1",
        ADAPTER,
        "        feed = DhanMarketFeed(self._access_token, self._client_id, on_event=_emit)",
        "        subscribe_payload = {'RequestCode': 1, 'SymbolList': symbols}\n"
        "        feed = DhanMarketFeed(self._access_token, self._client_id, on_event=_emit)",
    ),
    (
        "M3 send SecurityToken instead of SecurityId",
        ADAPTER,
        "        feed = DhanMarketFeed(self._access_token, self._client_id, on_event=_emit)",
        "        feed = DhanMarketFeed(self._access_token, self._client_id, on_event=_emit)\n"
        "        self._sent = {'SecurityToken': symbols}",
    ),
    (
        "M4 default the exchange segment to NSE_EQ",
        ADAPTER,
        "            if instrument is None or not instrument.security_id:\n"
        "                refused.append(symbol)\n"
        "                continue",
        "            if instrument is None or not instrument.security_id:\n"
        "                refused.append(symbol)\n"
        "                continue\n"
        "            instrument = instrument.__class__(\n"
        "                broker='dhan', broker_symbol=symbol, underlying='X',\n"
        "                instrument_type='EQ', exchange_segment='NSE_EQ',\n"
        "                security_id=symbol, lot_size=1)",
    ),
    (
        "M5 subscribe the display symbol as the security id",
        ADAPTER,
        "            sub = subscription_for_instrument(instrument, mode=FeedMode.QUOTE)",
        "            sub = subscription_for_instrument(instrument, mode=FeedMode.QUOTE)\n"
        "            sub.security_id = symbol",
    ),
    (
        "M6 restore the wrong feed host as a live url",
        ADAPTER,
        '        self._base_url = "https://api.dhan.co/v2"',
        '        self._base_url = "https://api.dhan.co/v2"\n'
        '        self._ws_url = "wss://api.dhan.co/v2/ws"',
    ),
    (
        "M7 drop the Dhan token column fallback in data_socket",
        DATA_SOCKET,
        '                if broker_type == "dhan" and not raw_token and secret_key:\n'
        "                    raw_token = secret_key",
        "                pass",
    ),
]


def run_suite() -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", TESTS, "-q", "--no-header", "-p", "no:cacheprovider"],
        capture_output=True, text=True,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-900:]


def main() -> int:
    print("  ── baseline: the unmutated suite must be green ──")
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
            print(f"     SKIP  {label}: anchor text not found (test file moved?)")
            survivors.append(label)
            continue
        with tempfile.NamedTemporaryFile("w", suffix=f".{path.name}.bak", delete=False) as fh:
            fh.write(original)
            backup = Path(fh.name)
        try:
            path.write_text(original.replace(old, new, 1))
            ok, out = run_suite()
            caught = not ok
            print(f"     {'caught' if caught else 'SURVIVED'}  {label}")
            if not caught:
                survivors.append(label)
                for line in out.splitlines():
                    if "passed" in line:
                        print(f"              {line.strip()}")
        finally:
            path.write_text(original)
            backup.unlink(missing_ok=True)

    restored_ok, _ = run_suite()
    print(f"\n  ── source restored, suite green again: {restored_ok} ──")
    if survivors:
        print(f"\n  {len(survivors)} mutation(s) SURVIVED -- the guard cannot see them:")
        for s in survivors:
            print(f"    - {s}")
        return 1
    print(f"\n  all {len(MUTATIONS)} mutations caught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
