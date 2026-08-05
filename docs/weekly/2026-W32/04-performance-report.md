# Weekly Performance Report — Week 2026-W32 (2026-07-29 → 2026-08-05)

## Traffic (7d)
- Total requests: 101600
- By status: 405 32.87,204 0,200 9.947e+04,401 917.3,404 48.35,403 58.17,400 2.08,429 785.1,307 12.22,503 178,422 1.001,500 0,201 45.02,409 2.004
- p95 latency: API 0.249s · edge (Caddy) 0.663s

## Error rates
- 5xx (7d): 178 · 4xx (7d): 1847

## Capacity / resources
trademetrix_api mem=357MiB / 768MiB cpu=6.05%
trademetrix_web mem=50.3MiB / 512MiB cpu=0.02%
trademetrix_prometheus mem=148MiB / 512MiB cpu=0.26%
trademetrix_caddy mem=20MiB / 128MiB cpu=0.00%
trademetrix_market_agent mem=37.3MiB / 256MiB cpu=0.02%
trademetrix_grafana mem=131.7MiB / 256MiB cpu=0.75%
trademetrix_redis mem=4.859MiB / 256MiB cpu=0.51%
trademetrix-n8n mem=308.9MiB / 1GiB cpu=0.11%

## Circuit breakers
broker_fyers 0

## Analysis
- **Traffic doubled (50,390 → 101,600) while p95 latency improved** (API 0.332s → 0.249s; edge 1.262s → 0.663s). No capacity concerns; the request mix is heavily `GET /metrics` (prometheus scrape) + `/health` + the builder-score endpoints.
- **5xx all 503 (178, 0.18%)**, concentrated in the pre-hardening window (expired Fyers token era); 0×500 this week. Last-24h 503/ASGI noise is `EndOfStream` client-aborts (10×).
- **Resources all well under limits**; API at 46% memory (357MiB/768MiB) with cpu 6.05% — headroom for the doubling traffic. Web 10%, Prometheus 29% of limit.
- **Circuit breakers**: broker_fyers OPEN count 0 this week (W31: 2). The breaker trips seen 08-03/08-04 in logs were the token-expiry window and have not recurred since the 08-04 fixes.
- **Latency hotspots by path** (from top-path rates): builder `score`/`logs` (0.0078/0.0058) and `marketdata/historical` (0.0042) are the hot user paths; nothing p95-critical observed.

## Recommendations
- Keep the two gating SLIs: 5xx < 0.2% and breaker OPEN = 0; alert on either via Grafana (no Telegram yet — KNOWN_ISSUES #4).
- Add a per-path p95 panel for `/api/v1/builder/*` and `/api/v1/marketdata/historical` so a backtest regression (38 runs/week now) shows up before users feel it.
- Watch API memory trend: 357MiB at 31 users; re-check when sign-ups accelerate past ~60 accounts.
