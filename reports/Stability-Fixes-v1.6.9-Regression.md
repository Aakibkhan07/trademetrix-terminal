# Regression Report — v1.6.9 Stability Sprint

**Date:** 07 Aug 2026 · **Base:** `d0367ca` (v1.6.8) · **Method:** full suite + focused suites + web gates
**Environment:** local (before deploy)

---

## 1. Result summary

| Gate | Scope | Result |
|------|-------|--------|
| API unit + integration + regression | **full** `apps/api tests/` | **981 passed, 1 xfailed (8 warnings)** |
| Focused affected suites | marketdata, auth, admin, ratelimit, + 4 new files | **81 passed** |
| New tests | option-chain normalize (7), journal resilience (5), auth throttle (4), audit null-user (2) | **18/18 passed** |
| Baseline comparison | v1.6.8 known-good = 963 passed, 1 xfailed | **+18 tests, 0 regressions** |
| Web typecheck | `tsc --noEmit` | **0 errors** |
| Web lint | `next lint` | **0 new** (1 pre-existing warning: `deploy-wizard.tsx` `useMemo` deps) |
| Web production build | `next build` (`.env.production` swap + restore) | **clean**, BUILD_ID `QiL_h7JpOgCdxeeLs4DV6` |

## 2. Full API suite

Command: `.venv/bin/python -m pytest tests/ -q`

- **981 passed, 1 xfailed** in 37.5s. The single `xfailed` is the pre-existing intentional xfail (present at baseline). The 8 warnings are the same Pydantic serialization warnings as baseline (none new).

## 3. Focused affected-area suites (post-change)

- `tests/test_marketdata.py` → all passed
- `tests/test_auth.py` → all passed (9) — signin now runs the throttle prologue/epilogue paths; Redis is unavailable in test env so the throttle no-ops gracefully, and the route still returns the expected 401/200 codes.
- `tests/test_admin_service.py` → all passed, incl. updated route-inventory test (now asserts the 3 new routes exist).
- `tests/test_ratelimit_hardening.py` → all passed.
- New: `tests/test_option_chain_normalize.py` (7), `tests/test_journal_resilience.py` (5), `tests/test_auth_throttle.py` (4) → **16/16 passed**.

## 4. Defect-adjacent regression checks

- **P1-1:** engine `get_option_chain(NIFTY50-INDEX|NIFTYBANK-INDEX|FINNIFTY-INDEX|SENSEX-INDEX)` always returns a chain (NSE → Fyers → simulated); `v1_market.py` engine route and `v1_marketdata.py` route both delegate to the same shared engine — no more 503 for supported families. Unsupported symbol → 503 as designed.
- **P1-2:** journal `_get_recent_trades` reads `orders` first (FILLED, `created_at desc`), falls back to `trades`; any table failure → `[]`, so `analyze_trades` returns the "No trades found" body instead of 500. Global handler now attaches `Access-Control-Allow-Origin` + `Vary: Origin` to unhandled 500 responses (headers param verified via `error_response` signature).
- **P1-3:** all 3 new admin routes registered (router-internal validation in `test_admin_service.py`); web tabs now target `API_BASE` (no relative-origin burst), `tsc` + `next build` clean.
- **P2-1:** throttle only delays/429s failed attempts; the successful path is never delayed or blocked (counter reset only). `test_auth_throttle.py` proves the fail path (progressive → lockout) and the success path (reset).
- **Audit (found in prod verification):** `core.audit._do_insert` coerces empty `user_id` → `None` (`audit_log.user_id` is a nullable UUID column; PostgREST rejects `""` with `22P02`). `test_audit_null_user.py` proves empty→NULL and non-empty preserved.

## 5. Post-deploy checks (COMPLETE — prod verified)

- Prod CORS on 500: routed 500 now echoes `Access-Control-Allow-Origin` for configured origins (verified locally with an allowed origin; prod `CORS_ORIGINS` includes `https://ai.trademetrix.tech`).
- Prod P1-1: `option-chain` for `NIFTY50-INDEX|NIFTYBANK-INDEX|SENSEX-INDEX` → 200 (simulated fallback, 19 strikes); `/market/option-chain` → 200 with live NSE data (101 strikes).
- Prod P1-2: `/ai/journal` → 200 + CORS headers with the AI origin.
- Prod P1-3: super-admin gated: non-admin 403; promoted user → `users/with-brokers` 200 (29 users), `ip-whitelist` GET 200 / POST add 200 / DELETE 200 (row cleaned).
- Prod P2-1: 5 wrong passwords → progressive delays (0.7→2.5s), 6th → 429; audit `auth_failed` (terms 2–5) + `login_locked` (term 6) persisted. Correct password after a fresh key → 200.
- Browser smoke on prod (puppeteer-core, Chrome, 1440×900): **9/9 PASS** — sign-in lands `/dashboard`; workspace Option Chain opens with strike rows (`NSE:NIFTY50-INDEX`); `/journal` AI journal renders without load failure; admin dashboard shows Trade Router / IP Whitelist tabs; IP Whitelist tab lists IPs + default `*` Allow-all; no page errors (only the benign anonymous `/auth/me` 401, documented).
- Mobile 390px regression (puppeteer, iPhone-ish viewport): **6/6 PASS** — sign-in works, `/journal`, `/workspace`, `/dashboard` render with `scrollWidth=390` (no horizontal overflow), no page errors.