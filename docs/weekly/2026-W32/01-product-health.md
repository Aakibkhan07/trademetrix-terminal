# Weekly Product Health Report — Week 2026-W32 (2026-07-29 → 2026-08-05)

## Summary
- Users: users=31 · Sign-ins: signed_in_ever=12,last7d_signins=3
- Adoption: strategies=9,builder_strategies=20,backtest_runs=38,orders=45,creds=4
- Backtest runs: runs_by_user=5 total_runs=38
- Requests (7d): 101600 · 5xx: 178 · 4xx: 1847
- Exceptions (7d): 1503 · Breakers: broker_fyers 0
- Credentials: fyers/needs_attention=2,fyers/valid=2

## Orders by status (7d)
FILLED=31,CANCELLED=8,REJECTED=6

## Top paths by rate (7d)
/metrics 0.06634,/health 0.03336,/api/v1/alerts/ 0.008659,/health/live 0.008256,/api/v1/builder/strategies/79cc22e33092/score 0.007842,/api/v1/builder/strategies/2b44c983247f/score 0.005833,/api/v1/marketdata/historical 0.004235,/api/v1/engine/orders 0.003593,/api/v1/market/instruments 0.003038,/api/v1/brokers/credentials 0.002942,/api/v1/strategies/assigned 0.002457,/api/v1/brokers/metadata 0.002434

## Open P0/P1 issues
None — INC-015 (kill-switch), INC-016 (raw 500s from expired broker token), INC-017 (paper bracket quote starvation) resolved and deployed 2026-08-04 (commit `fd896ca`). Severity-ranked open queue in `docs/weekly/2026-W32/12-top-10-issues.md`.

## Analysis
- **Usage acceleration is real (evidence: Supabase adoption columns + Prometheus top-paths).** Backtest runs went 2 → 38 (19×) across 5 users; builder strategies 7 → 20; total accounts 26 → 31 (+5). The `/api/v1/builder/strategies/*/score` paths (0.0078, 0.0058 rate) confirm the Strategy Builder is a daily-used path. Orders flat (43 → 45; 31 FILLED / 8 CANCELLED / 6 REJECTED). Broker connection remains the funnel blocker: 4 of 31 accounts connected a broker, 2 of those placed orders (see 06-funnel).
- **Reliability improved on every axis vs W31, driven by the 08-04 hardening sprint.** Zero container restarts. fyers breaker OPEN count 2 → 0. Credentials moved from 1 valid/3 needs_attention → 2 valid/2 needs_attention (token revalidated by the auto-refresh cron before 08-04 05:37 UTC). The 5xx volume (178, all 503) is concentrated in the night before/around the hardening deploy and maps to the expired-token period: `exports_total` exceptions (1503) raster-matched with the "Token refresh failed" (16,810 log lines/7d) and "access token has expired" (174) signatures that now print 0× in the last 24h of logs.
- **5xx rate 0.18% of 101,600 requests; last 24h genuinely clean.** Remaining ASGI exceptions in the last 24h are `anyio.EndOfStream` (10×, aborted client connections — benign) plus known external gaps (Fyers `history` 404, option-chain WAF 403).
- **Honest engagement is low: 3 signed-in users in the last 7 days.** The DAU series (08-04 = 49) and 74 sessions are inflated by smoke/E2E traffic and anonymous landing sessions. Until the tracker separates signed-in vs anonymous, sign-in counts are the ground truth.
- **Traffic doubled (50,390 → 101,600) with better latency** — p95 API 0.332s → 0.249s, edge 1.262s → 0.663s. Capacity is not a constraint; requests are dominated by `/metrics`, `/health`, `/alerts` polling.

## Recommendations
- In 03-ux/report split tracked users into signed-in vs anonymous so DAU/bounce are not confused by smoke traffic; prioritize the split above new funnel numbers.
- Ring-fence the beta activation gap: broker connection at 13%, and the Fyers re-auth friction (KNOWN_ISSUES #1) sits directly on it.
- ✅ DONE 2026-08-05: the 9 E2E-test feedback artifacts marked `wontfix` — W33 feedback counts real user reports only.
- Keep 5xx < 0.2% and fyers breaker OPEN = 0 as the two gating health SLIs for beta.