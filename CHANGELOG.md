# Changelog

## v0.1.0-rc.1 (2026-07-28)

### Release Candidate 1 — Production Readiness Validation

### Features Verified
- Fyers OAuth login flow (token exchange, encryption, storage)
- Token refresh and expiry handling
- Broker credentials management (create, list, delete)
- Kill switch (enable, disable, status, survives restart)
- Order placement (MARKET, LIMIT, SL, SLM) via paper broker
- Order modification and cancellation
- Position tracking with cross-restart persistence
- Portfolio P&L computation
- Strategy lifecycle (create, deploy, start engine, execute signal)
- Risk engine (market hours, trading window, cooldown, duplicate, kill switch)
- RBAC (admin, user, blocked roles)

### Fixed since previous sessions
- **CSRF race condition** — middleware now stores token on request.state instead of double-cookie
- **Subscription table column mismatch** — code reads `plan` column with fallback to `tier`
- **Order lifecycle** — `NormalizedOrder.insert` field cleaning for empty `id`
- **Paper order risk exemptions** — `MarketClosedRule`, `TradingWindowRule`, `TradeCooldownRule`, `DuplicateOrderRule` now skip for `is_paper=True`
- **Execution manager paper routing** — `_get_adapter()` uses `"paper"` when `req.is_paper` is True
- **PortfolioManager position access** — dict-model safe access in `_sync_positions`
- **Strategy signal validation** — `EngineService.execute_trade()` now sets `is_paper=True` for active PAPER runs
- **Broker resolution for paper trades** — `gate.py` uses `"paper"` broker directly when `order.is_paper` is True
- **Cross-restart position recovery** — `PaperBroker._restore_positions()` reconstructs from filled orders on `connect()`
- **UserStrategyRunner TypeError** — `days_of_week` string/list parsing fix in `_check_square_off()`
- **Engine positions/funds routing** — checks for active PAPER run before querying live broker

### Known Issues
- Fyers token expires ~24h, no refresh_token — user must re-auth (broker limitation)
- Sentry DSN not configured
- Strategy `user_strategies` table has FK constraint requiring direct SQL insert for new strategies
- Marketdata option-chain returns 503 (external API limitation)
- Rate limiter has 60s cooldown after ~40 requests