# TradeMetrix Terminal — Full Audit Report
# Generated: 2026-09-16 | Auditor: Hermes Agent (Solar Pro4)
# Project: /Users/aakib/trademetrix-terminal
# Live site: https://ai.trademetrix.tech | API: https://api.ai.trademetrix.tech

## EXECUTIVE SUMMARY

**Project**: Automated trading terminal — FastAPI backend + Next.js frontend, multi-broker support, Supabase DB, Redis, Telegram alerts.

**Overall Health**: The project has a **strong test foundation** (1029 passing tests) and has been through extensive production hardening (AGENTS.md documents 100+ fix sessions). However, there are **critical issues that prevent reliable live trading right now**.

**Risk Rating**: HIGH — multiple blocking issues for production live trading.

---

## PART 1: CRITICAL ISSUES (MUST FIX BEFORE LIVE TRADING)

### C1. Hardcoded Production Credentials (CRITICAL — IMMEDIATE ACTION)
**File**: `/Users/aakib/trademetrix-terminal/test_live_pipeline.py`

- Line 15: `"email": "Aakibkhn2@gmail.com"` — real production email
- Line 15: `"password": "Aakibkhan1@23"` — real production password

**Impact**: Anyone with access to this codebase or its git history can log into your production account. If this file is ever committed (even accidentally), credentials are leaked forever in git history.

**Fix**: Remove credentials. Use environment variables, prompts, or a secure vault. If already committed, rotate the password immediately and squash the git history.

---

### C2. Fyers Broker Token Expired (BLOCKS LIVE TRADING)
**Source**: KNOWN_ISSUES.md #1, INC-016, AGENTS.md

- Fyers access tokens last ~30 days and cannot be silently refreshed.
- The production token is EXPIRED.
- Auto-refresh cron is NOT re-validating this cycle.
- **Everything degrades gracefully** (backtests, index data via Yahoo) but **live order placement via Fyers fails**.
- Fix: User must re-authenticate via `/v1/brokers/fyers/re-auth` on the production API.

**Verification**: `curl -X POST https://api.ai.trademetrix.tech/api/v1/brokers/fyers/re-auth ...` (requires valid session).

---

### C3. Global Kill Switch Was ENABLED (BLOCKS ALL TRADING)
**Source**: AGENTS.md v1.7.0 entry, INC-015

- `global:kill_switch` Redis key was set to `"1"` (ENABLED) at last documented check.
- When enabled, `dispatch_signal()` in the execution engine returns immediately — **no orders are placed for anyone**.
- Fix: Admin must disable via `/api/v1/risk/kill-switch/disable` or `redis-cli DEL global:kill_switch`.

**Verification**: `docker exec trademetrix_redis redis-cli GET global:kill_switch` on VPS.

---

### C4. Disabled Risk Guards in broker_connect Engine (HIGH RISK)
**File**: `/Users/aakib/trademetrix-terminal/apps/api/broker_connect/execution/riskguard.py`, lines 63-69

The following risk checks are COMMENTED OUT:

```python
# today_pnl = await pnl_store.today(profile.user_id)
# if rk.get("max_daily_loss") and today_pnl <= -float(rk["max_daily_loss"]):
#     return False, "max_daily_loss_hit"
# open_pos = await positions.count(profile.user_id)
# if rk.get("max_open_positions") and open_pos >= int(rk["max_open_positions"]):
#     return False, "max_open_positions"
```

**Impact**: Daily loss limits and max position counts are NOT enforced in the broker_connect execution engine. A runaway strategy could lose unlimited money or open unlimited positions.

**Note**: The legacy engine (`engine/riskguard.py`, `risk/riskguard.py`) appears to have these guards active. But the broker_connect engine — which is documented as the "new" engine — has them disabled.

**Fix**: Uncomment and wire up the pnl_store and positions count dependencies.

---

### C5. Dual/Confused Execution Engine Architecture (HIGH RISK)
**Finding from full codebase scan**:

| Engine | Files | Lines | Status |
|--------|-------|-------|--------|
| Legacy `engine/` (engine.executor) | 27 files | ~5,589 | **ACTIVE** — wired into `routes/v1_engine.py`, `routes/v1_paper.py` |
| `execution_engine/` | 12 files | ~2,811 | Partially wired into lifespan |
| `broker_connect/execution/` | 32 files | ~2,408 | **DEAD CODE** — exists but NOT wired into any route |
| `strategy_runtime/` | 13 files | ~2,560 | Active for auto-trading signal dispatch |

**Impact**: Two competing execution engines (legacy vs broker_connect) creates confusion about which one is authoritative. The broker_connect engine has TODO'd risk guards (C4), suggesting it's not production-ready. The legacy engine is what's actually running.

**Recommendation**: Converge on one engine. The legacy engine appears to be the production path. Either complete the broker_connect migration OR deprecate it.

---

### C6. yfinance as Primary Fallback for Market Data (RELIABILITY RISK)
**File**: `/Users/aakib/trademetrix-terminal/apps/api/providers/yahoo.py`

- Uses `yfinance` (unofficial, unreliable) as fallback for all market data.
- Throttling is a known issue (KNOWN_ISSUES #13).
- TzCache warnings in container (can't write cache dir).
- No robust retry/backoff beyond basic try/except.
- Historical data for bare symbols (NIFTY50-INDEX without exchange prefix) was a source of 43 production 500 errors (fixed in v1.7.3, but the underlying yfinance dependency remains fragile).

**Impact**: Market data gaps during high-frequency periods or when Yahoo throttles. Not suitable for mission-critical live trading without a reliable primary data source (broker APIs).

---

### C7. Telegram and Sentry Not Configured in Production
**Source**: KNOWN_ISSUES.md #4, #5

- `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` unset → watchdog logs "[DEV] No Telegram configured" stubs.
- `SENTRY_DSN` not set → errors only visible via logs + Prometheus/Grafana.
- **Impact**: No real-time alerting when things break in production. Ops must monitor Grafana manually.

---

### C8. 11 Failed Tests + 20 Errors in Test Suite
**Test run**: `pytest tests/` — 11 failed, 20 errors, 1029 passed, 1 xfailed.

**Failed test**:
- `test_max_daily_trades_blocks_patiently` — assertion `0 >= 1` failed. Root cause: `strategy_runs` row for `sr-a-000001` fails with `invalid input syntax for type uuid: "sr-a-000001"` (22P02). The test uses fake UUIDs that don't match the DB schema.

**20 Errors** (all in `test_buyer_strategies.py::TestBuyerBase`):
- `TypeError: Can't instantiate abstract class _T without an implementation for abstract method '_on_15m'`
- These are test infrastructure issues — the test creates a concrete subclass of `BuyerBase` but doesn't implement the required abstract methods. Not a production bug, but indicates the test suite needs maintenance.

---

## PART 2: ROUTE CONFLICTS (MEDIUM RISK)

Several API endpoint paths are defined in **multiple route files**, creating ambiguity about which handler wins when FastAPI registers them:

| Path | Files |
|------|-------|
| `/` | v1_alerts.py, v1_backtest.py, v1_margin_estimate.py, v1_orders.py, v1_strategies.py, v1_user_strategies.py |
| `/activate` | v1_brokers.py, v1_buyer_strategies.py |
| `/historical` | v1_market.py, v1_marketdata.py |
| `/instruments` | v1_market.py, v1_marketdata.py |
| `/option-chain` | v1_market.py, v1_marketdata.py |
| `/kill-switch` | v1_admin.py, v1_risk.py |
| `/orders` | v1_admin.py, v1_engine.py |
| `/positions` | v1_admin.py, v1_engine.py, v1_paper.py |
| `/status` | 6 different files |
| `/strategies` | 5 different files |

**Impact**: FastAPI's behavior when the same path is registered twice depends on registration order. The last registered route wins. This can cause silent regressions when route files are reordered or new routes are added. Some of these may be intentional (different prefixes), but the `/` conflict is concerning — 6 files claim the root path.

**Recommendation**: Audit each conflict. Ensure only one handler per path, or use distinct prefixes.

---

## PART 3: CODE QUALITY FINDINGS

### 3.1 No Syntax Errors
All 433 Python files pass `compile()` — no syntax errors in the codebase.

### 3.2 Module Imports Clean
Core modules (`core.config`, `core.cache`, `core.exceptions`, `middleware.csrf`, `routes.v1_health`, `routes.v1_auth`, `routes.v1_risk`, `broker_connect.execution.engine`, `execution_engine.init`) all import successfully.

### 3.3 CSRF Implementation Looks Solid
- Uses `secrets.token_hex(32)` for token generation.
- Uses `secrets.compare_digest()` for timing-safe comparison.
- Cookie + header dual delivery.
- FIXED in INC-001 and INC-013 (production deployment gap).

### 3.4 TypeScript Frontend
- 773 TS/TSX files, no `tsc --noEmit` errors.
- CSRF bootstrap implemented in `lib/api.ts` with eager fetch on module load.
- Live dashboard (`/live`) has proper auth gate, SSE feed, market status polling.

### 3.5 No SQL Injection Vectors Found
- Only one f-string SQL found: `test_live_pipeline.py:199` (DELETE FROM auth.users WHERE id = '...') — in test code only.
- All production queries appear to use parameterized Supabase clients.

### 3.6 No Unsafe Deserialization
- No `pickle.load` in production code.
- `ast.literal_eval` used in `core/config.py:86` (safe).

---

## PART 4: WHAT'S WORKING WELL

1. **Extensive test coverage**: 1029 tests passing, covering auth, brokers, kill switch, auto-trading, engine service, risk, backtest, etc.

2. **Production hardening documented**: AGENTS.md records 100+ fix sessions with root causes, fixes, and verification.

3. **Kill switch mechanism**: Both global and per-user kill switches implemented with Redis backend. Restart-safe emergency state persistence (INC-015 fix).

4. **Token expiry handling**: Structured `BROKER_TOKEN_EXPIRED` errors (401) instead of raw 500s (INC-016 fix).

5. **Paper trading mode**: Works end-to-end, positions restored across restarts (INC-004 fix).

6. **CSRF protection**: Properly implemented with timing-safe comparison (INC-001, INC-011, INC-013 fixes).

7. **Deployment pipeline**: Single-command deploy with health gates, rollback procedure documented.

8. **Multi-broker support**: 15+ broker adapters (Fyers, Angel One, Upstox, Zerodha, Dhan, Kotak Neo, Groww, Alice Blue, FivePaisa, Finvasia, FlatTrade, Lemonn scaffold).

9. **Backtest engine**: 5-year windows, 10 curated strategies, real data only (no synthetic fallback).

10. **Frontend**: Next.js 14, live dashboard, trader workspace for index options, backtest UI, strategy builder.

---

## PART 5: RECOMMENDED FIX PRIORITY

### IMMEDIATE (before any live trading)
1. **Remove hardcoded credentials from test_live_pipeline.py** — rotate password if already committed
2. **Re-authenticate Fyers broker** on production — live orders are blocked
3. **Disable global kill switch** on production — trading is halted
4. **Enable risk guards** in broker_connect/riskguard.py (or confirm legacy engine is the authority)

### SHORT TERM (this week)
5. **Resolve dual-engine confusion** — pick one execution engine as authoritative
6. **Fix route conflicts** — audit the `/` and other multi-file path conflicts
7. **Configure Telegram + Sentry** in production for alerting
8. **Fix the 11 failing tests** — at minimum the `test_max_daily_trades_blocks_patiently` UUID issue

### MEDIUM TERM (this month)
9. **Replace yfinance fallback** with a more reliable market data source for critical paths
10. **Audit broker_connect engine** — either complete it or deprecate it
11. **Add rate limiting per-user** for market data endpoints (currently global only)
12. **Set up off-host backups** for VPS data (KNOWN_ISSUES #8)

---

## PART 6: BLOCKERS FOR "FULLY WORKING LIVE TRADING TOOL"

For this to be a fully working live trading tool **right now**, the following must be true:

| Requirement | Status |
|-------------|--------|
| Production API reachable and healthy | Unknown (can't test from this session) |
| At least one broker connected with valid token | ❌ Fyers token expired |
| Kill switch disabled | ❌ Was enabled at last check |
| Risk guards active (daily loss, max positions) | ❌ Commented out in broker_connect engine |
| Market data working (indices, stocks, options) | ⚠️ Degrades to yfinance (unreliable) |
| No hardcoded credentials in codebase | ❌ test_live_pipeline.py |
| Test suite green | ⚠️ 11 failed, 20 errors |
| Alerting configured (Telegram/Sentry) | ❌ Not configured |
| No route conflicts | ⚠️ Multiple path conflicts |

**Bottom line**: The project is a substantial, well-tested trading platform that has been through extensive hardening. But in its current state, **live trading is not safe** — the kill switch may be on, the broker token is expired, risk guards are disabled in one engine, and credentials are leaked in a test file.

---

*End of audit report.*
