"""The ten mutations the retry/reconciliation safety must refuse.

Each one reintroduces a specific defect. A mutation that SURVIVES means a guard cannot see
that class of failure, and the number is not a proof of safety.

A baseline failure invalidates the whole run, so it is asserted first.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

MANAGER = Path("oms/manager.py")
RECON = Path("oms/reconciliation.py")
RULES = Path("risk/rules.py")
RETRY = Path("execution/retry.py")
EXECMGR = Path("execution/manager.py")
TESTS = "tests/test_oms_reconciliation.py"

MUTATIONS = [
    (
        "M1 a retry mints a NEW client order identity",
        MANAGER,
        "        execution_request_id=order.execution_request_id,\n",
        "        execution_request_id=None,\n",
    ),
    (
        "M2 skip reconciliation before retry (retry the UNKNOWN result directly)",
        MANAGER,
        """                if exec_result.indeterminate:""",
        """                if False:""",
    ),
    (
        "M3 retry an UNKNOWN broker state immediately",
        MANAGER,
        """        if outcome.verdict is ReconcileVerdict.UNKNOWN:""",
        """        if outcome.verdict is ReconcileVerdict.NOT_FOUND:""",
    ),
    (
        "M4 treat a broker timeout as a definitive rejection",
        EXECMGR,
        """        except IndeterminateOrderError as e:""",
        """        except IndeterminateOrderError as e:  # noqa
            return OrderResult(success=False, message=str(e))
        except ZeroDivisionError as e:""",
    ),
    (
        "M5 disable DuplicateOrderRule completely",
        RULES,
        """            if dedup_key in recent:""",
        """            if False:""",
    ),
    (
        "M6 allow a changed quantity during recovery (fingerprint ignores it)",
        Path("oms/identity.py"),
        '    "user_id", "broker", "symbol", "side", "quantity", "order_type", "product",\n',
        '    "user_id", "broker", "symbol", "side", "order_type", "product",\n',
    ),
    (
        "M7 allow a changed SecurityId during recovery (fingerprint ignores it)",
        Path("oms/identity.py"),
        '    "instrument_type", "expiry_date", "strike_price", "option_type",\n',
        "",
    ),
    (
        "M8 allow a changed transaction side during recovery (fingerprint ignores it)",
        Path("oms/identity.py"),
        '    "user_id", "broker", "symbol", "side", "quantity", "order_type", "product",\n',
        '    "user_id", "broker", "symbol", "quantity", "order_type", "product",\n',
    ),
    (
        "M9 collapse AMBIGUOUS into ACCEPTED",
        RECON,
        """            return ReconcileOutcome(
                verdict=ReconcileVerdict.AMBIGUOUS, candidates=tuple(matches),
                reason=f"correlation id matched {len(matches)} broker orders",
            )""",
        """            return ReconcileOutcome(
                verdict=ReconcileVerdict.ACCEPTED, candidates=tuple(matches),
                match=matches[0],
                reason=f"correlation id matched {len(matches)} broker orders",
            )""",
    ),
    (
        "M10 collapse AMBIGUOUS into NOT_FOUND",
        RECON,
        """            return ReconcileOutcome(
                verdict=ReconcileVerdict.AMBIGUOUS, candidates=tuple(candidates),
                reason=(f"{len(candidates)} broker orders match this contract identity; "
                        f"refusing to choose one"),
            )""",
        """            return ReconcileOutcome(
                verdict=ReconcileVerdict.NOT_FOUND, candidates=tuple(candidates),
                retry_eligible=True,
                reason=(f"{len(candidates)} broker orders match; treated as absent"),
            )""",
    ),
    (
        "M11 treat a broker *failure* as absence",
        RECON,
        """        if self._is_failure(why):
            return ReconcileOutcome(
                verdict=ReconcileVerdict.UNKNOWN, reason=why,
            )
""",
        "",
    ),
    (
        "M12 retry a timeout at the transport layer",
        RETRY,
        """            if is_indeterminate(e):""",
        """            if False:""",
    ),
]


def run_suite() -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", TESTS, "-q", "--no-header",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-700:]


def main() -> int:
    print("  ── baseline: unmutated suite must be green ──")
    ok, out = run_suite()
    print(f"     {'PASS' if ok else 'FAIL'}  baseline green")
    if not ok:
        print(out)
        return 1

    print("\n  ── each mutation must be caught ──")
    survivors = []
    for label, path, old, new in MUTATIONS:
        original = path.read_text()
        if old not in original:
            print(f"     SKIP    {label}  (anchor not found)")
            survivors.append(label)
            continue
        with tempfile.NamedTemporaryFile("w", delete=False) as fh:
            fh.write(original)
            backup = Path(fh.name)
        try:
            path.write_text(original.replace(old, new, 1))
            ok, _ = run_suite()
            print(f"     {'caught' if not ok else 'SURVIVED'}  {label}")
            if ok:
                survivors.append(label)
        finally:
            path.write_text(original)
            backup.unlink(missing_ok=True)

    restored, _ = run_suite()
    print(f"\n  ── sources restored, suite green again: {restored} ──")
    if survivors:
        print(f"\n  {len(survivors)} mutation(s) SURVIVED -- the guards cannot see them:")
        for s in survivors:
            print(f"    - {s}")
        return 1
    print(f"\n  all {len(MUTATIONS)} mutations caught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
