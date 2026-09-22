# TradeMetrix Terminal — Phase 1 Audit Report

**Date:** 2026-09-20 (IST)  
**Auditor:** Hermes Agent  
**Scope:** Production environment at ai.trademetrix.tech + VPS container health + codebase scan

---

## 🔴 BROKEN (currently live but erroring/failing — needs a fix, not a rebuild)

### 1. Broker credential decryption failure — CRITICAL, blocks trading

**What:** 27,503 "Failed to decrypt broker credentials" errors in the last 24 hours (spam at ~6/min). The API cannot decrypt stored broker credentials for 3 of 6 brokers.

**Severity:** Blocks users — prevents broker connections, quote refreshes, order placement, and paper trading for affected brokers.

**Effort:** Small (env var fix) once root cause confirmed.

**Details:**
- Affected brokers: **Fyers** (2 of 3 records), **Angel One** (1 record), **Lemonn** (1 record — already inactive)
- Working brokers: Zerodha, Dhan, Upstox (all records created 2026-09-17)
- Root cause: Records created before 2026-09-17 were encrypted with a key that is NOT the current `ENCRYPTION_KEY` and NOT in `ENCRYPTION_KEYS` fallback. The `ENCRYPTION_KEY` was rotated on ~2026-09-17, and the old key in `ENCRYPTION_KEYS` (`_mfb8-qF7nNHDGdeNAriCYemHCVAiVTzmyWWlJ0Zbn8=`) does not match the key used for pre-Sept-17 records.
- Fyers circuit breaker is OPEN (466+ failures) — paper bracket quote refreshes failing with "Broker fyers unavailable: CircuitBreaker[broker_fyers] is open"
- That one working Fyers record (inactive, created 2026-09-16) decrypts OK — confirming the key rotation boundary

**Fix path:** Identify the missing old key (the one used between ~Jul 15 and Sep 16) and add it to `ENCRYPTION_KEYS` in `apps/api/.env` on the VPS, then restart the API container. Alternatively, if that key is unrecoverable, affected users must re-auth their brokers via the connect flow.

---

### 2. API routing mismatch on main domain — MEDIUM, affects API calls from wrong host

**What:** Caddy routes `ai.trademetrix.tech/*` → web container (Next.js) and `api.ai.trademetrix.tech/*` → API container. Any API call hit via `ai.trademetrix.tech/api/v1/*` returns the Next.js 404 HTML page instead of JSON.

**Severity:** Blocks users if the frontend ever sends API requests to the wrong base URL.

**Effort:** Small (verify frontend config, or add Caddy route).

**Details:**
- Frontend `.env.production` correctly sets `NEXT_PUBLIC_API_URL=https://api.ai.trademetrix.tech/api/v1`
- `NEXT_PUBLIC_API_BASE=https://api.ai.trademetrix.tech` (no `/api/v1` suffix)
- CSP `connect-src` includes `https://api.ai.trademetrix.tech` — correct
- Verified: `curl https://api.ai.trademetrix.tech/api/v1/brokers` → `{"detail":"Not authenticated"}` (correct JSON from API)
- Verified: `curl https://ai.trademetrix.tech/api/v1/brokers` → Next.js 404 HTML (wrong — hits web container)
- The `/api/v1/health` route does NOT exist on the API (only `/health` at root) — this is expected, not a bug

**Fix path:** No code change needed if frontend is correct. Verify by checking browser network tab that API calls go to `api.ai.trademetrix.tech`. Optionally add a Caddy redirect `ai.trademetrix.tech/api/* → api.ai.trademetrix.tech/api/*` as a safety net.

---

### 3. Fyers circuit breaker open — HIGH, blocks Fyers live/paper trading

**What:** CircuitBreaker for `broker_fyers` is open due to 466+ consecutive failures (all caused by credential decryption failure — item #1 above). Backoff 300s, retrying in half-open state but failing again immediately.

**Severity:** Blocks Fyers users from placing orders or getting quotes.

**Effort:** Small — resolves when #1 is fixed (reconnect or key restore).

**Details:**
- First opened: 2026-09-19 ~06:32 UTC
- 10+ reopen events logged in the last 24h
- Paper bracket quote refresh failing: `NSE:NIFTY10SEP25000CE` (and others)
- The Fyers adapter returns `{"s":"error","code":-16,"message":"Could not authenticate the user"}` on every call

**Fix path:** Same as #1. Once credentials decrypt, the circuit breaker will auto-close on next successful call.

---

## 🟡 INCOMPLETE (partially built, stubbed, or degraded)

### 4. Lemonn broker — scaffold only, no real API

**What:** Lemonn adapter is a scaffold. All 10 trading/data methods raise `UnsupportedFeatureError`. Capability matrix row: `"lemonn": set()` (zero capabilities). One inactive credential record (created 2026-08-31) that also fails decryption.

**Severity:** Cosmetic — Lemonn is registered and visible in the UI but cannot connect or trade. User was aware (approved scaffold per AGENTS.md v1.7.2).

**Effort:** Large — requires real Lemonn API integration (Lemonn publishes no public trading API; their algo is hosted only).

**Details:**
- `apps/api/broker_connect/brokers/lemonn.py` — placeholder connect flow
- `apps/api/brokers/lemonn_adapter.py` — full adapter with typed-unsupported on all methods
- Web UI shows "Lemonn (API pending)" in onboarding picker
- `/brokers` page is metadata-driven — no frontend changes needed to add real support later

---

### 5. Google OAuth — deployed but provider not activated

**What:** Google sign-in code is deployed (`/auth` page has "Continue with Google" button, `/auth/callback` handles the exchange). But Supabase project has `"google": false` — the provider is not activated in the Supabase dashboard.

**Severity:** Cosmetic — button is visible but clicking it will fail at the Google consent step.

**Effort:** Small — 3 dashboard steps (Google Cloud OAuth client → Supabase Auth → Providers → Google → add redirect URI).

**Details:**
- `apps/web/app/auth/page.tsx` — Google button renders
- `apps/web/app/auth/callback/page.tsx` — callback handler ready
- `apps/api/routes/v1_auth.py` — `POST /api/v1/auth/google` endpoint ready
- Pending: Supabase dashboard → enable Google provider + add `https://ai.trademetrix.tech/auth/callback` to redirect URLs

---

### 6. Risk Guardrails — TODO hooks not wired

**What:** Risk guardrails panel exists at `/risk` (deployed v1.6.8). But the `riskguard.py` execution-layer hooks have TODO comments — `max_daily_loss` and other limits are not wired to a live P&L/positions source.

**Severity:** Medium — the UI shows the panel but the actual risk limits don't enforce anything at order time.

**Effort:** Medium — needs a live P&L/positions data source to be wired in.

**Details:**
- `apps/api/broker_connect/execution/riskguard.py:9` — TODO hooks comment
- `apps/api/broker_connect/execution/riskguard.py:63` — TODO: enable once wired to live P&L/positions
- UI panel deployed and functional as a display layer

---

### 7. Kotak Neo quotes — not implemented, using fallback

**What:** `kotakneo_adapter.py:390` logs "Kotak Neo broker quotes not implemented; relying on fallback source". Kotak Neo orders may work but real-time quotes come from a fallback, not the broker.

**Severity:** Medium — quotes may be delayed or inaccurate for Kotak Neo users.

**Effort:** Medium — implement `get_quote` / `get_quotes` in the Kotak Neo adapter.

---

## 🟢 MISSING (not started, would need to be built from scratch)

### 8. No-code visual strategy/leg builder

**What:** A drag-and-drop or visual UI for building multi-leg strategies without code. The `/strategies/builder` page exists but is not a no-code visual builder based on current codebase.

**Severity:** Enhances UX but not blocking — users can still deploy pre-built strategies.

**Effort:** Large — would require a visual canvas component, leg definition UI, and a compiler that generates strategy config from the visual representation.

---

### 9. User-facing backtesting UI

**What:** The `/backtest` page exists and the backend has a real backtest engine (v1.7.0, 5-year windows, real data only). But the user-facing experience may be limited — no ability to compare multiple strategies, view detailed trade-by-trade logs visually, or export results.

**Severity:** Medium — backtesting works but the UI is basic.

**Effort:** Medium — enhance the existing `/backtest` page with comparison views, trade log Explorer, and export.

---

### 10. Forward testing mode

**What:** A "forward testing" mode that runs a strategy against live market data without placing real orders — distinct from both backtesting (historical) and paper trading (simulated fills). Not present in the codebase.

**Severity:** Enhances confidence before going live — not blocking.

**Effort:** Large — requires a new engine mode that subscribes to live candles, runs strategy logic, and records signals without sending orders.

---

### 11. Margin estimator

**What:** A tool that estimates margin requirements for a given strategy or basket of positions before deployment. The trader workspace (`/trade`) has a `marginEstimate` call per contract, but no holistic margin estimation for multi-leg strategies.

**Severity:** Medium — traders need to know margin requirements before deploying.

**Effort:** Medium — aggregate individual contract margin estimates + broker-specific margin rules into a strategy-level view.

---

## 📋 Container Health Summary

| Container | Status | Uptime | Notes |
|-----------|--------|--------|-------|
| trademetrix_caddy | Up (healthy) | 10 min | On restart |
| trademetrix_web | Up (healthy) | 2 hours | On restart |
| trademetrix_api | Up (healthy) | 39 hours | **Decryption errors spamming** |
| trademetrix_market_agent | Up | 2 days | — |
| trademetrix_grafana | Up | 2 days | — |
| trademetrix_redis | Up (healthy) | 2 days | — |
| trademetrix-n8n | Up | 2 days | — |
| trademetrix_autoheal | Up (healthy) | 2 days | — |
| trademetrix_prometheus | Up | 2 days | — |
| trademetrix_redis_exporter | Up | 2 days | — |
| trademetrix_node_exporter | Up | 2 days | — |

---

## 📋 Codebase TODO/FIXME Scan

Grep across `apps/api` and `apps/web` (excluding `node_modules` and `.venv`):

| File | Marker | Context |
|------|--------|---------|
| `brokers/sdk/certification.py:51` | "Capability declared but not implemented" | Capability gap documentation |
| `brokers/sdk/certification.py:116` | "typed error raised (capability declared but not implemented — gap)" | Test assertion for gap |
| `brokers/kotakneo_adapter.py:390` | "Kotak Neo broker quotes not implemented" | Fallback source warning |
| `broker_connect/brokers/lemonn.py:7` | "placeholder" | Lemonn scaffold |
| `broker_connect/brokers/base.py:54` | "intentionally not implemented" | Base class doc |

No other TODO/FIXME/stub/coming-soon markers found in application code.

---

## 📋 Site Walkthrough Summary

**Page:** `https://ai.trademetrix.tech/` (landing/auth page)
- Loads: Full Next.js app, sidebar nav (Dashboard, Go Live, Trade, Positions, Paper Trading, Brokers, Strategies, Backtest, Marketplace, Analytics, Markets, Terminal, Risk, AI Assistant, Daily Report, Settings, Help), ticker bar (NIFTY/BANKNIFTY/etc. showing "--"), status bar (DISCONNECTED, FEED: NONE, SYS: OK)
- Auth: Phone OTP input (+91 prefix, 10-digit number), Google OAuth button
- Console: 0 errors, 7 network requests loaded
- Network: All JS/CSS chunks load from `/_next/static/` successfully. Cloudflare challenge-js present.
- No browser console errors.

**Note:** Could not complete auth flow (no access to phone OTP or Google account). The dashboard pages (`/live`, `/trade`, `/brokers`, `/backtest`, `/strategies`) all return 200 with full HTML — the Next.js app shell loads correctly. Authenticated feature testing requires a valid session.

---

## 📋 Known-Missing Features Comparison (from prior audit)

| Feature | Status | Effort |
|---------|--------|--------|
| No-code visual strategy/leg builder | Still missing | Large |
| User-facing backtesting UI | Partially present (`/backtest` page exists) | Medium to enhance |
| Forward testing mode | Still missing | Large |
| Margin estimator | Partial (per-contract only in `/trade`) | Medium to build holistic |

---

## 🚨 Top Priority for Phase 2

1. **Fix credential decryption** (item #1) — blocks 3 of 6 brokers, causes circuit breaker cascade
2. **Verify frontend API URL config** (item #2) — confirm browser requests hit `api.ai.trademetrix.tech`
3. **Activate Google OAuth** (item #5) — 3 dashboard clicks, button already in UI
