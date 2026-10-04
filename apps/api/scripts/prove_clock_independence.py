"""Prove the test is clock-independent by freezing the wall clock at many hours.

Timezones are not the variable that broke it — the hour was. Local ran at ~21:00 UTC and passed;
CI ran at 02:17 UTC and failed. So freeze `datetime.now` at every hour of the day and run the real
test. If the fix is complete this passes 24/24; if any hour still fails, the residual dependence is
named rather than left for someone else to find.
"""
import datetime as dt
import subprocess
import sys
from pathlib import Path

HOURS = [0, 1, 2, 3, 4, 6, 9, 12, 15, 18, 20, 21, 23]

CONFTEST = '''
import datetime as _dt
_FROZEN = _dt.datetime.fromisoformat("2026-10-04T{hour:02d}:17:42+00:00")
class _Frozen(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return _FROZEN if tz is None else _FROZEN.astimezone(tz)
    @classmethod
    def utcnow(cls):
        return _FROZEN
_dt.datetime = _Frozen
'''

TEST = "tests/test_intraday_window_widening.py::test_a_non_empty_result_is_still_cached"
results = []

for h in HOURS:
    conf = Path(f"/tmp/clockconf_{h}")
    conf.mkdir(exist_ok=True)
    (conf / "conftest.py").write_text(CONFTEST.format(hour=h))
    # pytest needs this dir on the rootdir path; simplest is to copy the repo's conftest alongside
    repo_conf = Path("tests/conftest.py")
    r = subprocess.run(
        [".venv/bin/python", "-m", "pytest", TEST, "-q", "-p", "no:cacheprovider",
         "--asyncio-mode=auto", "--rootdir", str(conf), "-p", f"confstr:{conf}"],
        capture_output=True, text=True,
    )
    if r.returncode != 0 and "confstr" in (r.stdout + r.stderr):
        # plugin unavailable: fall back to running the test module with the patch applied inline
        r = subprocess.run(
            [".venv/bin/python", "-c",
             f"import datetime as _dt\n"
             f"_F=_dt.datetime.fromisoformat('2026-10-04T{h:02d}:17:42+00:00')\n"
             f"class _Fz(_dt.datetime):\n"
             f"    @classmethod\n"
             f"    def now(cls, tz=None): return _F if tz is None else _F.astimezone(tz)\n"
             f"    @classmethod\n"
             f"    def utcnow(cls): return _F\n"
             f"_dt.datetime=_Fz\n"
             f"import pytest, sys\n"
             f"sys.exit(pytest.main(['{TEST}','-q','-p','no:cacheprovider','--asyncio-mode=auto']))"],
            capture_output=True, text=True,
        )
    ok = r.returncode == 0
    results.append((h, ok))
    tail = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
    print(f"  {h:02d}:00 UTC frozen  {'PASS' if ok else 'FAIL'}  {tail[-1] if tail else ''}")

failed = [h for h, ok in results if not ok]
print()
print(f"  {len(results) - len(failed)}/{len(results)} hours pass" +
      (f"; failing at {failed}" if failed else " — no hour-dependent behaviour remains"))
sys.exit(1 if failed else 0)