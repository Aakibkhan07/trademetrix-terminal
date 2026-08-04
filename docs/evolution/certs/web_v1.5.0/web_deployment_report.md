# TradeMetrix Web — Deployment Report (Auto Trading v1.0)

- **Build**: `next build` (Next.js 14.1.0, React 18.3) — clean, 0 errors, 0 warnings
- **BUILD_ID**: `gJiJa4QYQJlUThzieN0Ff`
- **Bundle**: 620 files, 4.5 MB server + 2.1 MB static (excl. regenerable cache)
- **Env**: `.env.production` (prod Supabase + `https://api.ai.trademetrix.tech/api/v1`), restored after build
- **Typecheck**: `npx tsc --noEmit` clean

## Deployment steps

1. Build with production env (`cp .env.production .env && npm run build`, env restored after)
2. `tar czf` `.next` (excluding `.next/cache`), `scp` to VPS
3. `docker cp` → `trademetrix_web:/tmp/`
4. `docker exec -u root` — `rm -rf .next && tar xzf && chown -R node:node .next`
5. `docker restart trademetrix_web` — `Ready in ~1.1s`, container `healthy`

## Route availability (all HTTP 200)

`/` `/auth` `/dashboard` `/strategies` `/strategies/builder` `/paper` `/portfolio`
`/positions` `/marketdata` `/terminal` `/terminal/option-chain` `/workspace`
`/backtest` `/risk` `/funds` `/settings` `/transparency` `/status`

## Integrity

- Served strategies-page chunk matches the local build byte-for-byte (sha1 `e00f40fd…`)
- New runtime client present in deployed chunks: `runtime/emergency`, `runtime/accounts`,
  `runtime/pause-all`, `confirm_live`, `Emergency Stop` UI

## Post-deploy fixes shipped in this release

- `strategy_runtime/manager.py` + `workers.py`: `position_manager.get_positions` is **sync**
  — removed erroneous `await` that made `max_positions` gating and `position_consistency`
  silently no-op in production (unit-test stubs were async and masked it)
- `reconcile` reports broker truth under `broker_positions` (no longer overwrites the
  string `broker` field)
- `tests/test_auto_trading.py`: stub made sync to match the real contract

## Regression

- Full API suite: **832 passed, 1 skipped (credential-gated live cert), 1 xfailed**
- Web: `tsc --noEmit` clean + `next build` clean before and after

## Known pre-existing prod noise (not regressions)

- `/api/v1/engine/positions|funds` CORS-blocked in browser: admin user's Fyers token is
  expired → circuit breaker open → 500 → error path omits CORS headers (tracked in
  CHANGELOG since 2026-08-01; pending Fyers re-auth)
- `analytics/track-batch` 429 during smoke: rate-limit bucket exhausted by repeated E2E runs
