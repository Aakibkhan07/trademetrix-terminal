# Weekly Most Used Features Report — Week 2026-W32 (2026-07-29 → 2026-08-05)

## Top tracked events (7d: event | count | users)
click | 587|27;page.view|564|73;session.start|213|73;backtest.run|23|3;client_error|20|7;strategy.created|20|3;broker.connected|3|1

## All-time events: 1529
- Errors (7d): errors7d=119

## Analysis
- First real event ranking: **session tracking (213), page views (564) and clicks (587 by 27 users) dominate**; the value-feature events are backtest.run (23 by 3 users), strategy.created (20 by 3 users), broker.connected (3 by 1 user).
- Page-level ranking (7d, page.view by path): `/portfolio` 69, `/workspace` 34, `/positions` 32, `/funds` 30, `/` 30, `/terminal` 24, `/brokers` 20, `/analytics` 19, `/marketdata` 18, `/dashboard` 17, `/strategies/builder` 17, `/paper` 16. **Portfolio is the most-visited surface**; broker-adjacent pages (`/brokers`) out-number builder.
- Client-side errors: 20 events / 7 users (all pre-08-03 build; see 03-ux).
- Backtest usage (38 runs, 3 tracked run events) is concentrated in the 5 users driving the W32 growth — the backtest/builder loop is the current "power path" and is broker-free.

## Recommendations
- Rank builder/backtest feature surface by the new `/api/v1/builder/*/score|logs` telemetry (2nd/3rd busiest paths) in W33.
- Instrument "backtest exported / shared" (the report page shipped this week) — 5 users deep in backtests is the widest audience for feedback/retention.
- Aggressively fix the one crash class (already done) before inviting more traffic; errors7d=119 includes server-side api_error records which halved after the 08-04 hardening.
