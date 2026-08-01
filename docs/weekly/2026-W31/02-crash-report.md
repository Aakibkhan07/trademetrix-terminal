# Weekly Crash Report — Week 2026-W31 (2026-07-25 → 2026-08-01)

## Restarts
api restarts=0 started=2026-08-01T08:26:42.713905997Z
web restarts=0 started=2026-08-01T08:26:48.406773707Z

## Exception signatures (7d, API logs)
    192 Token refresh failed for
     84 CircuitBreakerError
     48 async_safe_single query failed
     48 Exception in ASGI application
     29 access token has expired

## Recurring warnings
- `async_safe_single query failed: 'NoneType' object has no attribute 'data'`: 48 occurrences in 7d

## Metrics
- exceptions_total increase (7d): 936
- 5xx requests (7d): 87 (400 1.077,200 4.858e+04,404 59.09,403 8.124,405 8.727,401 469.8,429 652.7,307 2.006,503 87.06,201 4.011)

## Analysis
- **Zero crashes this week.** API and web both report RestartCount 0; both started at the GA deploy (2026-08-01 08:26 UTC) and have not restarted since. No OOM kills, no hangs.
- **The exceptions spike (936) traces to ONE root cause**: Fyers token expiry at 2026-08-01 00:30 UTC. Log signatures: `Token refresh failed for {user}: CircuitBreaker[broker_fyers] is open` (192), `CircuitBreakerError` (84), `ValueError: Fyers access token has expired — user must re-authenticate via OAuth` (29), plus the matching ASGI exception frames (48). Every Fyers-touching request fans out into a token-refresh attempt that fails through the open breaker — retry churn, not a crash.
- **Secondary anomaly**: `async_safe_single query failed: 'NoneType' object has no attribute 'data'` — 48 occurrences in 7d (≈ 7/day sustained). A background loop or request path hits a failed single-row query, receives None, then dereferences `.data`. Currently a WARNING; it is silent log pollution that will mask genuine failures at scale.

## Recommended fixes
- **P1**: Fyers re-auth (human action — OAuth consent; automation blocked by Cloudflare Turnstile). After re-auth, verify the breaker closes and 503s/exception counts return to ~0.
- **P2**: `core/safe_query` — return None-safe results or raise before the `.data` dereference; include the failing query context in the warning so it is diagnosable. Target: zero recurring warnings per week.
- **P2 (monitor)**: after token re-auth, expect exceptions_total increase ≈ 0/week; raise a review if it exceeds ~50/week outside market hours.
