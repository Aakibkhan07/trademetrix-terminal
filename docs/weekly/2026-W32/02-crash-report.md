# Weekly Crash Report — Week 2026-W32 (2026-07-29 → 2026-08-05)

## Restarts
api restarts=0 started=2026-08-05T07:27:51.752356742Z
web restarts=0 started=2026-08-05T07:15:52.922083322Z

## Exception signatures (7d, API logs)
  16810 Token refresh failed for
    174 access token has expired
     86 CircuitBreakerError
     85 async_safe_single query failed
     63 Exception in ASGI application

## Recurring warnings
- `async_safe_single query failed: 'NoneType' object has no attribute 'data'`: 85 occurrences in 7d

## Metrics
- exceptions_total increase (7d): 1503
- 5xx requests (7d): 178 (405 32.87,204 0,200 9.947e+04,401 917.3,404 48.35,403 58.17,400 2.08,429 785.1,307 12.22,503 178,422 1.001,500 0,201 45.02,409 2.004)

## Analysis
- **Dominant 7d signature (16,810 "Token refresh failed", 174 "access token expired") is a resolved incident, not a live problem.** The Fyers token for the active account expired ~08-01 00:30 UTC; the auto-refresh cron revalidated it before 08-04 05:37 UTC and INC-016 (deployed 08-04) made those failures structured 401s instead of raw tracebacks. Grep of the last 24h container logs shows 0× "Token refresh failed" and 0× "CircuitBreaker[broker_fyers] is open".
- **Remaining 24h exceptions are benign or known (evidence: `docker logs --since 24h`).** `anyio.EndOfStream` 10× (client aborted mid-request — normal web noise), `Exception in ASGI` 12× (11 of them = the EndOfStream group), `async_safe_single ... None` 7×, `22P02` 7×, `risk_audit_log PGRST205` 1×.
- **Two server-side error signatures deserve real fixes:**
  1. `risk.kill_switch: Failed to persist emergency stop (release): Could not find the table 'public.risk_audit_log' (PGRST205)` — KNOWN_ISSUES #14 [Action required]; emergency-stop audits are falling back to `audit_log` and erroring every write. Migration `20260804_01600_risk_audit_log.sql` is idempotent and not yet applied to prod.
  2. `strategy_runs row for <hex> skipped (runner continues): invalid input syntax for type uuid` (8×/48h) + `execution.manager: Failed to insert order atomically ... "smoke"` — pre-existing builder-hex-id vs uuid-column schema debt (documented in AGENTS.md); runner continues by design, but it is silent data loss for the runtime state.
- `async_safe_single ... NoneType` (653×/48h) is the largest recurring log-noise item; it is treated as "no row" (benign) but should be downgraded from WARNING and rate-limited.
- No client-side crash since 08-03; the Aug 1–2 color-parsing crash (20 events) is fixed in the live build (verified: `components/chart.tsx` + `app/backtest/page.tsx` pass parsed hex to lightweight-charts, see 03-ux).
- 5xx all 503, count 178, concentrated in the pre-hardening window; 500 = 0 this week.

## Recommended fixes
- **P1 — DONE 2026-08-05**: `supabase/migrations/20260804_01600_risk_audit_log.sql` applied to prod (psql + PostgREST schema reload; `rest/v1/risk_audit_log` 200). PGRST205 on emergency-stop writes eliminated.
- **P2** — Downgrade `async_safe_single ... None` from WARNING to DEBUG (or add per-minute log throttle): ~470×/day of noise hides real errors.
- **P2** — Track `strategy_runs.strategy_id` as TEXT (or store builder runs separately) to stop the 22P02 skip warnings and make runtime state durable.
- **P3 — DONE 2026-08-05**: the 9 E2E feedback artifacts marked wontfix; EndOfStream-aware 503s treated as expected, no code change needed.
