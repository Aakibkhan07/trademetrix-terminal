# Weekly Performance Report — Week 2026-W31 (2026-07-25 → 2026-08-01)

## Traffic (7d)
- Total requests: 49880
- By status: 400 1.077,200 4.858e+04,404 59.09,403 8.124,405 8.727,401 469.8,429 652.7,307 2.006,503 87.06,201 4.011
- p95 latency: API 0.333s · edge (Caddy) 1.188s

## Error rates
- 5xx (7d): 87 · 4xx (7d): 1199

## Capacity / resources
trademetrix_web mem=38.87MiB / 512MiB cpu=0.00%
trademetrix_api mem=166.7MiB / 768MiB cpu=0.52%
trademetrix_prometheus mem=74.59MiB / 512MiB cpu=0.21%
trademetrix_caddy mem=15.67MiB / 128MiB cpu=0.00%
trademetrix_market_agent mem=37.3MiB / 256MiB cpu=0.02%
trademetrix_grafana mem=129.5MiB / 256MiB cpu=0.78%
trademetrix_redis mem=4.168MiB / 256MiB cpu=2.73%
trademetrix-n8n mem=292.3MiB / 1GiB cpu=0.12%

## Circuit breakers
broker_fyers 2

## Analysis
- **Latency is healthy at current load**: API p95 = 0.333 s, edge (Caddy) p95 = 1.188 s. Edge adds ~0.85 s p95 (TLS + proxy); acceptable but worth watching as traffic grows.
- **Availability**: 97.4% of requests returned 200. The 87× 503s are Fyers-token-dependent paths failing through the open circuit breaker — an availability artifact of the credential expiry, not a capacity problem.
- **Error mix by status (7d totals)**: 400 ×1, 401 ×470 (session churn), 403 ×8, 404 ×59 (stale routes), 405 ×9, 429 ×653 (rate limiter — see UX report), 503 ×87, 307 ×2.
- **Capacity is massively underused**: API 167/768 MiB (22%), web 38/512 MiB, n8n 292/1024 MiB, Grafana 131/256 MiB, Prometheus 66/512 MiB. CPU ≤ 1.1% across the stack. No memory trend risk observed this week.
- **Circuit breaker**: `broker_fyers` OPEN (state 2) — live broker path is down pending re-auth; fallbacks (Yahoo data for indices) keep backtests/alerts working.

## Recommendations
1. Re-auth Fyers (P1) — the 503 count should drop to ~0; re-check next week.
2. Investigate the 401 cluster (470/7d): if it's session-expiry churn from the UI, check the login-redirect UX; if it's probes, ignore. Also confirm whether the 404s (59) map to client routes calling endpoints the API no longer serves.
3. Keep p95 API under 1 s as a weekly watch item; no capacity spend until sustained traffic justifies it (current headroom ~5×).
