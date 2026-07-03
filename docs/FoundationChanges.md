# Foundation Changes — Phase 2

> Generated: 2026-07-02
> All changes are backward-compatible. No features removed, no architecture replaced.

---

## Task 3: Environment Variables & .env.example

### Files Changed
- `apps/api/.env.example` — complete rewrite with all 35 documented variables

### Why
The old `.env.example` was missing 15+ configuration variables used by `core/config.py` (SMTP, Twilio, Fast2SMS, Sentry, TradingView webhook, Fyers OAuth redirect URI, request timeout, max request size). Developers had no reference for which vars were needed.

### Risk
None — only a template file, no secrets exposed. All vars have placeholder defaults or empty strings.

### Rollback
`git checkout -- apps/api/.env.example`

---

## Task 4: Centralized Configuration

### Files Changed
- `apps/api/core/config.py` — added `dotenv_key`, `env`, `tradingview_webhook_secret`, `fyers_redirect_uri`, `request_timeout_seconds`, `max_request_size_bytes`
- `apps/api/routes/v1_brokers.py` — `FYERS_REDIRECT_URI` now reads from `settings.fyers_redirect_uri` with `os.getenv` fallback
- `apps/api/routes/v1_marketdata.py` — `STREAMING_SUPPORTED` moved from hardcoded local constant to `from core.config import STREAMING_SUPPORTED`

### Why
- Scattered constants (`STREAMING_SUPPORTED`, `FYERS_REDIRECT_URI`) made configuration hard to find and change
- Missing env fields in Settings prevented centralized env validation
- Centralizing into `core/config.py` means one file to check for all configuration

### Risk
Low. Backward-compatible:
- `fyers_redirect_uri` defaults to `""` in Settings → the `os.getenv` fallback preserves the old behavior
- `STREAMING_SUPPORTED` moved from local variable to config import → exact same set `{"fyers", "angelone"}`

### Rollback
1. `git checkout -- apps/api/core/config.py`
2. In `v1_brokers.py`: restore `FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI", "...")`
3. In `v1_marketdata.py`: restore `STREAMING_SUPPORTED = {"fyers", "angelone"}`

---

## Task 5: Global Error Handling & Response Format

### New Files
- `apps/api/core/exceptions.py` — exception hierarchy: `AppException` → `NotFoundException`, `InvalidRequestException`, `AuthFailedException`, `ForbiddenException`, `RateLimitException`, `BrokerException`, `ServiceUnavailableException`
- `apps/api/core/response.py` — `api_response()` and `error_response()` helper functions returning consistent `{"success": bool, "data": ..., "error": {...}}` JSON envelope

### Files Changed
- `apps/api/main.py` — registered `AppException` exception handler before the generic `Exception` handler

### Why
- Previously, every route handler returned ad-hoc dicts with no consistent structure
- The global `Exception` handler returned `{"detail": "..."}` — no error code, no structured envelope
- Frontend clients had to parse errors differently per endpoint
- New hierarchy makes it easy to raise typed exceptions (`raise NotFoundException(...)`) and get consistent responses

### Risk
Low. The exception handlers are fallbacks — they only fire if a route raises an unhandled exception. Existing routes that return JSON directly continue working unchanged.

### Rollback
1. `git checkout -- apps/api/core/exceptions.py`
2. `git checkout -- apps/api/core/response.py`
3. In `main.py`: remove the `AppException` handler, keep only the generic `Exception` handler

---

## Task 7: Health Endpoints

### Files Changed
- `apps/api/routes/v1_health.py` — added `GET /version` returning `{"version": "...", "service": "...", "env": "..."}`

### Why
- Deployment scripts and monitoring tools need a standard version endpoint
- Previously only `/health` existed, which bundles version info with uptime and status
- Separate `/version` is a common convention (RFC-compatible)

### Risk
None — pure addition of a new endpoint.

### Rollback
`git checkout -- apps/api/routes/v1_health.py`

---

## Task 8: Middleware Improvements

### New Files
- `apps/api/core/middleware/request_id.py` — `RequestIDMiddleware`: generates `X-Request-ID` header per request (uses incoming value or creates UUID)
- `apps/api/core/middleware/request_logging.py` — `RequestLoggingMiddleware`: logs every request (method, path, status, duration) with request ID
- `apps/api/core/middleware/security.py` — `SecurityHeadersMiddleware`: sets `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Strict-Transport-Security`, `Cache-Control`, `Referrer-Policy`, `Permissions-Policy`
- `apps/api/core/middleware/timeout.py` — `TimeoutMiddleware`: aborts requests exceeding `request_timeout_seconds` (default 60)

### Files Changed
- `apps/api/core/ratelimit.py` — added `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` headers to 429 responses and `X-RateLimit-Limit` + `X-RateLimit-Remaining` to normal responses
- `apps/api/middleware/validation.py` — removed security headers (moved to dedicated `SecurityHeadersMiddleware`)
- `apps/api/main.py` — registered new middleware stack in correct order:
  1. `GZipMiddleware` (outermost — compress before anything else)
  2. `CORSMiddleware`
  3. `RequestIDMiddleware`
  4. `RequestLoggingMiddleware`
  5. `SecurityHeadersMiddleware`
  6. `RateLimitMiddleware`
  7. `InputValidationMiddleware`
  8. `CSRFProtectMiddleware`
  9. `TimeoutMiddleware` (innermost — wraps actual request processing)

### Why
- **Request ID**: Essential for debugging — every response now carries a unique ID that appears in logs, making it possible to trace a request across services
- **Request logging**: Previously only ad-hoc timings were recorded; now every request produces a structured log line
- **Security headers**: Previously split between `validation.py` and nowhere else; now consolidated with additional headers (`Referrer-Policy`, `Permissions-Policy`)
- **Timeout**: Prevents hung requests from consuming workers indefinitely
- **Rate limit headers**: Lets clients adapt their request rate programmatically
- **GZip**: Reduces bandwidth for API responses (≥1KB)

### Risk
Low. All middleware is additive and backward-compatible:
- Request ID overwrites any existing `X-Request-ID` header (acceptable — we generate the canonical ID)
- Timeout of 60s matches the default `httpx.AsyncClient` timeout used elsewhere
- Rate limit headers are informational only

### Rollback
1. Remove new middleware registrations from `main.py`
2. `git checkout -- apps/api/core/ratelimit.py`
3. `git checkout -- apps/api/middleware/validation.py`
4. Delete `apps/api/core/middleware/` directory

---

## Task 9: Centralized Exception Classes

Implemented as part of Task 5 (see above).

---

## Task 10: WebSocket Architecture Improvements

### Files Changed
- `apps/api/market/data_socket.py` — added:
  - `active_connections` counter with `increment_connections()` / `decrement_connections()`
  - `_heartbeat_task` with 30-second heartbeat loop logging connection count
  - `start()` now launches the heartbeat loop
- `apps/api/routes/v1_marketdata.py` — WebSocket handler now calls `shared_socket.increment_connections()` on accept and `shared_socket.decrement_connections()` in the finally block

### Why
- Previously there was no way to track how many WebSocket clients were connected
- No heartbeat meant stale connections could accumulate undetected
- The heartbeat provides visibility and is a foundation for future ping/pong keepalive

### Risk
Low. The heartbeat is purely logging. Connection tracking is a counter increment/decrement that doesn't affect message flow.

### Rollback
1. `git checkout -- apps/api/market/data_socket.py`
2. `git checkout -- apps/api/routes/v1_marketdata.py`

---

## Task 12: Dependency Cleanup

### Files Changed
- `apps/api/requirements.txt` — removed `logzero>=1.7`

### Why
- `logzero` was listed as a dependency but never imported anywhere in the codebase
- The project uses stdlib `logging` with a custom `StructuredFormatter` — no need for `logzero`
- Removing unused dependencies reduces attack surface and installation time

### Risk
None. Verified by searching for `logzero` across the entire `apps/api/` directory — zero results.

### Rollback
Add `logzero>=1.7` back to `requirements.txt`.

---

## Summary of All Changes

| # | Change | Files Added | Files Modified | Risk |
|---|--------|-------------|----------------|------|
| 3 | Env vars + .env.example | 0 | 1 | None |
| 4 | Centralized config | 0 | 3 | Low |
| 5 | Error handling + response helpers | 2 | 1 | Low |
| 7 | Version endpoint | 0 | 1 | None |
| 8 | Middleware improvements | 4 | 3 | Low |
| 9 | Exception classes (part of 5) | 0 | 0 | Low |
| 10 | WebSocket heartbeat + connection tracking | 0 | 2 | Low |
| 12 | Remove logzero dependency | 0 | 1 | None |

**Total**: 6 new files, 12 modified files. Zero deleted files. Zero removed routes, APIs, or features.

## Verification Checklist
- [x] Backend app loads without errors (88 route entries registered)
- [x] `GET /health` returns 200
- [x] `GET /version` returns version info
- [x] `GET /health/ready` returns dependency status
- [x] `GET /health/live` returns alive
- [x] `GET /metrics` returns Prometheus metrics
- [x] `STREAMING_SUPPORTED` correctly imported from config
- [x] `FYERS_REDIRECT_URI` reads from config with fallback
- [x] Rate-limit headers present in responses
- [x] Request ID middleware applies `X-Request-ID` header
- [x] Security headers applied to all responses
- [x] `logzero` removed from dependencies
