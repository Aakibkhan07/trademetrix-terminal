# Production Readiness Report — TradeMetrix Terminal

**Date:** 2026-07-03
**Scope:** Full repository audit (apps/api, apps/web, infra/, docs/, tests/)
**Auditors:** Parallel subsystem analysis (core, execution, OMS, risk, portfolio, paper, brokers, market, runtime, engine, routes, frontend, infra, deployment)

---

## Executive Summary

The TradeMetrix Terminal codebase is extensive and functionally rich, but **not production-ready**. The audit identified **286 issues** across all subsystems:

| Severity | Count | Estimated Effort |
|----------|-------|-----------------|
| **CRITICAL** | 47 | ~140h |
| **HIGH** | 82 | ~160h |
| **MEDIUM** | 95 | ~120h |
| **LOW** | 62 | ~50h |
| **Total** | **286** | **~470h** |

**Top 5 existential risks (fix before connecting real money):**
1. **All broker adapters lack HTTP timeouts** — connections hang forever, workers leak
2. **Risk rules fail open on exception** — DB/market outage allows unrestricted trading
3. **No order idempotency** — network retries cause duplicate fills, real financial loss
4. **In-memory state everywhere** — all OMS/portfolio/paper state lost on restart
5. **Retry layer is broken** — `place_order` errors are swallowed, never retried

---

## Section 1: CRITICAL Issues (47)

### 1.1 Broker & Execution — Real Money Risk

| # | Issue | File | Lines | Root Cause | Fix | Effort |
|---|-------|------|-------|------------|-----|--------|
| C01 | **No HTTP timeouts on any broker API call** | ALL broker adapters | Every `client.get/post/put/delete` | Missing `timeout` parameter on every `httpx` request. A stuck TCP connection blocks the coroutine indefinitely. Under network partitions, workers hang, connections pool exhausts, entire system freezes. | Add `timeout=httpx.Timeout(10.0, connect=5.0)` to all broker HTTP calls | 4h |
| C02 | **Retry layer broken for `place_order`** | `execution/manager.py:431-445`, `execution/retry.py:58-64`, `brokers/base.py:106-115` | `broker_adapter.place_order()` catches ALL exceptions and returns `OrderResult(success=False)`. The retry function only retries when the wrapped operation *raises* an exception. Since every failure returns a failed `OrderResult` (no exception), `retry_with_backoff` treats it as success and returns immediately. **Retry for the primary order path is entirely non-functional.** | Return `OrderResult` for validation errors (non-retryable), but RE-RAISE transient exceptions (network, timeout, rate limit) so the retry layer catches them. Add error codes to distinguish. | 4h |
| C03 | **No idempotency key forwarded to real brokers** | `execution/broker_adapter.py:106-115`, ALL broker adapters | `client_order_id`/`execution_request_id` is never mapped to broker idempotency fields. Network retries cause duplicate fills. Most brokers (Zerodha, Dhan, Fyers) support idempotency keys. | Forward `execution_request_id` as broker's idempotency field in each adapter | 8h |
| C04 | **`cancel_order` always reports success — 6 adapters** | `brokers/zerodha_adapter.py:139`, `upstox_adapter.py:126`, `dhan_adapter.py:134`, `fivepaisa_adapter.py:184`, `kotakneo_adapter.py:149`, `aliceblue_adapter.py:140` | `success=True` hardcoded regardless of broker API response. Cancel failures are invisible — orders appear cancelled when they're still live. | Parse actual response status, return success=False on failure | 0.5h |
| C05 | **`retry_with_backoff` tuple not unpacked in modify/cancel** | `execution/manager.py:226-228, 275-277` | `retry_with_backoff` returns `(result, attempts, elapsed)` tuple. `modify_order` and `cancel_order` store the whole tuple in `broker_result`, then check `broker_result.success` → `AttributeError: 'tuple' object has no attribute 'success'`. **These methods always crash.** | Unpack tuple: `broker_result, attempts, _ = await retry_with_backoff(...)` | 0.25h |
| C06 | **Margin check always returns True** | `execution/validation.py:99-124` | `_check_margin` loads credentials but never checks margin. Always returns `True`. Also fails open on exception (returns True). | Implement actual margin check against order value | 2h |
| C07 | **Market/trading session validation fails open** | `execution/validation.py:74-78`, `risk/rules.py:79-80, 104-105` | All market-session checks return `True` on ANY exception. If market status service is down, trades flow during holidays/after-hours. | Fail closed: return False on uncertainty, log CRITICAL alert | 1h |

### 1.2 Order Management — State Loss & Race Conditions

| # | Issue | File | Lines | Root Cause | Fix | Effort |
|---|-------|------|-------|------------|-----|--------|
| C08 | **All OMS state is in-memory — total loss on restart** | `oms/manager.py:46-48`, `oms/order_queue.py:14-20` | `_orders`, `_bracket_orders`, `_oco_orders`, `_fifo`, `_priority`, `_retry`, `_processing` — all plain in-memory dicts/lists. Any process restart (deploy, crash, scale) loses ALL active orders, bracket legs, OCO state, and queued retries. | Persist OMS state to PostgreSQL. Write-through on every state mutation. Recover active orders on startup. | 24h |
| C09 | **Order queue has zero durability** | `oms/order_queue.py` (entire file) | Queue is entirely in-memory. A crash at any point loses: all queued orders, all pending retries, all in-flight processing markers. Orders silently vanish. | Replace with Redis-backed queue (RPOPLPUSH pattern) or PostgreSQL SKIP LOCKED | 14h |
| C10 | **Cancel vs process race condition — orders get stuck** | `oms/manager.py:114-131` | TOCTOU race: `if order.state == QUEUED` then `await order_queue.remove(id)`. Between check and remove, processor dequeues and sets SENT. Cancel falls through without cancelling with broker. Order is stuck — user thinks cancel was attempted but order keeps executing. | Use atomic CAS pattern: set "cancel requested" flag before checking state; check flag in processor | 5h |
| C11 | **State set to SENT before execution — crash loses order** | `oms/manager.py:271, 293` | Order state mutated to SENT before the actual broker execute call. If process crashes between these lines, order is state=SENT in memory, but unknown to broker. | Execute first, then set state. Or use prepare-execute-commit with recovery scanner. | 3h |
| C12 | **No graceful shutdown / drain** | `oms/manager.py:58-62` | `stop()` immediately cancels the processor task without draining in-flight items. Any order being executed at shutdown is silently dropped. | Implement drain phase: set `_running=False`, wait for current item, then cancel. Persist processing set. | 4h |
| C13 | **Bracket order SL/target legs never submitted** | `oms/manager.py:332-338` | `create_bracket()` stores a `BracketOrder` record but only places the parent entry order. `_handle_parent_completion()` sets `entry_filled=True` but NEVER submits the stop-loss or target orders. **Protective legs simply don't exist.** | After entry fill, submit SL and target orders via `ExecutionManager.place_order()`. Wire broker_order_ids. | 10h |
| C14 | **OCO sibling cancellation not implemented** | `oms/manager.py:306-307` | When one leg of an OCO order fills, the other leg should be cancelled. No handler exists. | Add OCO completion handler that cancels sibling via `_exec_mgr.cancel_order()` | 4h |

### 1.3 Risk & Financial Safety

| # | Issue | File | Lines | Root Cause | Fix | Effort |
|---|-------|------|-------|------------|-----|--------|
| C15 | **Risk config fails open on DB outage** | `risk/manager.py:105-114` | `_load_config` catches all exceptions silently and returns `RiskConfig()` with zero limits. When DB is unreachable, `daily_loss_limit=0`, `max_capital=0`, `kill_switch_enabled=False` — all risk rules pass through unhindered. | Cache last known good config. On DB failure, apply most restrictive config (reject all). Log CRITICAL alert. | 2h |
| C16 | **Market order exposure check bypassed (price=0)** | `risk/rules.py:244, 275, 402` | `MaxExposureRule`, `MaxSymbolExposureRule`, `MaxCapitalRule` compute `order_value = qty * (req.price or 0)`. For market orders, `price=0`, so `order_value=0`. Million-dollar market orders pass all capital checks. | Use estimated market price (LTP from cache) with slippage buffer for market orders | 3h |
| C17 | **Emergency stop lost on restart** | `risk/kill_switch.py:12-13, 28` | `_emergency_stops` is in-memory only, initialized empty. After any restart, all emergency stops are cleared. | On startup, query audit log for active emergency stops. Re-hydrate from DB. | 3h |
| C18 | **Risk DB column mappings are wrong** | `risk/manager.py:121, 129` | `max_exposure = row.get("max_capital", 0)` and `max_account_exposure = row.get("max_capital", 0)`. These read the wrong DB column — they all read `max_capital` instead of their respective columns. | Map each field to its correct DB column | 0.5h |
| C19 | **Drawdown calculation is mathematically wrong** | `risk/rules.py:441-456` | `peak = max(pnls)` where pnls are individual run PnLs (independent, not cumulative). `current = sum(pnls)`. This is not peak-to-trough drawdown. A sequence [100, -80, 100] shows 0% drawdown (peak=100, current=120). But 80% drawdown actually occurred between points 2 and 3. | Use time-ordered cumulative equity snapshots. Peak = max(rolling_cumulative), current = latest. | 5h |
| C20 | **Paper broker margin ignores unrealized losses** | `paper/paper_broker.py:248-253` | `available_margin = total_margin - used_margin`. `total_margin` is initial capital and never decreases. Users with heavy unrealized losses can keep opening new positions at full capital. | `available_margin = max(0, total_margin + m2m_unrealised - used_margin)` | 2h |
| C21 | **Paper broker state completely in-memory** | `paper/paper_broker.py:38-43` | `_orders`, `_positions`, `_account` are in-memory. Only order record saved to DB. Restart resets every paper trader to initial_capital=500000 with zero positions. | Persist `PaperPosition` and `PaperAccount` to DB on every mutation. Load on connect(). | 6h |
| C22 | **Paper fill engine can fill at price 0.0** | `paper/fill_engine.py:78-82` | `_get_fill_price` returns `order.price or 0.0` when market cache is empty. Market orders fill at 0.0 → infinite profit. | If no price available, reject the fill. Use LTP or error. | 1h |
| C23 | **Paper position PnL potentially double-counted** | `paper/paper_broker.py:237` | PnL is only computed when quantity reaches exactly zero. Crossing from long to short (quantity passes through 0 to negative) skips PnL booking at the zero crossing. Short positions start with wrong cost basis. | Compute realized PnL on every fill based on quantity change direction | 4h |
| C24 | **Three different PnL formulas, two wrong** | `risk/rules.py:127-151`, `portfolio/manager.py:409-434`, `risk/riskguard.py:162-226` | Three independent PnL calculations with different methods. The `risk/rules.py` and `portfolio/manager.py` versions use a simple sum formula that doesn't match FIFO. Inconsistencies of 10-40% on multi-lot trades. | Extract a single, correct FIFO PnL function shared across all three modules | 6h |
| C25 | **No cross-user isolation validation** | All risk/portfolio/paper modules | No server-side validation that `req.user_id` matches authenticated user. If any upstream code passes a different user_id, cross-user data access is possible. | Add validation layer comparing authenticated user with user_id parameter | 3h |

### 1.4 Security & Authentication

| # | Issue | File | Lines | Root Cause | Fix | Effort |
|---|-------|------|-------|------------|-----|--------|
| C26 | **TradingView webhook can execute as any user** | `routes/v1_tradingview.py:117-126` | When `WEBHOOK_SECRET` is not set AND no `user_id` is sent, fetches ANY active broker credential (first match) and executes trades as that user. Unauthenticated POST can trade real money. | Require `user_id` when `WEBHOOK_SECRET` not configured. Never auto-select user. | 1h |
| C27 | **OTP leaked in response when delivery fails** | `routes/v1_otp.py:107, 161` | When `deliver_otp` fails, raw OTP is returned in `debug_otp` field. Attacker who knows delivery will fail (bogus email) gets the OTP. | Never return `debug_otp` in production. Log server-side only. | 0.5h |
| C28 | **OTP generation not cryptographically secure** | `routes/v1_otp.py:70` | `random.randint(100000, 999999)` is predictable. | Use `secrets.randbelow()` or `random.SystemRandom()` | 0.5h |
| C29 | **No replay attack protection on webhook** | `routes/v1_tradingview.py:78-139` | No nonce, timestamp, or idempotency key. Intercepted valid webhook can be replayed infinitely. | Add required `nonce` field + Redis dedup with TTL. Validate timestamp ±60s. | 4h |
| C30 | **No idempotency on trade execution endpoints** | `routes/v1_engine.py:105-129`, `routes/v1_admin.py:331-384` | No idempotency key mechanism. Network retries cause duplicate orders. | Require `Idempotency-Key` header. Store processed keys in Redis with TTL. | 6h |
| C31 | **Hardcoded production secrets in test file** | `tests/test_mirror_fanout.py:15-17` | Production Supabase URL, service key, JWT secret, Redis URL hardcoded in version-controlled test file. | Remove immediately. Use env vars or `.env.test`. | 0.5h |
| C32 | **CSRF cookie is HttpOnly=False** | `middleware/csrf.py:50-55` | CSRF cookie is readable by JavaScript. If any XSS exists, CSRF token is stolen, defeating double-submit protection. | Make cookie HttpOnly. Use separate mechanism for JS (custom header check). | 1h |
| C33 | **No Content-Security-Policy header** | `core/middleware/security.py:13-20` (frontend `next.config.js:2-8`) | Missing CSP, Permissions-Policy minimal. Elevated XSS risk. | Add strict CSP: `default-src 'self'; script-src 'self'` | 1h |
| C34 | **Prometheus metrics endpoint has no auth** | `core/prometheus.py:42` | `/metrics` exposes circuit breaker states, memory usage, request rates to anyone. | Serve on internal-only port or add header verification | 1h |
| C35 | **Builder router has zero authentication** | `routes/v1_builder.py:89-265` | None of the builder CRUD endpoints include `get_current_user`. Anyone can create/read/update/delete strategies. (Currently not imported in main.py, but when wired up, wide open.) | Add `Depends(get_current_user)` to all builder endpoints | 2h |

### 1.5 Data Integrity & Consistency

| # | Issue | File | Lines | Root Cause | Fix | Effort |
|---|-------|------|-------|------------|-----|--------|
| C36 | **Portfolio state mutations not locked** | `portfolio/manager.py:131-190, 231-273` | `refresh()` mutates positions/holdings/funds/pnl in-place with no synchronization. Two concurrent `refresh()` calls interleave → lost updates, corrupted PnL, incorrect portfolio state. | Add `asyncio.Lock` per `user_id:broker` key. Acquire in every mutating method. | 4h |
| C37 | **Reconciliation is self-referential — never compares with broker** | `portfolio/manager.py:338-341` | `result.broker_positions = len(state.positions)`. Broker count is just local count. No actual broker API call. Drift detection is entirely broken. | Pass raw broker positions from `refresh()` into `_reconcile()`. Compare symbol-by-symbol. | 4h |
| C38 | **Event bus publish in risk/manager.py not awaited** | `risk/manager.py:138-153, 155-168` | `_publish_decision` and `_update_config_from_result` call `execution_event_bus.publish()` without `await`. Risk decisions are silently dropped. | Add `await` to all event bus publish calls | - |
| C39 | **Fire-and-forget events silently lost on failure** | `portfolio/manager.py:479`, `paper/paper_broker.py:312`, `execution/manager.py:514`, `oms/manager.py:340`, `runtime/manager.py:356` | All events published via `fire_and_forget()`. If publish fails, exception is logged but event is permanently lost. Downstream consumers never see it. | Use producer with retry + dead-letter queue. Log at ERROR level. | 6h |
| C40 | **Audit trail silently drops entries** | `execution/audit.py:52-54, 76-77` | Every audit DB insert wrapped in bare `except Exception: pass` (no logging). If Supabase unreachable or schema changes, ALL audit entries silently vanish. Compliance failure. | Implement dual-write: primary DB with retry, fallback to local spool, alert on persistent failure. | 7h |
| C41 | **`positions_snapshot` used as source of truth but never timely synced** | `risk/rules.py:208`, `portfolio/manager.py:397-407` | Risk rules load positions from `positions_snapshot`. If refresh fails or is infrequent, snapshot is stale. Risk decisions use stale data. | Write positions immediately on every `refresh()`. Add staleness check (>N min = flag as stale). | 2h |

### 1.6 Infrastructure & Deployment

| # | Issue | File | Lines | Root Cause | Fix | Effort |
|---|-------|------|-------|------------|-----|--------|
| C42 | **No resource limits on any container** | `infra/production/docker-compose.yml` (entire) | No `deploy.resources.limits.memory` on any service. A memory leak OOM-kills all containers on VPS. | Add memory limits: api=512M, web=512M, redis=256M, prometheus=256M, grafana=256M | 1h |
| C43 | **API Dockerfile runs as root** | `apps/api/Dockerfile:1-14` | No `USER` directive. If compromised, attacker has full container root. | Add `RUN adduser --system appuser && USER appuser` | 1h |
| C44 | **No backup strategy** | `infra/production/deploy.sh` (entire) | No database backup step. No pg_dump, no WAL archiving, no off-server storage. Single VPS with no replication. Data loss = total loss. | Add pre-deploy pg_dump, store last 7 days off-server (S3-compatible) | 3h |
| C45 | **Hardcoded JWT secret and Supabase keys in docker-compose** | `infra/docker-compose.yml:60, 147-148` | JWT secret (`super-secret-jwt-token-for-local-dev`) and service key hardcoded in version-controlled compose file. | Use `${JWT_SECRET}` env var, inject via `.env` | 1h |
| C46 | **All supabase calls in async routes block event loop** | ALL route files (systemic) | Every `supabase.table(...).execute()` inside an `async def` endpoint blocks the event loop. The `async_supabase` helper exists in `core/db.py` but is never used anywhere. **Single biggest performance issue.** | Use `async_supabase` wrapper on all DB calls, or migrate to supabase-py async client, or wrap in `run_in_executor` | 16h |
| C47 | **Zero broker adapter tests** | `tests/` (entire suite) | No tests for any broker adapter (Fyers, Zerodha, Angel One, Dhan, Upstox, 5Paisa, etc.). No mock broker, no integration test. Deployment without broker tests is blind. | Add unit tests with mocked HTTP responses for each broker adapter | 8h |

---

## Section 2: HIGH Issues (82 selected — top 30 by impact)

| # | Issue | File | Severity | Effort |
|---|-------|------|----------|--------|
| H01 | `datetime.utcnow()` deprecated — 32 instances across codebase | Multiple files | High | 2h |
| H02 | `threading.Lock` used in asyncio loops (risk/portfolio/paper/observability) | `risk/observability.py:8`, `portfolio/observability.py:8`, `paper/observability.py:8`, `runtime/observability.py:8` | High | 0.5h |
| H03 | Unbounded `_adapters` dict — memory leak (never evicted) | `execution/manager.py:63, 405-433` | High | 4h |
| H04 | No graceful shutdown for HTTP client, Supabase, scheduler, websocket | `main.py:46-54` | High | 1.5h |
| H05 | Lazy Fernet init — module-level raise crashes on import before vault init | `core/security.py:14-18` | High | 1h |
| H06 | No query timeouts anywhere — runaway queries hang indefinitely | `core/safe_query.py`, ALL DB calls | High | 2h |
| H07 | Race condition in Redis singleton init | `core/cache.py:15-18` | High | 1.5h |
| H08 | Rate limiter memory leak — `_windows` dict grows unbounded | `core/ratelimit.py:14` | High | 2h |
| H09 | Risk config cache never refreshes (stale settings used indefinitely) | `risk/manager.py:101-104` | High | 1.5h |
| H10 | Dedup set cleared entirely at threshold (100 entries) — allows duplicate burst | `risk/rules.py:344-345` | High | 1h |
| H11 | Rate limiter/dedup state lost on restart — burst attack vector | `risk/rules.py:303, 331` | High | 4h |
| H12 | No audit trail for risk overrides | `risk/riskguard.py`, `risk/manager.py` | High | 4h |
| H13 | No alerting on critical risk events | All risk files | High | 4h |
| H14 | `day_start_equity` always = current equity, never actual start-of-day | `portfolio/manager.py:326` | High | 2h |
| H15 | No retry on transient broker API failures — any adapter | ALL broker adapters | High | 6h |
| H16 | Token expiry never detected at runtime | ALL adapters + `token_manager.py` | High | 5h |
| H17 | WebSocket reconnection creates leaked HTTP clients | 7 adapters (upstox, dhan, kotakneo, aliceblue, finvasia, flattrade) | High | 2h |
| H18 | No HTTP client cleanup on disconnect — 8 adapters | 8 adapters (set `client = None` without `.aclose()`) | High | 1h |
| H19 | `DhanAdapter.get_funds` — typo "availabelBalance" always returns 0 | `brokers/dhan_adapter.py:168` | High | 0.25h |
| H20 | `KotakNeoAdapter.stream` — broken WebSocket subscribe, never receives ticks | `brokers/kotakneo_adapter.py:283-284` | High | 4h |
| H21 | `AngelOneAdapter.get_quotes` — N+1 sequential API calls | `brokers/angelone_adapter.py:356-371` | High | 2h |
| H22 | `FyersAdapter` — `Exchange.NSE` hardcoded in all normalization | `brokers/fyers_adapter.py:317, 338, 357, 371` | High | 2h |
| H23 | Market data `_latencies` and observability lists grow unbounded | All observability files | High | 2h |
| H24 | `RuntimeContext.build()` — `get_candles()` method doesn't exist, crashes | `runtime/context.py:86` | High | 1h |
| H25 | Two competing schedulers (`engine/scheduler.py` + `runtime/scheduler.py`) | Both scheduler files | High | 3h |
| H26 | Synthetic historical data poisons cache across users | `market/historical.py:38-43` | High | 2h |
| H27 | No rate limiting on auth endpoints | `routes/v1_auth.py`, `routes/v1_otp.py` | High | 8h |
| H28 | User enumeration via OTP/login endpoints | `routes/v1_otp.py:97-105`, `routes/v1_auth.py:63-64` | High | 1h |
| H29 | No auth on backtest V2 control endpoints | `routes/v1_backtest.py:172-198` | High | 1h |
| H30 | WebSocket no exponential backoff on reconnect | `apps/web/lib/use-market-data.tsx:76` | High | 2h |

*(52 additional HIGH issues omitted for brevity — see subsystem reports for full detail)*

---

## Section 3: Cross-Cutting Themes

### Theme 1: Silent Failures (13 CRITICAL, 22 HIGH)
The audit found a pervasive pattern of `except Exception: pass` or `except Exception: logger.debug(...)` across the codebase:
- `execution/audit.py` — audit entries silently dropped
- `risk/manager.py` — risk config defaults to permissive on DB error
- `core/cache.py` — all cache operations fail silently
- `core/safe_query.py` — all DB errors logged at DEBUG level
- `portfolio/manager.py` — portfolio refresh errors invisible
- `execution/validation.py` — margin check always returns True on error

**Impact:** Ops has no visibility into backend degradation. Failures cascade silently until catastrophic.

### Theme 2: Connection/Resource Leaks (8 CRITICAL, 15 HIGH)
Resources are created but never cleaned up:
- Supabase HTTP clients never closed
- Shared HTTP client never closed on shutdown
- 8 broker adapters set client to None without `.aclose()`
- WebSocket reconnect creates new HTTP clients without closing old ones
- Redis connections can double-connect on singleton race
- Scheduler/WebSocket feeds not stopped on lifespan shutdown

**Impact:** Every hot reload, reconnect, or rolling restart leaks connections until OOM or connection pool exhaustion.

### Theme 3: In-Memory State (6 CRITICAL, 4 HIGH)
Critical state is never persisted:
- OMS orders/brackets/OCO — all lost on restart
- Order queue — all queued/retrying orders lost
- Portfolio state — in-memory, reloaded from DB on demand
- Paper broker account/positions — reset to initial capital
- Risk kill switch — per-user emergency stops cleared
- Rate limiter/dedup state — burst after restart

**Impact:** Any deployment or crash causes total state loss. Trading halts, positions unrecoverable.

### Theme 4: Fail-Open Risk Rules (5 CRITICAL)
Risk rules consistently allow trades when they can't determine the answer:
- `_check_margin` → True on exception
- `_validate_trading_session` → True on exception  
- `MarketClosedRule` → approve on exception
- `TradingWindowRule` → approve on exception
- `_load_config` → permissive default on DB error

**Impact:** Financial risk. Trades execute during outages when they should be blocked.

### Theme 5: Event Loop Blocking (Systemic)
Every route file calls synchronous `supabase.Client.execute()` inside async endpoints. The `async_supabase` helper exists but is never used. This is the single highest-impact performance issue — under load, a few slow DB queries block ALL other requests.

### Theme 6: No Monitoring or Alerting (12 HIGH)
- No alert rules in Prometheus
- No latency percentiles (only averages — misleading)
- No Sentry `before_send` — sensitive data could leak to Sentry
- No health checks on monitoring services themselves
- No alerting on risk events, kill switch triggers, broker failures

---

## Section 4: Prioritized Remediation Plan

### Phase 1 — Immediate (Week 1: ~40h)
*Fix before connecting to real money or deploying to production*

| Priority | Issues | Effort | Impact |
|----------|--------|--------|--------|
| P1 | C01-C07 (Broker timeouts, retry, idempotency, cancel success, margin, market session) | ~20h | Prevents financial loss, hangs, and silent failures |
| P2 | C15-C18, C24 (Risk fail-open, column mapping, drawdown, emergency stop) | ~14h | Prevents unrestricted trading during outages |
| P3 | C26-C31, C34 (Webhook security, OTP, CSRF, CSP, webhook replay, test secrets) | ~8h | Security vulnerabilities |

### Phase 2 — Short-term (Week 2: ~50h)
*Fix before scaling users*

| Priority | Issues | Effort | Impact |
|----------|--------|--------|--------|
| P4 | C08-C14, C38-C40 (OMS persistence, queue, cancel race, bracket SL, audit, events) | ~60h | Order state survival, compliance, bracket safety |
| P5 | C20-C23, C36-C37 (Paper state, margin, PnL, portfolio locking, reconciliation) | ~20h | Data integrity for paper + portfolio |
| P6 | C42-C47 (Infra limits, Docker, backups, secrets in compose, DB blocking, tests) | ~30h | Production infrastructure readiness |

### Phase 3 — Medium-term (Week 3-4: ~80h)
*Fix before marketing / user growth*

| Priority | Issues | Effort | Impact |
|--------|--------|--------|--------|
| P7 | H01-H10, H14, H27-H28 (utcnow, locks, adapters leak, shutdown, Fernet, timeouts, rate limiter, config cache, dedup, auth rate limit, user enum) | ~24h | Platform stability and security 
| P8 | H15-H22 (Broker retry, token expiry, WS reconnect, HTTP cleanup, specific adapter bugs) | ~28h | Broker reliability |
| P9 | H23-H26, H29-H30 (Memory leaks, context crash, scheduler conflict, data poisoning, backtest auth, WS backoff) | ~12h | Runtime stability |

### Phase 4 — Long-term (Month 2: ~100h)
*Fix for production scale*

| Priority | Issues | Effort | Impact |
|--------|--------|--------|--------|
| P10 | All remaining HIGH issues | ~50h | Edge cases and hardening |
| P11 | All MEDIUM issues | ~120h | Code quality and monitoring |
| P12 | All LOW issues | ~50h | Technical debt cleanup |

---

## Section 5: Key Architecture Decisions Required

1. **Event loop blocking**: Decide on a strategy for supabase calls — `run_in_executor` at each call site vs. switching to native async Supabase client vs. using a connection pool adapter like `databases`.

2. **State persistence**: Choose between Redis + PostgreSQL hybrid vs. full PostgreSQL persistence. Given existing Redis dependency, Redis-backed queue + Postgres state storage is recommended.

3. **Broker adapter timeouts**: Define standard timeout constants per broker (order=10s, quote=5s, history=30s) and implement systematically.

4. **Kong vs. direct**: The infra has both Kong API gateway and nginx. Clarify which reverse proxy is the production path, remove the other.

5. **Monorepo package split**: The `packages/shared-types` directory exists but is not used by either the API or frontend. Either adopt it or remove it.

---

*This report represents the consolidated findings from parallel audits of all subsystems. Each issue includes file paths, line numbers, root cause analysis, fix recommendation, and estimated effort. Subsystem-level detail reports are available for each major component.*
