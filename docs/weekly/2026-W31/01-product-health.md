# Weekly Product Health Report — Week 2026-W31 (2026-07-25 → 2026-08-01)

## Summary
- Users: users=26 · Sign-ins: signed_in_ever=11,last7d_signins=9
- Adoption: strategies=9,builder_strategies=7,backtest_runs=2,orders=43,creds=4
- Backtest runs: runs_by_user=1 total_runs=2
- Requests (7d): 49880 · 5xx: 87 · 4xx: 1199
- Exceptions (7d): 936 · Breakers: broker_fyers 2
- Credentials: fyers/needs_attention=3,fyers/valid=1

## Orders by status (7d)
FILLED=29,CANCELLED=8,REJECTED=6

## Top paths by rate (7d)
/metrics 0.03332,/health 0.01669,/api/v1/alerts/ 0.008517,/health/live 0.004136,/api/v1/market/instruments 0.002948,/api/v1/marketdata/historical 0.00265,/api/v1/engine/orders 0.00195,/api/v1/brokers/credentials 0.0019,/api/v1/brokers/metadata 0.001678,/api/v1/brokers/list 0.001664,/api/v1/strategies/assigned 0.001641,/api/v1/engine/positions 0.001088

## Open P0/P1 issues
- **P1 — Fyers token expired (2026-08-01 00:30 UTC): live trading blocked** — [#2](https://github.com/Aakibkhan07/trademetrix-terminal/issues/2); 3/4 broker credentials `needs_attention`; circuit breaker `broker_fyers` OPEN all week; watchdog re-auth attempts = the entire exceptions spike.
- **P1 — No feedback channel + no analytics: user reports cannot reach us** — [#3](https://github.com/Aakibkhan07/trademetrix-terminal/issues/3) (P1 for the observation program: without it, every weekly report depends on manual log/DB spelunking).
- **P2** — [#4](https://github.com/Aakibkhan07/trademetrix-terminal/issues/4) `safe_query` NoneType warnings · [#5](https://github.com/Aakibkhan07/trademetrix-terminal/issues/5) 429s during polling. **P3** — [#6](https://github.com/Aakibkhan07/trademetrix-terminal/issues/6) dormant accounts.

## Analysis
- **Adoption is pre-beta.** 26 accounts exist, but 15 have NEVER signed in; 11 signed in at least once, 9 in the last 7 days (concentrated Jul 27–31). Every piece of product data — 9 strategies, 7 builder strategies, 2 backtest runs, 43 orders — belongs to the founder/test account (fa668109). **No real user has yet created a strategy, run a backtest, or placed an order.**
- **Traffic is dominated by health probes + UI polling**: `/metrics`, `/health`, `/alerts/` are the top 3 paths; the remaining load is a working trading surface being exercised by one session (`/market/instruments`, `/marketdata/historical`, `/engine/orders`, `/brokers/*`).
- **Reliability of the week = Fyers token expiry.** 49.8k requests, 48.5k returned 200; 87× 503 (Fyers-dependent paths failing through the open circuit breaker). The 932 exceptions are essentially one root cause (token refresh retry churn).
- **Credentials are 3/4 broken** (`needs_attention`) — the platform has 4 credential rows but only 1 valid token, all Fyers.
- 429 rate-limit responses (653 in 7d, ~93/day) need a root-cause check: likely UI pollers hitting the 60 s cooldown window.

## Recommendations
1. Re-authenticate the Fyers token now (P1; unblocks the only funded live account).
2. Fix `async_safe_single` NoneType warning (P2; 28×/day log noise that will mask real failures as volume grows).
3. Stand up a feedback channel + light product analytics before the next beta wave (P1 for observation capability — see Customer Feedback report).
4. Audit the 429 volume per path before the next user wave; if pollers trip the limiter, tune limits for authenticated polling (usability over strictness).
