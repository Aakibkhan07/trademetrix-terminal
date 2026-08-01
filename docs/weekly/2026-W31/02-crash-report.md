# Weekly Crash Report — Week 2026-W31 (2026-07-25 → 2026-08-01)

## Restarts
api restarts=0 started=2026-08-01T09:22:27.780337795Z
web restarts=0 started=2026-08-01T09:30:16.211610616Z

## Exception signatures (7d, API logs)
    520 Token refresh failed for
    234 CircuitBreakerError
    130 async_safe_single query failed
    130 Exception in ASGI application
     63 access token has expired

## Recurring warnings
- `async_safe_single query failed: 'NoneType' object has no attribute 'data'`: 130 occurrences in 7d

## Metrics
- exceptions_total increase (7d): 1018
- 5xx requests (7d): 87 (400 1.077,200 4.91e+04,404 59.09,401 469.8,403 8.124,405 8.727,429 652.7,307 2.006,503 87.06,201 4.011)

## Analysis
(Author)

## Recommended fixes
(Author — with P0–P3 classification)
