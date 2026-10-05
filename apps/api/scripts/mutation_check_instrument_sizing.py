"""Mutation harness for the lot-size and instrument-master defects.

Each mutation reintroduces one specific defect and asserts that at least one test
fails. A mutation that leaves the suite green proves the tests cannot see that
defect, which is worse than having no test: it reports coverage that does not
exist.

Run from apps/api:

    .venv/bin/python scripts/mutation_check_instrument_sizing.py

Exits non-zero if any mutation survives.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

API = Path(__file__).resolve().parents[1]

# The test files each mutation must break. Narrow on purpose: a mutation that only
# breaks an unrelated file proves less than one that breaks the owning suite.
SUITE = [
    "tests/test_dhan_instruments.py",
    "tests/test_lot_size_sourcing.py",
    "tests/test_lot_size_reference_isolation.py",
    "tests/test_live_execution_quantity.py",
    "tests/test_user_strategies.py",
]

MUTATIONS: list[tuple[str, str, str, str]] = [
    # (label, target file, original snippet, mutated snippet)
    (
        "1. reintroduce a LOT_SIZES table",
        "market/instruments.py",
        'REFERENCE_BROKER = "dhan"',
        'REFERENCE_BROKER = "dhan"\nLOT_SIZES = {"NIFTY": 65, "BANKNIFTY": 30}',
    ),
    (
        "2. reintroduce LOT_SIZES.get(symbol, 75)",
        "market/instrument_service.py",
        'return resolve_lot_size((index or "").split(":")[-1], instrument_type="")',
        'return resolve_lot_size((index or "").split(":")[-1], instrument_type="") or 75',
    ),
    (
        "3. reintroduce a defaulted 65 lookup in the compile path",
        "engine/strategy_compiler.py",
        "    lot_size = resolve_lot_size(symbol)\n\n    if not lot_size:",
        "    lot_size = resolve_lot_size(symbol) or 65  # MUTATION\n\n    if not lot_size:",
    ),
    (
        "4. reintroduce lot_size = 1",
        "strategies/base.py",
        "        if not self.lot_size:\n            return 0",
        "        if not self.lot_size:\n            return 1",
    ),
    (
        "5. prefer a stale cached lot size over a fresh resolution",
        "strategies/buyer_base.py",
        "self.lot_size = instrument_service.lot_size(self.bc.index) or cached_lot",
        "self.lot_size = cached_lot or instrument_service.lot_size(self.bc.index)",
    ),
    (
        "6. accept a boolean lot size",
        "market/dhan_instruments.py",
        "    if raw is None or isinstance(raw, bool):\n        raise DhanMasterValidationError",
        "    if raw is None:\n        pass\n    if False:\n        raise DhanMasterValidationError",
    ),
    (
        "7. accept a fractional lot size",
        "market/dhan_instruments.py",
        "    if value != int(value):\n        raise DhanMasterValidationError(f\"{where}: lot size {value} is fractional\")",
        "    if False:\n        raise DhanMasterValidationError(f\"{where}: lot size {value} is fractional\")",
    ),
    (
        "8. accept a missing security id",
        "market/dhan_instruments.py",
        '            if not security_id:\n                reject("missing_security_id")\n                continue',
        '            if not security_id:\n                security_id = "unknown"',
    ),
    (
        "9. accept a missing expiry on an option",
        "market/dhan_instruments.py",
        "                    if expiry is None:\n                        reject(\"option_missing_expiry\")\n                        continue",
        "                    if expiry is None:\n                        expiry = date.today()",
    ),
    (
        "10. accept a missing strike on an option",
        "market/dhan_instruments.py",
        "                    if strike is None:\n                        reject(\"option_missing_strike\")\n                        continue",
        "                    if strike is None:\n                        strike = 0.0",
    ),
    (
        "11. accept a missing option type",
        "market/dhan_instruments.py",
        "                if is_option and not option_type:\n                    reject(\"option_missing_option_type\")\n                    continue",
        "                if is_option and not option_type:\n                    option_type = \"CE\"",
    ),
    (
        "12. clear the dataset before downloading",
        "market/dhan_instruments.py",
        '        self.health.last_attempt = datetime.now(UTC).isoformat()\n        try:\n            text = await self.download()',
        '        self.health.last_attempt = datetime.now(UTC).isoformat()\n        self._dataset = None  # MUTATION: delete before download\n        try:\n            text = await self.download()',
    ),
    (
        "13. let the legacy symbol master answer instead of Dhan",
        "market/instruments.py",
        """    def resolve(
        self,
        symbol: str,
        *,
        broker: str,
        instrument_type: str,
    ) -> Instrument | None:""",
        """    def resolve(
        self,
        symbol: str,
        *,
        broker: str,
        instrument_type: str,
    ) -> Instrument | None:
        _legacy_lot = {"NSE:NIFTY50-INDEX": 999, "NSE:RELIANCE-EQ": 500}  # MUTATION
        _lot = _legacy_lot.get(symbol)
        if _lot:
            return Instrument(broker=broker, security_id="legacy", broker_symbol=symbol,
                              exchange_segment="NSE_EQ", instrument_type=instrument_type,
                              lot_size=_lot, source="legacy")""",
    ),
    (
        "14. return a fabricated contract when nothing resolves",
        "market/dhan_instruments.py",
        """        if text.isdigit():
            for contract in dataset.by_security_id.values():
                if contract.security_id == text:
                    return contract.to_instrument()
        return None""",
        """        if text.isdigit():
            for contract in dataset.by_security_id.values():
                if contract.security_id == text:
                    return contract.to_instrument()
        return Instrument(broker="dhan", security_id=text or "0",  # MUTATION
                          broker_symbol=text, exchange_segment="NSE_FNO",
                          instrument_type="OPT", lot_size=65, option_type="CE")""",
    ),
]


def run_suite() -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *SUITE, "-q", "--no-header", "-x", "--tb=no"],
        cwd=API, capture_output=True, text=True,
    )
    return proc.returncode == 0, proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""


def main() -> int:
    survivors = []
    print(f"  baseline: {' '.join(SUITE)}")
    ok, summary = run_suite()
    if not ok:
        print(f"  BASELINE IS RED: {summary}")
        return 2
    print(f"  baseline green ({summary})\n")

    for label, rel, original, mutated in MUTATIONS:
        target = API / rel
        text = target.read_text(encoding="utf-8")
        if original not in text:
            print(f"  SKIP  {label}\n          anchor not found in {rel} -- the mutation is untested")
            survivors.append(label)
            continue
        backup = tempfile.NamedTemporaryFile(delete=False, suffix=".py")
        backup.write(text.encode())
        backup.close()
        try:
            target.write_text(text.replace(original, mutated, 1), encoding="utf-8")
            ok, _ = run_suite()
            if ok:
                print(f"  SURVIVED  {label}  <-- no test caught this")
                survivors.append(label)
            else:
                print(f"  caught    {label}")
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