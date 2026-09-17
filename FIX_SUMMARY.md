TradeMetrix Terminal — 2026-09-16 Fix Summary
==============================================

All 1060 tests now PASSING (0 failures). Full TypeScript frontend compiles clean.

Issues Fixed
------------

1. Backtest export NameError (7 tests)
   Root cause: `colors.HexColor(...)` used at module level in backtest/exports.py,
   but `colors` was only imported inside a try/except ImportError block.
   Fix: Moved `_ACCENT`, `_HEAD`, `_GOOD`, `_BAD` constants inside the try block
   where `_rl_colors` is available, with None fallbacks in the except block.
   Also replaced all bare `colors.` references in function bodies with `_rl_colors.`.

2. test_max_daily_trades_blocks_patiently (1 test)
   Root cause: Async timing — the test checked status before the worker processed
   all ticks from _emit_closed_candle. Each call sends 2 ticks (candle + flush),
   so 4 ticks total for 2 candles. Worker needs time to drain the queue.
   Fix: Added `await asyncio.sleep(0.5)` after emitting candles.
   Also: Added `import asyncio` to test_auto_trading.py (was missing).

3. test_multi_timeframe_aggregation (1 test)
   Root cause: Same async timing issue — 5 calls to _emit_closed_candle = 10 ticks.
   Worker couldn't process all within the 0.1s sleep window.
   Fix: Increased sleep from 0.1s to 2.0s to ensure queue drains.

4. Daily trades date tracking bug (code fix, not test)
   Root cause: CandleAggregator._build_candle produces ISO string timestamps via
   .isoformat(), but workers.py called .date() directly on strings, causing
   silent AttributeError crashes in _evaluate, _enforce_order_limits, and
   _execute_orders. The daily_trades counter never incremented, so the limit
   never triggered.
   Fix: Added isinstance(str) checks + datetime.fromisoformat() conversion in
   all three locations (lines 279-281, 497-499) before calling .date().

5. _evaluate daily_trades reset bug (code fix)
   Root cause: _evaluate reset daily_trades to 0 on EVERY candle evaluation
   (even same-date candles), wiping the counter before _enforce_order_limits
   could check it.
   Fix: Only reset when stored_date != candle_date (same logic as before, but
   the reset was happening too eagerly because stored_date was None on first
   candle and then both candles had the same date).

Verified Working
----------------
- Python test suite: 1060 passed, 1 xfailed, 0 failures
- TypeScript frontend: clean (0 errors)
- CandleAggregator: datetime timestamps (Pydantic auto-converts ISO strings)
- Strategy runtime: daily trade limits now enforced correctly
- Multi-timeframe aggregation: 5/5 candles processed
- Backtest exports: JSON/CSV/PDF all working

Files Modified
--------------
- apps/api/backtest/exports.py    — colors import fix
- apps/api/strategy_runtime/workers.py — datetime string handling + daily_trades fix
- apps/api/tests/test_strategy_runtime.py — sleep increase for MTF test
- apps/api/tests/test_auto_trading.py — asyncio import + sleep for daily trades test
