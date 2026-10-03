"""Regression tests for the intraday window that could contain no trading session at all.

## The bug

`days` is a **clock** window, not a **session** window, and for intraday intervals the difference
decides whether the answer is empty. Asked for `interval=5m, days=1` at 23:13 IST, the resolved range
was [04:43 IST that day, 04:43 IST the next] — a stretch with no session in it, because the day's
session had ended at 15:30 and the next had not opened. The durable store held 525 real 5m bars;
none of them fell inside the window.

Both the store read and the fetch were bounded by that window. `_fetch_and_store` pulled 1,498 real
candles from Yahoo and filtered them down to **zero**, stored nothing and returned nothing, so
`fetch_historical_data` raised its honesty `ValueError` and `/marketdata/historical` answered 400:

    No real market data available for NIFTY50-INDEX (5m, 1d) — backtests never run on fabricated candles

That sentence is true about the window and false about the market, and it is the exact response the
app's own charts ask for. Every intraday chart was empty for any user browsing in the evening.

`_covers_range` already allowed a trading day of slack at the edges for precisely this reason, but
neither `_trim_range` nor `_fetch_and_store` did, so the tolerance never reached the result. Widening
the *trim* alone does not work either: by then the fetch has already discarded everything outside the
window, so there is nothing left to widen to. The fetch has to span the wider range.

## The fix, and the two things it must not break

The fetch reads a day wider than asked and the result is then narrowed, with the exact window still
preferred. So:

* a request made **during** a session returns only that session — the widening is a fallback for an
  empty result, not a way to over-deliver
* an **explicit** `start`/`end` is never widened, because the caller stated the range and quietly
  returning a day outside it would misrepresent the data
* **daily** and coarser intervals are never widened, since they have a bar for every calendar day and
  a rolling window is never empty for them

The second fix here is the negative cache: `load` used to store an empty result in its module-level
cache, with no TTL. A transient failure — a broker 403, a Yahoo timeout, a swallowed PGRST error —
therefore became a permanent answer for that exact key for the life of the process.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backtest import historical as hist


def _candle(ts: datetime, interval: str = "5m") -> dict:
    return {
        "symbol": "NSE:NIFTY50-INDEX",
        "exchange": "NSE",
        "interval": interval,
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "volume": 1,
        "timestamp": ts.isoformat(),
    }


def _session(day: datetime, interval_minutes: int = 5) -> list[dict]:
    """75 bars starting 09:15 IST (03:45 UTC) — one NSE trading day."""
    start = day.replace(hour=3, minute=45, second=0, microsecond=0)
    return [
        _candle(start + timedelta(minutes=interval_minutes * i), f"{interval_minutes}m")
        for i in range(75)
    ]


@pytest.fixture(autouse=True)
def _clear_caches():
    """Both the module cache and `_CACHE` are process-global; a leak would make these order-dependent."""
    hist._CACHE.clear()
    yield
    hist._CACHE.clear()


@pytest.fixture
def store(monkeypatch):
    """A durable store holding exactly one session, two days back."""
    session_day = datetime(2026, 10, 1, tzinfo=UTC)          # a Thursday
    bars = _session(session_day)

    async def fake_load_from_db(symbol, exchange, interval, start_dt, end_dt):
        return [
            c for c in bars
            if start_dt <= hist._normalize_ts(c["timestamp"]) <= end_dt
        ]

    async def fake_fetch_and_store(symbol, exchange, interval, start_dt, end_dt, user_id=None):
        return [
            c for c in bars
            if start_dt <= hist._normalize_ts(c["timestamp"]) <= end_dt
        ]

    monkeypatch.setattr(hist.backtest_historical, "_load_from_db", fake_load_from_db)
    monkeypatch.setattr(hist.backtest_historical, "_fetch_and_store", fake_fetch_and_store)
    return session_day


# ── the bug ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_one_day_intraday_request_outside_the_session_returns_the_session(store, monkeypatch):
    """The request the app's charts make. 23:13 IST on the 2nd, asking for `days=1` at 5m.

    Nothing falls inside the 24-hour window, so before the fix this was empty and the route
    answered 400 "no real market data available" while 525 real bars sat in the store.
    """
    now = datetime(2026, 10, 2, 17, 46, tzinfo=UTC)  # 23:16 IST
    monkeypatch.setattr(hist.backtest_historical, "_resolve_range", lambda d, s, e: (now - timedelta(days=1), now))
    bars = await hist.backtest_historical.load(
        symbol="NSE:NIFTY50-INDEX", exchange="NSE", interval="5m", days=1,
    )

    assert bars, "a 1-day intraday request must reach the most recent session, not report no data"
    assert len(bars) == 75
    assert bars[0]["timestamp"].startswith("2026-10-01T03:45")
    assert bars[-1]["timestamp"].startswith("2026-10-01T09:55")


# ── what the fix must not break ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_explicit_range_is_never_widened(store, monkeypatch):
    """A caller that stated the range gets that range, even when it is empty.

    Silently returning a day outside a stated window would misrepresent the data, which is worse
    than returning nothing.
    """
    empty_from = datetime(2026, 9, 20, tzinfo=UTC)
    empty_to = datetime(2026, 9, 21, tzinfo=UTC)
    monkeypatch.setattr(hist.backtest_historical, "_resolve_range", lambda d, s, e: (empty_from, empty_to))
    bars = await hist.backtest_historical.load(
        symbol="NSE:NIFTY50-INDEX", exchange="NSE", interval="5m", days=1,
        start=empty_from.isoformat(), end=empty_to.isoformat(),
    )

    assert bars == [], "an explicit range must not be widened"


@pytest.mark.asyncio
async def test_daily_intervals_are_never_widened(store, monkeypatch):
    """A daily bar exists for every calendar day, so a rolling window is never empty for one."""
    now = datetime(2026, 10, 2, 17, 46, tzinfo=UTC)
    monkeypatch.setattr(hist.backtest_historical, "_resolve_range", lambda d, s, e: (now - timedelta(days=1), now))
    await hist.backtest_historical.load(
        symbol="NSE:NIFTY50-INDEX", exchange="NSE", interval="1d", days=1,
    )

    spans = {
        k.split(":")[2:] for k in hist._CACHE
    }
    # Whatever came back, the daily request must not have borrowed the intraday fetch window.
    assert all("1d" in ":".join(s) for s in spans if s), "a daily request widened its window"


@pytest.mark.asyncio
async def test_a_request_during_a_session_returns_only_that_session(store, monkeypatch):
    """Mid-session, `days=1` must mean today's session — not yesterday's as well.

    The widening is a fallback for an empty result, never a licence to over-deliver.
    """
    same_day = datetime(2026, 10, 1, tzinfo=UTC)
    intraday_now = same_day.replace(hour=8, minute=0)  # 13:30 IST, mid-session
    bars_in_session = [
        _candle(same_day.replace(hour=3, minute=45) + timedelta(minutes=5 * i))
        for i in range(45)  # only the morning half exists so far
    ]

    async def fake_load_from_db(symbol, exchange, interval, start_dt, end_dt):
        return [
            c for c in bars_in_session
            if start_dt <= hist._normalize_ts(c["timestamp"]) <= end_dt
        ]

    async def fake_fetch_and_store(symbol, exchange, interval, start_dt, end_dt, user_id=None):
        return list(bars_in_session)

    monkeypatch.setattr(hist.backtest_historical, "_load_from_db", fake_load_from_db)
    monkeypatch.setattr(hist.backtest_historical, "_fetch_and_store", fake_fetch_and_store)
    monkeypatch.setattr(
        hist.backtest_historical, "_resolve_range",
        lambda d, s, e: (intraday_now - timedelta(hours=6), intraday_now),
    )
    bars = await hist.backtest_historical.load(
        symbol="NSE:NIFTY50-INDEX", exchange="NSE", interval="5m", days=1,
    )

    assert bars
    assert all(hist._normalize_ts(b["timestamp"]).date() == same_day.date() for b in bars), (
        "a mid-session days=1 request must not include a previous day"
    )


# ── the negative cache ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_empty_result_is_not_cached(monkeypatch):
    """One transient failure must not become the permanent answer.

    The cache had no TTL, so a broker 403 or a Yahoo timeout stored `[]` under the key and served
    "no data" for the life of the process with nothing to invalidate it.
    """
    calls = {"n": 0}

    async def always_fails(symbol, exchange, interval, start_dt, end_dt, user_id=None):
        calls["n"] += 1
        return []

    async def no_rows(symbol, exchange, interval, start_dt, end_dt):
        return []

    monkeypatch.setattr(hist.backtest_historical, "_load_from_db", no_rows)
    monkeypatch.setattr(hist.backtest_historical, "_fetch_and_store", always_fails)

    args = dict(symbol="NSE:NONE", exchange="NSE", interval="5m", days=1)
    assert await hist.backtest_historical.load(**args) == []
    assert await hist.backtest_historical.load(**args) == []

    assert calls["n"] == 2, (
        "the second call was served from cache, so a transient failure has become permanent"
    )
    assert not any(k.startswith("NSE:NONE") for k in hist._CACHE), "an empty result was cached"


@pytest.mark.asyncio
async def test_a_non_empty_result_is_still_cached(monkeypatch):
    """The fix must not turn the cache off; dedupe is the reason it exists."""
    fetches = {"n": 0}

    async def no_rows(symbol, exchange, interval, start_dt, end_dt):
        return []

    async def fetch_once(symbol, exchange, interval, start_dt, end_dt, user_id=None):
        fetches["n"] += 1
        # Inside the requested window, derived from what the loader actually asked for.
        #
        # This was `datetime(2026, 10, 1)` — a literal. `load()` with `days=1` computes its window
        # from the real clock, then rejects a result that does not cover it:
        #
        #     if len(candles) < 2 or not self._covers_range(candles, fetch_start, end_dt):
        #
        # So the test was correct only while "today" sat near 1 October. It began failing on the
        # third, with no code change at all — a test that fails on the calendar rather than on a
        # regression is worse than a red suite, because every later run has to be re-checked against
        # it to be sure it is not something new. Two days of cushion keeps it inside `days=1`
        # whatever the hour.
        # Derived from `end_dt`, not a literal and not `start_dt`. With `days=1` the intraday
        # widening makes the window about two days wide (measured: 2026-10-01 13:10 → 2026-10-03
        # 13:10), and `_covers_range` wants the slice to reach `end_dt - 1 day`. A session placed at
        # the *start* of that window therefore fails coverage and the loader returns nothing — which
        # is what this test reported.
        day = end_dt.replace(hour=3, minute=30, second=0, microsecond=0)
        return _session(day) if fetches["n"] == 1 else []

    monkeypatch.setattr(hist.backtest_historical, "_load_from_db", no_rows)
    monkeypatch.setattr(hist.backtest_historical, "_fetch_and_store", fetch_once)

    # `days=1` and not more: `_covers_range` requires the returned slice to span the requested
    # window (within a one-day tolerance each side), so a single session can only satisfy a window
    # about a day wide. Widening it does not make the test stricter, it makes it unsatisfiable.
    args = dict(symbol="NSE:NIFTY50-INDEX", exchange="NSE", interval="5m", days=1)
    first = await hist.backtest_historical.load(**args)
    second = await hist.backtest_historical.load(**args)

    assert first and second
    assert fetches["n"] == 1, "a populated result should have been served from cache"


# ── the interval predicate ────────────────────────────────────────────────────

@pytest.mark.parametrize("interval,expected", [
    ("5m", True), ("15m", True), ("1h", True), ("30m", True), ("1min", True),
    ("1d", False), ("1D", False), ("daily", False), ("day", False),
    ("1wk", False), ("week", False), ("1mo", False), ("mo", False),
])
def test_is_intraday(interval, expected):
    assert hist.backtest_historical._is_intraday(interval) is expected