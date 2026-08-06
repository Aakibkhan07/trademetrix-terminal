# Security Report — v1.6.9 Stability Sprint

**Date:** 07 Aug 2026 · **Auditor context:** state before this sprint = `reports/Product-Acceptance-Audit-v1.6.8.md` §8.

---

## 1. Issue addressed this sprint

**P2-1 — Login brute-force / credential-stuffing exposure** (was the single audit WARN).

- **Before:** 6 consecutive wrong passwords → each `401`, correct password on the 7th attempt → **200**. No app-layer throttle.
- **After:** per-email+IP attempt limiter implemented in `apps/api/routes/v1_auth.py`:
  - Key `loginfail:{email}:{ip}` in Redis (`core.cache`), window 300 s.
  - **Progressive delay:** failed attempt #2+ sleeps `0.5 s × (n−1)` (cap 5 s) before returning 401.
  - **Lockout:** after 5 failures, requests for that email+IP return **`429 Too Many Requests`** (delays are RAC-safe — each failure increments under the window).
  - **Success path untouched:** a correct credential check only clears the counter — never delays/blocks `signin`.
  - **Client IP detection** trusts the first `X-Forwarded-For` hop (consistent with `middleware/ip_whitelist.py`), falls back to socket peer.
  - **Audit:** `auth_failed` (each throttled failure with attempts count) and `login_locked` (lockout trigger) entries via existing `record_audit`.
  - **Fail-open safety:** if Redis is unavailable, `cache.get`/`set` degrade to defaults and the throttle no-ops — legitimate logins are never locked out by an infra outage.

## 2. Existing controls re-verified (unchanged this sprint)

| Control | Status |
|---------|--------|
| CSRF on all mutating endpoints (403 without `X-CSRF-Token`) | PASS (audit + auth suite) |
| Forgot-password generic response — no user enumeration | PASS |
| Session cookie auth; admin routes 404 to non-admins | PASS |
| Admin endpoints `require_admin` / `require_super_admin` | PASS — new admin routes are **`require_super_admin`** gated |
| Kill-switch left ENABLED on prod (`global:kill_switch`) | PASS — untouched |
| No secrets in code; `.env*` gitignored | PASS — no secrets added |

## 3. New-survey items introduced by the changes

| Item | Assessment |
|------|-----------|
| Simulated option chain (`_generate_simulated_chain`) | Read-only fakes returned only to signed-in users when live providers fail; no PII/no writes; deterministic per symbol. |
| `admin_ip_whitelist` read path | Existing middleware cache (`admin_ip_whitelist` key, 60 s TTL) is invalidated by add/remove — no stale-allow. |
| CORS headers on 500s | Only mirror the configured `allow_origins` (echo of matching origin / `*` for wildcard); does not widen the CORS policy. |
| Login throttle bypass attempts | Keyed on email (lowercased) + first forwarded hop; an attacker rotating IPs still triggers per-email counters only if they share an egress IP — Redis-backed global count is not implemented (out of scope for the verified P2). |

## 4. Verification

- `apps/api/tests/test_auth_throttle.py` (4): forwarded/IP extraction, socket fallback, success-clears, progressive→429.
- Full regression re-ran with the throttle active: `tests/test_auth.py` unaffected (Redis-absent test env → throttle no-op, routes intact).
- Post-deploy check scheduled: 6 wrong passwords → delays + 429 on the 6th; correct password immediately after the window → 200; `login_locked` / `auth_failed` present in audit trail.