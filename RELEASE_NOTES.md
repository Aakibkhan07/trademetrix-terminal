# Release Notes — TradeMetrix Terminal v1.0.0 (GA)

**STATUS:** ✅ GENERAL AVAILABILITY — 2026-08-01

**Validation gate:** API regression **551 passed, 1 xfailed** · web `tsc --noEmit` + prod build clean · single-command deploy E2E on prod · verified backup E2E on prod · restart-persistence verified on remote Supabase (builder strategies, backtest runs, lifecycle logs, OMS recovery).

---

## What's new since v0.2.0-rc.7 (product polish) / v1.0.0-rc (RC1)

### Strategy Lifecycle (Phase 4.3)
- Version control: every strategy save snapshots a version (ring 50) with compare/rollback as new versions
- Lifecycle: DRAFT → VALIDATED → READY → PAPER/LIVE (deploy wizard with risk/schedule config, live requires broker)
- Strategy scorecard (A–F grade, 5 metrics), activity logs, execution dashboard (runtime stats, PnL, health)
- Persistence of all of the above in remote Supabase — survives API restarts (verified)

### Institutional Backtest Engine (Phase 5)
- Durable candle store (`candles`, `corporate_actions`, `backtest_runs` tables) — Supabase-first, gap-fill, write-back
- Realistic fills: MARKET@close±slippage, LIMIT trade-through + timeout, SL/SL-M/SL-L triggers, seeded partial fills, latency candles, Indian cost model (STT, brokerage, slippage)
- Performance analytics: expectancy, R-multiples, RR, weekday/hour/month distributions, alpha/beta vs benchmark
- Optimizer: grid search (≤512 combos), walk-forward, Monte Carlo (2000 paths, prob of profit), sensitivity (OFAT)
- Exports: JSON / CSV / PDF (reportlab, baked into the image), compare runs, deploy-to-paper
- Backtests no longer require broker credentials — Yahoo fallback for NIFTY/BANKNIFTY/FINNIFTY/SENSEX when Fyers token is expired/unavailable

### Product Polish (Phase 6)
- Accessibility: skip-link, dialog semantics for global search (focus trap, restore), aria-labels/expanded/current, AA color contrast tokens
- `app/error.tsx` + `app/not-found.tsx` error boundaries, version badge (`AppVersion`) in header + portal footer
- Toast semantics (`role=status/alert`), consistent color tokens (no hardcoded hexes), empty-state copy sweep

### General Availability hardening
- **Single-command production deploy**: `bash infra/production/deploy.sh` — non-interactive, installs Docker, resets repo to `origin/main`, builds, deploys, health-gates API + web
- **Verified backup pipeline**: `infra/scripts/backup.sh` — Redis (SAVE), Prometheus (TSDB snapshot via admin API), Grafana/n8n/Caddy (consistent stopped-volume tar), env files; every archive integrity-checked; 14-day retention
- **Remote Supabase fully migrated**: all 6 GA tables (`builder_strategies`, `builder_strategy_versions`, `builder_strategy_logs`, `backtest_runs`, `candles`, `corporate_actions`) applied with RLS; PostgreSQL 17.6
- **Repo made authoritative**: 112-file backlog committed + pushed; deployment = `git reset --hard origin/main`; no tracked secrets (verified on a public repo)
- **Dependencies baked**: reportlab 5.0.0 and all runtime deps in the Docker image — fresh containers need zero manual post-install

## Bug fixes in this cycle

- Backtests run with `user_id` propagated to the data loader (run-v3 previously loaded no candles)
- Auto data source routes through the durable candle store instead of broker-only
- Yahoo fallback also engages when the user has no broker credentials at all
- Backup archives previously truncated (`tar` of live volumes / wrong tar operand) — all archives now verified
- Prometheus snapshots required `--web.enable-lifecycle` + `--web.enable-admin-api` (Prometheus 3.x flag split) — compose updated
- Deployment script no longer blocks on an interactive OpenRouter prompt under non-TTY

## Test results (GA gate)

| Suite | Result |
|-------|--------|
| API pytest (apps/api) | 551 passed, 1 xfailed (intentional) |
| Web typecheck + build | `tsc --noEmit` clean, prod build clean |
| Restart persistence (remote Supabase) | 4/4 PASS (builder strategy, backtest run, logs, versions) + OMS recovery |
| Deploy E2E (fresh from `origin/main`) | PASS — images built, api+web healthy 200, GA banner |
| Backup E2E (prod) | PASS — all components verified, exit 0 |
| Market data fallback | PASS — Yahoo returns 725 candles for NIFTY 15m without broker creds |

## Operational notes

- Deploy: `DEPLOYMENT.md` · Backup/restore: `BACKUP_RESTORE.md` · Runbook: `RUNBOOK.md` · DR: `DISASTER_RECOVERY.md`
- Known gaps: `KNOWN_ISSUES.md` · Upgrading: `UPGRADE_GUIDE.md`
- Tested environment: single VPS 187.127.185.56, Docker 24+, remote Supabase (Postgres 17.6)
