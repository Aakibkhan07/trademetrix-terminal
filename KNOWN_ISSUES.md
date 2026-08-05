# Known Issues — TradeMetrix Terminal v1.0.0 (GA)

Status verified 2026-08-01. Each item notes impact and mitigation. None block GA; items marked **[Action required]** need a human/ops action before or soon after launch.

## Broker

1. **Fyers token expiry requires manual re-consent (EXPIRED)**
   - Fyers access tokens last ~30 days and cannot be refreshed silently. The token for the active account expired 2026-08-01 00:30 UTC, but was re-validated automatically (auto-refresh cron) before 2026-08-04 05:37 UTC — positions/funds return live data.
   - Impact when it does expire: live order placement via Fyers fails (circuit breaker opens; watchdog alerts at T-60min). Backtests and index market data continue via the Yahoo fallback. Paper bracket SL/TARGET quotes no longer depend on a live token (Yahoo-first).
   - Behavior is now graceful: `/engine/positions|funds` return a structured `401 BROKER_TOKEN_EXPIRED` (instead of raw 500s) so the UI can prompt re-auth.
   - Fix: user re-authenticates through the UI (`/v1/brokers/fyers/re-auth`). Automation (Playwright re-consent) is blocked by Cloudflare Turnstile.

2. **Index spot unavailable from Fyers data API**
   - `NSE:NIFTY`/`NSE:NIFTY50` and the option-chain endpoint fail. Workaround implemented: spot proxy via same-month index future; strike snapping uses the option's expiry-month future.

## Security / Configuration

3. **`TRADINGVIEW_WEBHOOK_SECRET` not set in production**
   - Startup emits a warning; webhook endpoints are unauthenticated beyond CSRF until the secret is set in `apps/api/.env`.

4. **Telegram alerting not configured (production)**
   - `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` unset → the watchdog logs "[DEV] No Telegram configured" stubs. Ops must rely on Grafana/Prometheus alerts until configured.

5. **`SENTRY_DSN` not set**
   - Errors are visible via structured logs + Prometheus/Grafana only. Set `SENTRY_DSN` in `apps/api/.env` to enable.

6. **Supabase keys are service-role (BYPASSRLS)**
   - The API authenticates with the service key (RLS is bypassed by design; anon is blocked). Protect `apps/api/.env` — it is gitignored and only exists on the VPS. Rotate keys if the file is ever exposed.

## Infrastructure

15. **Dashboard "User Strategies" admin tab is dead (404 endpoint)** *(v1.5.2 finding)*
   - `app/dashboard/user-strategies-tab.tsx` fetches `/api/v1/admin/strategies/all-user`, which
     does not exist in the API → the tab always renders "No user strategies found".
   - Impact: admins cannot see user strategies in the UI (the legacy `/user-strategies` API works).
   - Mitigation: implement the admin endpoint or remove the tab. Beta backlog item (post-freeze).


7. **Single host, single API worker**
   - Uvicorn runs 1 worker on 1 VPS. The order queue is Redis-backed and recovered cross-process, but horizontal scaling requires multi-instance work. Monitor memory (768m limit) and CPU.

8. **Backups live only on the VPS disk**
   - `backup.sh` writes to `/root/trademetrix-backups/` (14-day retention). Off-host copy (rsync/rclone) is recommended; Supabase data is platform-managed and not affected.

9. **n8n + analyzer stack on the same host**
   - `trademetrix-n8n`, `analyzer-frontend-1`, `analyzer-backend-1` share the VPS. A host failure takes them down together (trade-side app is unaffected beyond shared resources).

10. **Public GitHub repo**
    - `Aakibkhan07/trademetrix-terminal` is public. No secrets are tracked (verified; `.env*` gitignored). Discipline required: never commit env files or keys.

11. **Prometheus retention fixed at 30 days**
    - TSDB retention 30d. Older metrics are gone unless backups were taken (`backup.sh` snapshots).

## Cosmetic / Minor

12. **yfinance TzCache warnings**
    - `[TzInvalidZone] cannot write /nonexistent/.cache...` — harmless; the container user can't write the cache dir. Candle data is unaffected.

13. **Yahoo fallback throttling**
    - Occasional transient throttling on Yahoo when many symbols are fetched quickly; the durable candle store caches results so retries typically succeed.

14. **[Action required] `risk_audit_log` table not yet created in prod (Beta hardening, 2026-08-04)** — **RESOLVED 2026-08-05**: migration `20260804_01600_risk_audit_log.sql` applied to prod via psql (`CREATE TABLE` + index verified; PostgREST schema reloaded — `rest/v1/risk_audit_log` returns 200). Emergency-stop audits now persist to the dedicated table; the PGRST205 fallback path remains as belt-and-braces.
   - Keep the migration idempotent and re-verify after any Supabase restore.

## Resolved during GA prep (kept for audit)

- Remote Supabase placeholder DB password → real password, all GA migrations applied (2026-08-01)
- reportlab missing in deployed image → baked into the image (5.0.0), no manual pip installs
- VPS repo 112 files behind deployed app → committed + pushed, repo authoritative at `main`
- Backup archives truncated (live-volume tar) → stopped-container tar + `tar tzf` verification, all green
- Deploy script interactive prompt under non-TTY → fully non-interactive, health-gated
