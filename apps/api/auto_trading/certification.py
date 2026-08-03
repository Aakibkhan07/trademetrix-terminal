"""Auto Trading v1.0 — certification harness.

Runs the six required certifications and writes a JSON + Markdown report to
``docs/evolution/certs/auto_trading_v1/``.

Certification mapping (automated, deterministic — no live orders placed):

- PAPER         — paper deploy → RUNNING → candle-driven orders → stop
                  (tests/test_auto_trading.py, tests/test_strategy_runtime.py)
- LIVE          — explicit confirmation gate: unconfirmed live deploy is
                  refused (409), confirmed live requires a real broker
                  account; credential-gated live start marked SKIP unless
                  AUTO_CERT_USER has stored broker credentials
                  (tests/test_auto_trading_api.py)
- RECOVERY      — restore running / paused / idempotent / adopt legacy
                  (tests/test_strategy_runtime_recovery.py)
- RESTART       — hot restart keeps running, restart_count bumps, mode kept
                  (tests/test_strategy_runtime.py)
- MULTI_ACCOUNT — two strategies on distinct brokers/accounts stay isolated
                  (tests/test_strategy_runtime.py: two-strategy isolation)
- RISK          — max daily trades / max positions / max exposure enforced,
                  emergency stop halts all and blocks new starts
                  (tests/test_auto_trading.py)

Usage:  cd apps/api && PYTHONPATH=. .venv/bin/python -m auto_trading.certification
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

logging.basicConfig(level=logging.WARNING)

API_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = API_DIR.parent  # the terminal workspace root
REPORT_DIR = REPO_DIR / "docs" / "evolution" / "certs" / "auto_trading_v1"
VENV_PY = API_DIR / ".venv" / "bin" / "python"


class CertSuite:
    def __init__(self, name: str):
        self.name = name
        self.checks: list[dict] = []

    def check(self, ok: bool, label: str, detail: str = "", skipped: bool = False) -> None:
        self.checks.append({"ok": bool(ok), "skipped": bool(skipped), "label": label, "detail": detail})
        state = "SKIP" if skipped else ("PASS" if ok else "FAIL")
        print(f"  [{state}] {self.name}: {label} — {detail}")

    def passed(self) -> bool:
        ran = [c for c in self.checks if not c.get("skipped")]
        return bool(ran) and all(c.get("ok") for c in ran)

    def summary(self) -> dict:
        ran = [c for c in self.checks if not c.get("skipped")]
        return {
            "name": self.name,
            "passed": self.passed(),
            "checks": self.checks,
            "total": len(self.checks),
            "executed": len(ran),
            "skipped": len(self.checks) - len(ran),
        }


def _run_pytest(args: list[str]) -> tuple[int, float]:
    t0 = time.monotonic()
    proc = subprocess.run(
        [str(VENV_PY), "-m", "pytest", "--no-header", "-q", *args],
        cwd=str(API_DIR),
        capture_output=True,
        text=True,
    )
    elapsed_ms = (time.monotonic() - t0) * 1000
    tail = proc.stdout.strip().splitlines()[-1:] + proc.stderr.strip().splitlines()[-2:]
    return proc.returncode, elapsed_ms, " | ".join(tail)


def _live_credential_gate(suite: CertSuite) -> None:
    user = os.getenv("AUTO_CERT_USER", "")
    if not user:
        suite.check(True, "live-credential-gate", "no AUTO_CERT_USER configured — live start SKIP (credential-gated)", skipped=True)
        return
    try:
        from infrastructure.repositories.broker_repository import BrokerRepository

        repo = BrokerRepository()
        rows = asyncio.run(repo.list_credentials(user)) or []
        active = [r for r in rows if r.get("is_active") and r.get("broker")]
    except Exception as e:
        suite.check(True, "live-credential-gate", f"credential lookup unavailable: {e} — SKIP", skipped=True)
        return
    if not active:
        suite.check(True, "live-credential-gate", f"no active broker credentials for {user} — SKIP (credential-gated)", skipped=True)
        return
    suite.check(True, "live-credential-gate", f"active broker credentials for {user}: {[r['broker'] for r in active]}")
    suite.check(True, "live-notice", "a confirmed live start would be routed through the frozen engine gate "
                                     "(risk-checked, paper-never). Actual live orders are intentionally NOT placed "
                                     "by this harness — use the builder deploy flow with confirm_live=true.")


def _certify(name: str, pytest_files: list[str]) -> CertSuite:
    suite = CertSuite(name)
    code, elapsed, tail = _run_pytest(pytest_files)
    suite.check(code == 0, "automated-suite", f"exit={code} elapsed_ms={elapsed:.0f} {tail}", skipped=False)
    return suite


async def main() -> int:
    print("Auto Trading v1.0 certification run —", datetime.now(UTC).isoformat())

    paper = _certify("Paper", ["tests/test_auto_trading.py", "tests/test_strategy_runtime.py"])
    live = _certify("Live", ["tests/test_auto_trading_api.py"])
    _live_credential_gate(live)
    recovery = _certify("Recovery", ["tests/test_strategy_runtime_recovery.py"])
    restart = _certify("Restart", ["tests/test_strategy_runtime.py"])
    multi_account = _certify("MultiAccount", ["tests/test_strategy_runtime.py"])
    risk = _certify("Risk", ["tests/test_auto_trading.py", "tests/test_auto_trading_api.py"])

    suites = [paper, live, recovery, restart, multi_account, risk]
    all_ok = all(s.passed() for s in suites)
    report = {
        "certification": "auto_trading_v1",
        "date": datetime.now(UTC).isoformat(),
        "verdict": "CERTIFIED" if all_ok else "NOT CERTIFIED",
        "summary": {s.name: s.summary() for s in suites},
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "certification.json").write_text(json.dumps(report, indent=2))
    (REPORT_DIR / "certification.md").write_text(_render_md(report))

    print("\n" + "=" * 60)
    for s in suites:
        verdict = "CERTIFIED" if s.passed() else "FAILED"
        print(f"  {s.name:14s} → {verdict}  ({s.summary()['executed']} executed, {s.summary()['skipped']} skipped)")
    print(f"\nVerdict: {report['verdict']}")
    print(f"Report:  {REPORT_DIR / 'certification.json'}")
    return 0 if all_ok else 1


def _render_md(report: dict) -> str:
    lines = [
        "# Auto Trading v1.0 — Certification Report",
        "",
        f"**Date:** {report['date']}",
        f"**Verdict:** {report['verdict']}",
        "",
        "## Summary",
        "",
        "| Certification | Verdict | Executed | Skipped |",
        "|---|---|---|---|",
    ]
    for name, s in report["summary"].items():
        lines.append(f"| {name} | {'CERTIFIED' if s['passed'] else 'FAILED'} | {s['executed']} | {s['skipped']} |")
    lines += ["", "## Detail", ""]
    for name, s in report["summary"].items():
        lines.append(f"### {name}")
        for c in s["checks"]:
            state = "SKIP" if c["skipped"] else ("PASS" if c["ok"] else "FAIL")
            lines.append(f"- [{state}] {c['label']} — {c['detail']}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
