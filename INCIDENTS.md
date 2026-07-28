# Production Incidents Log

## INC-001: CSRF Race Condition (2026-07-27)

**Severity:** Critical  
**Status:** Resolved  
**Root Cause:** CSRF middleware set cookie and header independently; on concurrent requests the token from cookie could differ from header, causing 403 on state-modifying requests.  
**Fix:** Route handler stores token on `request.state.csrf_token`, middleware reads from state and sets both cookie + header on every response.  
**Files Changed:** `apps/api/middleware/csrf.py`  
**Verification:** 98/98 PAT pass, all state-modifying operations succeed.

## INC-002: Subscription Table Column Mismatch (2026-07-27)

**Severity:** High  
**Status:** Resolved  
**Root Cause:** Init migration creates `subscriptions` with `plan` column; later migration creates same table with `tier` column (no-op due to `IF NOT EXISTS`). Code expected `tier`.  
**Fix:** Code reads `plan` column with fallback to `tier`.  
**Files Changed:** `apps/api/core/capabilities.py`, `apps/api/application/services/subscription_service.py`  
**Verification:** Subscription endpoint returns correct tier data.

## INC-003: Order Lifecycle Validation Failure for Paper Trades (2026-07-28)

**Severity:** Critical  
**Status:** Resolved  
**Root Cause:** `place_order()` via `/engine/trade` created `NormalizedOrder` without `is_paper=True`. Gate resolved broker from `broker_credentials` (Fyers), not the active PAPER run. Risk validation then rejected with "Validation failed" due to market-hours check.  
**Fix:** 
- `EngineService.execute_trade()` queries `strategy_runs` for active PAPER run → sets `is_paper=True`
- `gate.py execute_order()` checks `order.is_paper` before resolving broker, uses "paper" directly  
**Files Changed:** `apps/api/application/services/engine_service.py`, `apps/api/engine/gate.py`  
**Verification:** Signal → FILLED (broker="paper", is_paper=true, filled_qty=10). 98/98 PAT pass.

## INC-004: Positions Lost After Server Restart (2026-07-28)

**Severity:** High  
**Status:** Resolved  
**Root Cause:** Three layers:
1. `EngineService.get_positions()` resolved broker from `broker_credentials` (Fyers), but paper positions stored under broker="paper" in PortfolioManager  
2. PaperBroker's `_positions` dict was in-memory only; lost on restart  
3. `positions_snapshot` table never written for paper broker  
**Fix:**
- `get_positions()`/`get_funds()` now check for active PAPER run and route to PortfolioManager
- `PaperBroker.connect()` calls `_restore_positions()` from orders table  
**Files Changed:** `apps/api/application/services/engine_service.py`, `apps/api/paper/paper_broker.py`
**Verification:** TCS position (qty=80) restored across restart from 7 filled orders. 98/98 PAT pass.

## INC-005: UserStrategyRunner TypeError (2026-07-28)

**Severity:** Low  
**Status:** Resolved  
**Root Cause:** `current_dow not in days_of_week` raised TypeError when `days_of_week` stored as string in DB (not list).  
**Fix:** Type-safe parsing for both string and list formats.  
**Files Changed:** `apps/api/engine/user_strategy_runner.py`  
**Verification:** No TypeError in logs. 98/98 PAT pass.

## INC-006: GET /api/v1/admin/stats Returns 404 (2026-07-28)

**Severity:** Medium  
**Status:** Resolved  
**Root Cause:** `AdminService.get_stats()` was implemented but the HTTP route `@router.get("/stats")` was never registered in `v1_admin.py`. Frontend API lib called `api.admin.stats()` → `GET /api/v1/admin/stats` → 404.  
**Fix:** Registered `GET /admin/stats` route in `v1_admin.py` calling `AdminService.get_stats()`.  
**Files Changed:** `apps/api/routes/v1_admin.py`, `apps/api/tests/test_admin_service.py`  
**Verification:** Route confirmed registered via test. `GET /api/v1/admin/stats` now returns stats payload.