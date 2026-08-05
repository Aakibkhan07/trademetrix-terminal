# Weekly Top 10 Issues — Week 2026-W32 (2026-07-29 → 2026-08-05)

| # | Issue | Priority | User impact (evidence) | Status |
|---|-------|----------|------------------------|--------|
| 1 | Fyers token expiry cycle → broker step failure (KNOWN_ISSUES #1, INC-016) | P1 | 2/4 creds needs_attention; 13% broker connect (4/31); 16,810 token-refresh log lines in 7d; structured 401s now but re-auth still manual (Turnstile) | Mitigated (08-04) / open |
| 2 | `risk_audit_log` table missing → PGRST205 on every emergency-stop write (KNOWN_ISSUES #14) | P1 | Emergency-stop audit records fall back to audit_log with an error per write; kill-switch audit trail incomplete | **RESOLVED 2026-08-05** (migration applied + PostgREST reloaded) |
| 3 | Client crash: `Failed to parse color: color-mix(...)` (lightweight-charts) | P2 | 20 events / 7 users (08-01–02) — chart panel fails to render; 0 occurrences since 08-03 fix | Resolved (08-03) |
| 4 | 429 on `/api/v1/alerts/` from poller (610/7d of 785 total 429s) | P2 | Not user-visible yet; saturates rate-limiter budget; poll reliability risk | Open |
| 5 | Fyers data-source gaps: option-chain WAF 403, history 404 (KNOWN_ISSUES #2) | P2 | Market-data panels depend on Yahoo fallback; options chain dead on prod | Open (external) |
| 6 | `async_safe_single ... NoneType` log noise (653×/48h) | P2 | None (treated as no-row) — hides real errors, burns log volume | Open |
| 7 | `strategy_runs` 22P02: builder hex ids vs uuid column (8×/48h, runner continues) | P3 | Runtime state rows silently skipped for builder strategies | Open (schema debt) |
| 8 | Order atomic-insert 22P02 for `smoke` client-order-ids | P3 | Affects smoke/E2E order placement only; live orders unaffected | Open (test harness) |
| 9 | 65% single-page bounce (48/74 sessions) | P3 | Visitor-only artifact pending auth split; not actionable until W33 | Monitoring |
| 10 | Dashboard "User Strategies" admin tab dead endpoint (KNOWN_ISSUES #15) | P3 | Admins can't see user strategies in UI (404 → empty table) | Open (beta backlog) |

## Closed this week
- INC-015 kill-switch gate silently disabled + emergency state lost on restart — fixed (`fd896ca`, Redis-backed + recover()).
- INC-016 raw 500s on `/engine/positions|funds` from expired token — fixed (structured `BROKER_TOKEN_EXPIRED` 401s; 0 CircuitBreaker tracebacks since).
- INC-017 paper bracket quote starvation + 5,542-line log spam — fixed (market-cache/Yahoo-first + 1/min throttle).
- Client color-parse crash (issue #3 above) — fixed 08-03 in the workspace chart + all new backtest charts use hex.

## Analysis
- Week 32's reliability story is "a bad week, fixed well": one external event (Fyers token expiry) explains most of the 5xx/exceptions/log-line volume, and the 08-04 hardening (kill switch, token expiry, bracket quotes) converted the raw-500s era into structured errors with zero recurrences in the last 24h.
- The remaining pain is concentrated in two places: the broker step (issues 1 + 5 — where activation dies) and data/schema hygiene (2, 6, 7 — no user impact yet, but they pollute the error channel that beta monitoring depends on).
- No P0s are open. Issue #2 (the ready migration) was applied 2026-08-05 — pure ops, zero code risk, verified end-to-end (table + index + PostgREST 200). The open list is now: broker step friction (1, 5), alerts poller (4), log noise (6), schema debt (7), test-harness (8), monitoring (9, 10).
