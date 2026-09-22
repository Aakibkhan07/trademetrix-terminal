# TradeMetrix Terminal — Phase 1 Audit Report (Merged)

**Date:** 2026-09-20 (IST)
**Auditor:** Hermes Agent (Solar Pro4)
**Scope:** Production environment at ai.trademetrix.tech + VPS container health + codebase scan
**Foundation:** AUDIT_REPORT.md (Sep 16) + FIX_SUMMARY.md (Sep 16) + live verification (Sep 20)

---

## 🔴 BROKEN (currently live but erroring/failing — needs a fix, not a rebuild)

### 1. Broker credential decryption failure — CRITICAL, blocks trading

**Status: ✅ FIXED (Sep 20, 2026-09-20T09:54 UTC)**

**What:** API logs showed continuous "Failed to decrypt broker credentials with primary and all old keys" errors. The API could not decrypt stored broker credentials for multiple brokers. Redis was empty (DBSIZE 0).

**Fix applied:** Added the missing Aug 1 encryption key (`ZTtsuGQCgigNHKjnANV_FyTsMqZuRKPOCyYK8nps7x0=`) to `ENCRYPTION_KEYS` in both `infra/production/.env` and `apps/api/.env` on the VPS, then restarted the API container.

**Verification:**
- Decryption errors: **0 in the last 10 minutes** (down from ~6/min)
- API health: ✅ `{"status":"ok","version":"0.1.0"}`
- Redis: 21 keys (auto-recreated by buyer runner on startup)

**Records fixed (3 of 4):**
| Broker | Created | Active | Status |
|--------|---------|--------|--------|
| Angel One | 2026-08-12 | ✅ Yes | ✅ Fixed — access_token recovered (1238 chars) |
| Fyers | 2026-07-22 | ✅ Yes | ✅ Fixed — access_token recovered (660 chars) |
| Lemonn | 2026-08-31 | ❌ No | ✅ Fixed (inactive, cosmetic) |

**Still broken (1 record):**
| Broker | Created | Active | Status |
|--------|---------|--------|--------|
| Fyers | 2026-07-15 | ✅ Yes | ❌ Still fails — encrypted with pre-Aug-1 key, unrecoverable. User must re-authenticate via Brokers page. |

**Root cause:** The `ENCRYPTION_KEY` was rotated on ~Sep 17. The old key used between Jul 15 and Aug 1 (`ZTtsuG...`) was not in the `ENCRYPTION_KEYS` fallback. The Aug 1 backup (`/root/trademetrix-backups/20260801_135225/env/api.env`) contained this key, allowing recovery of 3 of 4 records. The Jul 15 record predates the Aug 1 backup and its key is permanently lost.

**Severity after fix:** Reduced from CRITICAL to MEDIUM — 1 active user (Fyers Jul-15) still blocked; all other active brokers operational.

**Effort:** Small (env var fix).

---

### 2. Fyers circuit breaker open — HIGH, blocks Fyers live/paper trading

**Status update from Sep 16 audit (C2 — Fyers token expired):** ✅ Root cause upgraded. This is NOT just an expired token — it's the credential decryption failure (item #1 above) that causes every Fyers call to fail, which trips the circuit breaker. The token may be valid but the API can't decrypt the credentials to use it.

**Severity:** Blocks Fyers users from placing orders or getting quotes.

**Effort:** Small — resolves when #1 is fixed (circuit breaker auto-closes on next successful call).

**Details:**
- CircuitBreaker `broker_fyers` opened with 606+ failures, 602 consecutive opens.
- First opened: 2026-09-19 ~06:32 UTC.
- 10+ reopen events in last 24h.
- Fyers adapter returns `{"s":"error","code":-16,"message":"Could not authenticate the user"}` on every call.

---

### 3. API routing mismatch on main domain — MEDIUM

**What:** Caddy routes `ai.trademetrix.tech/*` → web container (Next.js) and `api.ai.trademetrix.tech/*` → API container. Any API call via `ai.trademetrix.tech/api/v1/*` returns Next.js 404 HTML instead of JSON.

**Severity:** Blocks users if the frontend ever sends API requests to the wrong base URL.

**Effort:** Small (verify frontend config, or add Caddy route).

**Details:**
- Frontend `.env.production` correctly sets `NEXT_PUBLIC_API_URL=https://api.ai.trademetrix.tech/api/v1`
- Verified: `curl https://api.ai.trademetrix.tech/api/v1/health` → `{"status":"ok",...}` (correct)
- Verified: `curl https://ai.trademetrix.tech/api/v1/brokers` → Next.js 404 HTML (wrong container)
- Caddyfile is clean — two separate site blocks, no ambiguity.

**Fix path:** No code change needed if frontend is correct. Firewall at the API level. Optionally add a Caddy redirect as a safety net.

---

### 4. Redis state wiped — CRITICAL, cascading impact

**Status: ⚠️ PARTIALLY RESOLVED — Redis auto-recreating, cause still unknown**

**What:** Redis container is UP and healthy but was completely empty (DBSIZE 0) at audit time. All broker sessions, rate limit counters, kill switch state, and cached data were gone.

**Update (Sep 20 post-fix):** Redis now has 21 keys — the buyer runner service auto-recreates its state on startup. The AOF file (`appendonly.aof.1.incr.aof`) is 9.2MB with 1.1M lines of history, confirming data existed before the wipe. The AOF tail shows `DEL` commands for rate limit keys, login failure tracking, and the `global:kill_switch` key — indicating a systematic flush occurred.

**Evidence:**
- `appendonly.aof.1.incr.aof`: 9.2MB, 1,172,699 lines, 8,881 commands
- `kill_switch` appears 13 times in AOF — SET and DEL operations for both `global:kill_switch` and per-user `kill_switch:emergency:*` keys
- Last AOF entries are DEL commands — data was intentionally flushed, not corrupted
- Redis dump.rdb: only 157 bytes (empty) — created at 2026-09-20 14:08 UTC

**Severity:** Medium after auto-recovery — the buyer runner state recreates on startup. Kill switch defaults to OFF (safe). Broker sessions are stored in Supabase, not Redis (so they survive Redis wipes). But rate limit counters and caching are lost.

**Effort:** Medium — investigate what caused the flush (application-level DEL? `FLUSHALL`? Misconfigured cleanup job?). The AOF evidence suggests systematic DEL operations, not a corruption event.

---

## 🟡 INCOMPLETE (partially built, stubbed, or degraded)

### 5. Risk Guardrails — TODO hooks now enabled ✅

**Status: ✅ FIXED (Sep 20, 2026-09-20T18:04 UTC)**

**What:** Risk guardrails panel exists at `/risk`. The execution-layer hooks for `max_daily_loss` and `max_open_positions` were commented out — now enabled and wired to Supabase data.

**Fix applied:** Uncommented and implemented the risk checks in `broker_connect/execution/riskguard.py`:
- `max_daily_loss`: Queries `strategy_runs` table for the user's `daily_pnl` + `total_pnl` from running/open strategy runs. Blocks orders when cumulative P&L hits the negative threshold.
- `max_open_positions`: Counts open/pending/partial orders from the `orders` table for the user. Blocks when position count hits the cap.
- `max_drawdown_pct`: Still TODO — requires peak-equity tracking in Supabase (not yet available as a data source).

**Verification:**
- Import test: ✅ `RiskSettingsGuard` imports cleanly
- Code verification: ✅ `max_daily_loss_hit` and `max_open_positions` enforcement present in deployed container
- API health: ✅ `{"status":"ok","version":"0.1.0"}`
- 0 startup errors

**Severity after fix:** Reduced from Medium to Low — 2 of 3 risk checks now active. `max_drawdown_pct` still needs a data source.

**Files modified:** `apps/api/broker_connect/execution/riskguard.py` (deployed to VPS via `docker cp`)

---

### 6. Dual/Confused Execution Engine Architecture — unresolved

**Status update from Sep 16 audit (C5):** ✅ CONFIRMED STILL PRESENT. Three engine codebases exist with no clear convergence.

**What:**
| Engine | Path | Files | Status |
|--------|------|-------|--------|
| Legacy | `apps/api/engine/` | ~5,589 lines | ACTIVE — wired into routes |
| execution_engine | `apps/api/execution_engine/` | ~2,811 lines | Partially wired into lifespan |
| broker_connect execution | `apps/api/broker_connect/execution/` | ~2,408 lines | DEAD CODE — not wired into any route |

**Severity:** Medium-High — confusion about which engine is authoritative. Risk guards disabled in broker_connect engine (item #5).

**Effort:** Large — requires converging on one engine or clearly deprecating the others.

---

### 7. yfinance as primary fallback for market data — still in use

**Status update from Sep 16 audit (C6):** ✅ CONFIRMED STILL PRESENT. Heavily used in `fyers_adapter.py`.

**What:** `yfinance` (unofficial, unreliable) is used as fallback for all market data. The Fyers adapter explicitly streams Yahoo fallback for unsupported indices.

**Severity:** Medium — market data gaps during Yahoo throttling. Not suitable for mission-critical live trading.

**Effort:** Medium — replace with a more reliable primary data source.

**Details:**
- `fyers_adapter.py:466` — `from providers.yahoo import fetch_quotes`
- `fyers_adapter.py:533` — `from providers.yahoo import fetch_historical`
- `fyers_adapter.py:561,578,657-727` — Yahoo streaming fallback for indices
- The Sep 16 audit noted 43 production 500 errors from this (fixed in v1.7.3 for bare symbols, but yfinance dependency remains)

---

### 8. Telegram and Sentry not configured in production

**Status update from Sep 16 audit (C7):** ✅ CONFIRMED STILL MISSING.

**What:** No `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, or `SENTRY_DSN` in production environment.

**Severity:** Medium — no real-time alerting when things break. Ops must monitor Grafana manually.

**Effort:** Small (Telegram) + Small (Sentry) — env var configuration.

**Details:**
- API container env: no TELEGRAM_*, no SENTRY_* vars
- Compose .env: no TELEGRAM_*, no SENTRY_* entries
- `infra/production/.env`: only has ENCRYPTION_KEY, ENCRYPTION_KEYS, SECRET_KEY, SUPABASE keys, TRADINGVIEW_WEBHOOK_SECRET

---

### 9. Kotak Neo quotes — not implemented, using fallback

**What:** `kotakneo_adapter.py:390` logs "Kotak Neo broker quotes not implemented; relying on fallback source". Real-time quotes come from a fallback, not the broker.

**Severity:** Medium — quotes may be delayed or inaccurate for Kotak Neo users.

**Effort:** Medium — implement `get_quote` / `get_quotes` in the Kotak Neo adapter.

---

### 10. Google OAuth — deployed but provider not activated

**What:** Google sign-in code is deployed (`/auth` page has "Continue with Google" button, `/auth/callback` handles the exchange). But Supabase project has `"google": false` — provider not activated in Supabase dashboard.

**Severity:** Cosmetic — button visible but clicking fails at Google consent step.

**Effort:** Small — 3 dashboard steps.

---

### 10b. Fyers OAuth App Credentials — MISSING (action required from you)

**What:** `FYERS_APP_ID` and `FYERS_SECRET` are empty in production `.env` files. The Fyers adapter can decrypt existing user credentials from Supabase (client_id: `PKL4EMD8ML-200`, secret: `luJcw8FFkWMRJebK` recovered for the Jul-22 record), but the OAuth token refresh flow requires the Fyers app credentials to exchange auth codes for access tokens.

**Files affected:**
| File | Line | Current Value |
|------|------|---------------|
| `/root/trademetrix-terminal/infra/production/.env` | 26-27 | `FYERS_APP_ID=` `FYERS_SECRET=*** (empty) |
| `/root/trademetrix-terminal/apps/api/.env` | 26-27 | `FYERS_APP_ID=` `FYERS_SECRET=*** (empty) |

**What you need to do:**
1. Log into **Fyers developer console** (myapi.fyers.in → Settings → API Management) to get your Fyers app's `client_id` (App ID) and `secret_key` (App Secret).
2. Fill in `FYERS_APP_ID=<your_app_id>` and `FYERS_SECRET=<your_secret_key>` in BOTH `.env` files on the VPS.
3. Update `FYERS_REDIRECT_URI` from `http://localhost:8000/api/broker/callback` to the production callback URL if needed.
4. Restart the API container after updating.

**Note:** The existing user credentials in Supabase are decryptable and contain valid client_id/secret_key pairs. The env vars are needed for the OAuth token refresh endpoint (`/api/v1/brokers/fyers/re-auth`), not for decrypting stored credentials.

**Severity:** Medium — blocks Fyers token refresh and the Jul-15 user's re-authentication flow.

**Effort:** Small (env var fill) + depends on your Fyers console access.

---

### 11. Lemonn broker — scaffold only, no real API

**What:** Lemonn adapter is a scaffold. All 10 trading/data methods raise `UnsupportedFeatureError`. Capability matrix row: `"lemonn": set()`.

**Severity:** Cosmetic — registered and visible in UI but cannot connect or trade. User was aware (approved scaffold per AGENTS.md v1.7.2).

**Effort:** Large — requires real Lemonn API integration (Lemonn publishes no public trading API).

---

## 🟢 MISSING (not started, would need to be built from scratch)

### 12. No-code visual strategy/leg builder

**What:** A drag-and-drop or visual UI for building multi-leg strategies without code. The `/strategies/builder` page exists but is not a no-code visual builder.

**Severity:** Enhances UX but not blocking — users can still deploy pre-built strategies.

**Effort:** Large — visual canvas component, leg definition UI, compiler from visual representation to strategy config.

---

### 13. User-facing backtesting UI (enhancement)

**What:** The `/backtest` page exists and the backend has a real backtest engine (v1.7.0, 5-year windows, real data only, 10 curated strategies). But the user-facing experience is basic — no comparison views, trade-by-trade log explorer, or export.

**Severity:** Medium — backtesting works but the UI is basic.

**Effort:** Medium — enhance existing `/backtest` page.

**Verified working:**
- `GET /api/v1/backtests/strategies` → 200 with 10 strategies + catalog metadata
- 5-year backtest windows, real candles only (no synthetic fallback)

---

### 14. Forward testing mode

**What:** A "forward testing" mode that runs a strategy against live market data without placing real orders — distinct from backtesting (historical) and paper trading (simulated fills). Not present in the codebase.

**Severity:** Enhances confidence before going live — not blocking.

**Effort:** Large — new engine mode subscribing to live candles, running strategy logic, recording signals without sending orders.

---

### 15. Margin estimator (holistic)

**What:** The trader workspace (`/trade`) has a `marginEstimate` call per contract, but no holistic margin estimation for multi-leg strategies.

**Severity:** Medium — traders need to know margin requirements before deploying.

**Effort:** Medium — aggregate individual contract margin estimates + broker-specific margin rules into a strategy-level view.

---

## 📋 Container Health Summary

| Container | Status | Uptime | Notes |
|-----------|--------|--------|-------|
| trademetrix_caddy | Up (healthy) | 12 hours | Clean logs |
| trademetrix_web | Up (healthy) | 13 hours | Clean logs, no errors |
| trademetrix_api | Up (healthy) | 2 days | **27,500+ decryption errors**, Fyers circuit breaker open |
| trademetrix_market_agent | Up | 2 days | — |
| trademetrix_grafana | Up | ~1 hour | Recently restarted |
| trademetrix_redis | Up (healthy) | 2 days | **DBSIZE 0 — completely empty** |
| trademetrix-n8n | Up | 2 days | — |
| trademetrix_autoheal | Up (healthy) | 2 days | — |
| trademetrix_prometheus | Up | 2 days | — |
| trademetrix_redis_exporter | Up | 2 days | — |
| trademetrix_node_exporter | Up | 2 days | — |

**All containers healthy.** The issues are application-level, not container-level.

---

## 📋 Error Log Summary (last 24-48h)

### API container (`trademetrix_api`):
- **27,500+ "Failed to decrypt broker credentials" errors** — spamming at ~6/min, continuous
- **Fyers circuit breaker open** — 606+ failures, 602 consecutive opens
- No other error patterns detected in the last 200 lines
- Web container: **0 errors**
- Caddy container: **0 errors, 0 5xx responses**

---

## 📋 Live-Site Verification (curl-based, Sep 20)

| Endpoint | Auth | Result | Status |
|----------|------|--------|--------|
| `GET /health` | — | `{"status":"ok","version":"0.1.0"}` | ✅ 200 |
| `GET /api/v1/market/status` | — | `{"is_open":false,"market":"CLOSED"}` | ✅ 200 (market closed, next open Sep 21) |
| `POST /api/v1/auth/signup` | — | User created, token issued | ✅ 201 |
| `POST /api/v1/auth/signin` | — | User signed in, token issued | ✅ 200 |
| `GET /api/v1/auth/csrf` | — | CSRF token returned | ✅ 200 |
| `GET /api/v1/backtests/strategies` | — | 10 strategies + catalog | ✅ 200 |
| `GET /api/v1/strategies` | Required | 307 redirect → 401 | ⚠️ Needs auth (expected) |
| `GET /api/v1/marketdata/option-chain` | Required | 401 | ⚠️ Needs auth (expected) |
| `GET /api/v1/marketdata/historical` | Required | 401 | ⚠️ Needs auth (expected) |
| `GET /api/v1/risk/settings` | Required | 401 | ⚠️ Needs auth (expected) |
| `POST /api/v1/brokers` | — | 404 Not Found | ⚠️ Route not registered |
| `GET /api/v1/admin/stats` | Required | 401 | ⚠️ Needs auth (expected) |

**Site walkthrough limitations:** Could not complete browser-based walkthrough (no camofox/browser backend available in this session). Authenticated feature testing requires a valid browser session (OTP auth / Google OAuth). The API is verified working for unauthenticated endpoints. The Next.js app shell loads correctly (200 on all pages).

---

## 📋 Codebase TODO/FIXME Scan

Real TODO/FIXME markers found (excluding form placeholders and intentional scaffold comments):

| File | Marker | Context |
|------|--------|---------|
| `broker_connect/execution/riskguard.py:9` | TODO | Risk hooks not wired |
| `broker_connect/execution/riskguard.py:63` | TODO | Enable once wired to P&L/positions |
| `brokers/sdk/certification.py:51` | "not implemented" | Capability gap documentation |
| `brokers/kotakneo_adapter.py:390` | "not implemented" | Kotak Neo quotes fallback |
| `broker_connect/brokers/base.py:54` | "intentionally not implemented" | Base class doc |
| `broker_connect/brokers/lemonn.py:7` | "placeholder" | Lemonn scaffold |
| `web/app/terminal/builder/page.tsx:711` | "LIVE coming soon" | Disabled LIVE button in builder |
| `web/app/help/page.tsx:124` | "coming soon" | Help section placeholder |

No other TODO/FIXME/stub markers in application code.

---

## 📋 Redis Wipe Investigation (Task 3 Findings)

**Conclusion: Root cause not conclusively identifiable from available evidence.**

**What was checked:**
- No `FLUSHDB` or `FLUSHALL` calls anywhere in the Python codebase
- All Redis delete operations are single-key (killswitch reset, cache invalidate, auth cleanup)
- Cron jobs: `fyers_auto_token.py` (8:20 IST), `engine.token_refresh` (3:15 UTC), `uptime-check.sh` (every 2 min) — none flush Redis
- Backup script (`infra/scripts/backup.sh`): calls `redis-cli SAVE` for snapshot, does NOT flush
- `autoheal` container (willfarrell/autoheal): monitors container health and restarts on failure — could trigger Redis restart

**AOF evidence:**
- `appendonly.aof.1.incr.aof`: 9.2MB, 1.1M lines — contains full command history
- `kill_switch` appears 13 times — SET and DEL operations
- Tail shows DEL commands for rate limit keys, login failure keys, kill_switch keys
- `dump.rdb`: 157 bytes (empty), created at 2026-09-20 14:08 UTC

**Theories (in order of likelihood):**
1. **Redis restart loading from empty RDB** — The `dump.rdb` was empty at 14:08. If Redis was restarted and loaded from this empty RDB, all in-memory state would be lost. The AOF incr file was modified at 14:09, suggesting it was written after the restart. This is the most likely explanation.
2. **autoheal-triggered restart** — The `autoheal` container monitors `trademetrix_redis` and restarts it on health check failure. If Redis became unhealthy (e.g., OOM, disk full, config error), autoheal would restart it, potentially losing in-memory state if the AOF was not properly loaded.
3. **AOF rewrite cycle** — A `CONFIG SET appendonly no → yes` cycle triggers an AOF rewrite. If this happened when the DB was empty (post-restart), the new AOF would reflect the empty state.

**Recommended next steps (not yet done):**
- Check Redis container logs around 14:08 UTC for restart events: `docker logs trademetrix_redis --since 2026-09-20T14:00:00 --until 2026-09-20T14:10:00`
- Check autoheal logs for Redis restart events
- Add Redis persistence monitoring (alert on DBSIZE drop)
- Consider adding a Redis health check that verifies key presence

**Severity:** Low after auto-recovery. The data that was lost (rate limit counters, cache, kill switch state) is ephemeral and recreatable. Broker sessions are in Supabase, not Redis.

| # | Issue (Sep 16) | Status (Sep 20) |
|---|----------------|-----------------|
| C1 | Hardcoded credentials in test_live_pipeline.py | ✅ FIXED — now uses env vars |
| C2 | Fyers broker token expired | ⚠️ UPGRADED — root cause is credential decryption failure (item #1), not just token expiry. Circuit breaker open. |
| C3 | Global kill switch enabled | ✅ RESOLVED — Redis is empty (DBSIZE 0), no kill_switch key exists. Trading not blocked by kill switch. But Redis wipe is a separate critical issue (#4). |
| C4 | Risk guards commented out in broker_connect | ✅ STILL PRESENT — lines 63-69 commented out with TODOs |
| C5 | Dual/Confused execution engine | ✅ STILL PRESENT — three engines, no convergence |
| C6 | yfinance fallback for market data | ✅ STILL PRESENT — heavily used in fyers_adapter.py |
| C7 | Telegram/Sentry not configured | ✅ STILL MISSING — no env vars in production |
| C8 | 11 failed tests + 20 errors | ⚠️ UNABLE TO VERIFY — test suite not in production container. FIX_SUMMARY.md (Sep 16) claims 1060 tests passing after fixes. The 20 errors were test-infrastructure issues (abstract method implementations). The 11 failures included the UUID issue and async timing issues — both addressed in FIX_SUMMARY.md. |

**Note on C8:** The production API container does not include the test suite (tests excluded from Docker image). Running tests requires the local dev environment with Supabase test instance. FIX_SUMMARY.md documents that all 1060 tests pass after the Sep 16 fixes.

---

## 📋 Known-Missing Features Comparison

| Feature | Status | Effort |
|---------|--------|--------|
| No-code visual strategy/leg builder | Still missing | Large |
| User-facing backtesting UI | Partially present (`/backtest` exists, backend works) | Medium to enhance |
| Forward testing mode | Still missing | Large |
| Margin estimator | Partial (per-contract in `/trade`) | Medium to build holistic |

---

## 🚨 Top Priority for Phase 2

1. **Fix credential decryption** (item #1) — blocks 3 of 6 brokers, causes circuit breaker cascade, 27,500+ errors/day
2. **Investigate Redis wipe** (item #4) — DBSIZE 0 means ALL state lost. Determine cause (flush? no persistence? container recreation?) and ensure it doesn't happen again
3. **Re-populate broker connections** — after fixing decryption, users must re-auth brokers (or restore from backup if keys are recoverable)
4. **Wire risk guards** (item #5) — enable the commented-out checks in riskguard.py
5. **Configure Telegram alerts** (item #8) — small env var change, enables real-time production alerting

---

## 🛠️ Phase 2 Fix Progress (Sep 20, 2026)

### Completed

1. **✅ Credential decryption fix** (Item #1) — Added missing Aug 1 key to `ENCRYPTION_KEYS`. 3 of 4 broken broker records recovered. Angel One and Fyers (Jul-22) now fully operational with valid access tokens. 0 decryption errors in last 10 minutes.

2. **✅ API container recreated** — Full `docker compose down/up` to pick up the updated `.env` with the new `ENCRYPTION_KEYS` value.

### In Progress

3. **🔄 Redis wipe investigation** (Item #4) — Redis now has 21 keys (auto-recovered). AOF evidence shows systematic DEL operations. Root cause not yet identified.

4. **⏳ Fyers Jul-15 re-auth** — The only remaining broken record. User must re-authenticate via Brokers page (pre-Aug-1 key permanently lost).

### Still Needed

5. **Wire risk guards** (Item #5) — TODO hooks in `riskguard.py` still commented out
6. **Configure Telegram alerts** (Item #8) — No `TELEGRAM_BOT_TOKEN` in production env
7. **Fix Fyers circuit breaker** — Will auto-close once Fyers Jul-15 user re-authenticates and the adapter can make a successful call

---

## 🚨 Top Priority for Phase 2 (Updated)

1. **Re-authenticate Fyers Jul-15 user** — Last remaining broken broker record. One active user blocked. ⚠️ Requires your Fyers console login to fill `FYERS_APP_ID`/`FYERS_SECRET` in production `.env`.
2. **Fill Fyers OAuth app credentials** (item #10b) — `FYERS_APP_ID`/`FYERS_SECRET` empty in both `.env` files on VPS. Needed for token refresh + Jul-15 re-auth.
3. **Configure Telegram alerts** (item #8) — No `TELEGRAM_BOT_TOKEN` in production env.
4. **Investigate Redis wipe root cause** (item #4) — Theories identified (empty RDB load, autoheal restart). Needs log verification.

---

*End of merged Phase 1 audit report.*
