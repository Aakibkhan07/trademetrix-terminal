# Missing Features & Gaps

## Critical Gaps

### 1. No Test Suite
- **Location**: Entire project
- **Severity**: HIGH
- **Description**: Zero unit tests, integration tests, or E2E tests exist for any module (API routes, broker adapters, market engine, frontend components).
- **Impact**: Every deployment is a leap of faith. Regressions cannot be caught automatically.
- **Recommendation**: Start with pytest for API routes (using TestClient), then add broker adapter tests with mocked HTTP responses.

### 2. Dhan & Upstox OAuth Flows Missing
- **Location**: `apps/api/brokers/dhan_adapter.py`, `apps/api/brokers/upstox_adapter.py`
- **Severity**: HIGH
- **Description**: Both adapters accept `access_token` directly but have no OAuth authorization flow. Users cannot connect these brokers through the UI.
- **Impact**: 2 of 10 supported brokers are effectively unusable through the portal.
- **Recommendation**: Implement OAuth redirect flow matching the patterns in `fyers_adapter.py`.

### 3. AliceBlue, Finvasia, FlatTrade, KotakNeo `stream()` Untested
- **Location**: `apps/api/brokers/aliceblue_adapter.py`, `finvasia_adapter.py`, `flattrade_adapter.py`, `kotakneo_adapter.py`
- **Severity**: HIGH
- **Description**: These adapters implement the `stream()` interface but have never been validated against live broker APIs. KotakNeo's WebSocket subscription was fixed, but never tested end-to-end.
- **Impact**: May crash silently or produce no data when used with real credentials.
- **Recommendation**: Test each adapter with live credentials. Add error logging and graceful degradation.

---

## Important Gaps

### 4. No Pagination / Infinite Scroll
- **Location**: All data tables in portal + admin
- **Severity**: MEDIUM
- **Description**: Orders, positions, trades, and audit log tables load all data at once. Will become unusable with 1000+ rows.
- **Recommendation**: Add server-side pagination to list endpoints (`?page=1&per_page=50`), update frontend tables to use pagination controls.

### 5. No WebSocket Reconnection Backoff
- **Location**: `apps/web/lib/use-market-data.tsx`
- **Severity**: MEDIUM
- **Description**: On WS disconnect, the hook attempts immediate reconnection. Could cause reconnection storms on network flapping.
- **Recommendation**: Implement exponential backoff: 1s → 2s → 4s → 8s → max 30s, reset on successful connection.

### 6. Simulator Price Drift (No Mean Reversion)
- **Location**: `apps/api/market/simulator.py`
- **Severity**: MEDIUM
- **Description**: Gaussian random walk without mean reversion. Prices can drift to unrealistic levels over hours/days.
- **Recommendation**: Add Ornstein-Uhlenbeck process (mean-reverting random walk) with configurable reversion strength.

### 7. No Alert Persistence on Restart
- **Location**: `apps/api/market/alert_checker.py`
- **Severity**: MEDIUM
- **Description**: AlertChecker is in-memory. API restart requires manual `feed/start` call to resume alert monitoring.
- **Recommendation**: Auto-start alert checker on API startup (read active alerts from DB). Or add startup lifecycle hook.

### 8. Jinja2 Admin Template vs. Next.js Admin Page (Duplicate)
- **Location**: `apps/api/templates/admin.html` vs `apps/web/app/admin/page.tsx`
- **Severity**: LOW
- **Description**: Two separate admin UIs exist. The Jinja2 template is served at `/admin` by FastAPI directly, while Next.js handles `/admin` routing. Likely one is unused.
- **Recommendation**: Determine which is in active use. Remove the unused one to prevent confusion. If the FastAPI route for the Jinja2 template still exists, it could conflict with Next.js routing.

---

## Nice-to-Have Gaps

### 9. No SEO / Sitemap / Robots.txt
- **Location**: Marketing site (`apps/web/app/page.tsx`)
- **Severity**: LOW
- **Description**: Marketing landing page has no meta tags, Open Graph data, sitemap.xml, or robots.txt.
- **Recommendation**: Add next-seo metadata, generate sitemap.xml, add robots.txt.

### 10. No Order Modification / Cancellation UI
- **Location**: Portal orders tab
- **Severity**: LOW
- **Description**: Orders can be placed but not modified or cancelled from the UI.
- **Recommendation**: Add modify/cancel buttons to open orders table. Backend endpoints already exist in broker adapters.

### 11. No Multi-User Alert Sharing
- **Location**: `apps/api/routes/v1_alerts.py`
- **Severity**: LOW
- **Description**: Alerts are per-user. No way for admin to set alerts for all users.
- **Recommendation**: Add `scope` field to alerts (personal/broadcast). Admin-created broadcast alerts fire for all users.

### 12. No Two-Factor Authentication
- **Location**: Auth system
- **Severity**: LOW
- **Description**: OTP-based login is single-factor (email + OTP). No TOTP or hardware key support.
- **Recommendation**: Add TOTP as optional second factor for admin accounts.

### 13. No API Key Management for Programmatic Access
- **Location**: Entire project
- **Severity**: LOW
- **Description**: No way for users to generate API keys for programmatic trading (algorithmic / script-based).
- **Recommendation**: Add API key generation UI + header-based auth middleware.

### 14. No Rate Limit Status Headers
- **Location**: `apps/api/core/ratelimit.py`
- **Severity**: LOW
- **Description**: Rate limiter doesn't return `X-RateLimit-Remaining` or `X-RateLimit-Reset` headers. Clients can't adapt their request rate.
- **Recommendation**: Add standard rate limit headers to responses.

### 15. No Graceful Degradation for Broker Timeouts
- **Location**: All broker adapters
- **Severity**: LOW
- **Description**: If a broker API times out, the adapter raises an exception that propagates up. No retry logic or circuit breaker.
- **Recommendation**: Add retry with backoff (2 attempts) and timeout config per adapter.
