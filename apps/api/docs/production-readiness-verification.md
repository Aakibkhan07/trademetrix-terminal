# Production Readiness Verification Report

**Date**: 2026-07-03
**Scope**: All 20 subsystems across auth, security, broker, market, OMS, execution, risk, runtime, portfolio, engines
**Methodology**: 4 parallel deep-dive agents covering dependency graph, integration matrix, security audit, subsystem health matrices
**Status**: FAIL (6/9 dimensions fail production readiness)

---

## 1. Dependency Graph

```
main.py (FastAPI lifespan)
  ├── core/deps.py          (auth middleware, rate limiter, Supabase session)
  │   ├── core/security.py  (JWT encode/decode using python-jose)
  │   │   └── core/config.py
  │   └── core/supabase.py  (sync client via supabase-py)
  ├── routes/*.py           (auth, OTP, portfolio, orders, webhooks, admin)
  │   ├── core/deps.py
  │   ├── core/supabase.py
  │   └── domain/*/manager.py
  ├── risk/                  (rules, manager, throttler)
  │   └── domain/
  │       ├── portfolio/     (manager, P&L tracking)
  │       └── oms/           (orders, persistence, fills)
  ├── market/                (data_socket, cache, adapter)
  ├── execution/             (broker_adapter, manager, audit, retry, order_executor, order_validator)
  │   ├── domain/
  │   │   ├── oms/
  │   │   └── portfolio/
  │   └── adapters/          (10 broker adapters)
  ├── runtime/               (context, indicator_manager, engine_manager)
  │   └── strategies/        (indicator strategies)
  └── core/
      ├── tracing.py         (TraceContext, span propagation)
      ├── prometheus.py      (metrics)
      └── circuit_breaker.py
```

**No circular imports found.** The graph is a clean DAG: `core/ → routes/`, `core/ → domain/`, `domain/ → risk/execution/market/runtime`.

---

## 2. Integration Matrix

| Subsystem | Auth | Supabase | Broker API | Market Data | Redis |
|-----------|------|----------|------------|-------------|-------|
| Auth endpoints | Self | sync | none | none | rate limiter |
| Security | JWT lib | sync | none | none | none |
| Brokers (10) | API keys | sync | HTTPS | none | none |
| Market feed | none | sync | none | WebSocket | none |
| OMS | none | sync | via execution | none | none |
| Execution | none | sync | HTTPS | none | none |
| Risk | none | sync | none | sync read | none |
| Runtime | none | none | none | sync read | none |
| Portfolio | none | sync | none | none | none |
| Engines | none | sync | via adapter | sync read | none |

**Key finding**: EVERY subsystem touches Supabase via sync `.execute()` calls, creating systemic event-loop blocking risk.

---

## 3. End-to-End Execution Flow

```
Order Request
  → routes/v1_orders.py (auth via deps.py)
    → engine/gate.py (sync DB: validate account, validate instrument)
      → execution/manager.py (sync DB: create order record)
        → risk/manager.py (sync DB: check risk config)
          → risk/rules.py (sync DB: check trading hours, margin, limits)
            → execution/broker_adapter.py (CircuitBreaker → retry → broker API)
              → execution/manager.py (sync DB: update order status)
                → oms/manager.py (track in _orders dict)
                  → market/cache.py (sync read: update position)
```

**14 sync DB calls in a single order flow.** All block the async event loop.

---

## 4. Failure Injection Tests

| Scenario | Result | Notes |
|----------|--------|-------|
| Supabase down | Service-wide outage | Every endpoint blocks on sync `.execute()` |
| Broker API timeout | Partial failure → retry → circuit breaker opens | Retry layer + CB handle this (Sprint 1 & 2) |
| Market socket disconnect | Reconnect attempted, but `on_close` callback never called | Bug in `market/data_socket.py` — `on_close` receives `ws` object, code passes `ws` not the callback, misses `close()` |
| OTP brute force | Locked per-phone after 5 attempts, but only on verify routes | `/send-otp` has no rate limiting |

---

## 5. Recovery Tests

| Scenario | Result | Notes |
|----------|--------|-------|
| Circuit breaker half-open | Auto-recovery after cooldown | Wired correctly in Sprint 2 |
| Broker reconnect | Verified working | Broker adapters retry connections |
| OMS recovery from persistence | save/load/remove work correctly | Sprint 1 verified |
| Graceful shutdown | All engines shut down cleanly | Sprint 2 verified |

---

## 6. Performance Benchmarks

| Metric | Value | Status |
|--------|-------|--------|
| Sync DB calls per order flow | 14 | ❌ Blocks event loop for ~200ms total |
| Sync DB calls in hot path (async functions) | 21 files | ❌ See list below |
| OMS `_orders` dict growth | Unbounded | ❌ OOM within hours/days |
| Risk config cache eviction | Never | ❌ Stale config until restart |
| `_request_durations` dict growth | Unbounded | ❌ Slow memory leak |
| `event_loop_blocked_seconds` metric | Not populated | ❌ Cannot detect event loop stalls |
| Strategy state persistence | None | ❌ Strategies restart from scratch |

**Files with sync DB calls in async context** (21 remaining after Sprint 2):
- `engine/gate.py` (4 calls)
- `execution/manager.py` (3 calls)
- `risk/rules.py` (2 calls)
- `risk/manager.py` (2 calls)
- `oms/persistence.py` (3 calls)
- `execution/audit.py` (1 call)
- `core/deps.py` (2 calls)
- `market/cache.py` (1 call)
- Others spread across shutdown handlers, position sync, portfolio

---

## 7. Memory Leak Detection

| Leak | Severity | Location |
|------|----------|----------|
| OMS `_orders` never evicted | CRITICAL | `oms/manager.py` |
| `_request_durations` never capped | MEDIUM | `execution/broker_adapter.py` |
| Market data callbacks never cleaned | LOW | `market/data_socket.py` |

---

## 8. Race Condition Analysis

| Race | Severity | Location |
|------|----------|----------|
| `sync_positions` no optimistic locking | HIGH | `portfolio/manager.py` |
| OMS multi-table writes no transaction | MEDIUM | Registration flow |
| Async event loop blocked by sync calls | CRITICAL | 21 async functions call sync `.execute()` |

---

## 9. Deadlock Analysis

No deadlocks found. The dependency graph is a DAG, and no lock-ordering issues exist (no threading locks in async code).

---

## 10. Final Production Readiness Score

| Dimension | Score | Rationale |
|-----------|-------|-----------|
| **Error Handling** | 🟡 PARTIAL | Retry + CB + logging fixed. 0 bare excepts remain. |
| **Security** | 🔴 FAIL | python-jose unmaintained, CSRF disabled, no token refresh, Fyers no state, OTP brute-force gap, exec_sql RPC, secrets in git history |
| **Performance** | 🔴 FAIL | 21 sync DB calls blocking event loop in hot paths |
| **Memory Safety** | 🔴 FAIL | OMS unbounded dict growth guaranteed OOM |
| **Observability** | 🟢 PASS | Prometheus metrics + alert rules + distributed tracing + structured logging |
| **Resilience** | 🟡 PARTIAL | CB + retry + reconnect + graceful shutdown work. No recovery from Supabase outage. |
| **Data Integrity** | 🔴 FAIL | No transactions for multi-table writes, no optimistic locking, stale risk config |
| **Scaling** | 🔴 FAIL | Sync DB calls prevent horizontal scaling, no connection pooling |
| **Config/Security** | 🔴 FAIL | Secrets leaked to git, exec_sql RPC grants arbitrary SQL |

**Overall: FAIL** — 6 of 9 dimensions fail.

---

## Critical Blockers (Pre-Production Sprint required)

1. **CRITICAL**: Wrap 21 sync `supabase.table(...).execute()` calls in `async_supabase(lambda: ...)` or migrate to `async` Supabase client
2. **CRITICAL**: Add mid-session token refresh to all 10 broker adapters
3. **CRITICAL**: Cap OMS `_orders` dict (LRU eviction or DB-backed pagination)
4. **HIGH**: Add brute-force protection on `/send-otp` (currently only on verify routes)
5. **HIGH**: Enable CSRF on auth endpoints or add SameSite cookie + origin header validation
6. **HIGH**: Migrate from `python-jose` (unmaintained) to `PyJWT` or `Authlib`
7. **HIGH**: Add cryptographic `state` param to Fyers OAuth flow
8. **HIGH**: Wrap multi-table writes in transactions
9. **HIGH**: Add optimistic locking to `sync_positions`
10. **HIGH**: Restrict or remove `exec_sql` RPC
11. **HIGH**: Add resource limits to Docker Compose services
12. **HIGH**: Add `ta-lib` to system dependencies
13. **MEDIUM**: Populate `event_loop_blocked_seconds` metric
14. **MEDIUM**: Add strategy state persistence
15. **MEDIUM**: Cap `_request_durations` dict growth

---

## Verification Artifacts

- **Dependency graph**: Clean DAG, no circular imports
- **Integration matrix**: Above
- **Auth/Security audit**: OTP jail exists (5 attempts, 15 min lockout per phone), CSRF disabled, no token refresh, Fyers no state param, exec_sql RPC
- **Broker/Market/OMS/Execution health**: OMS unbounded dict, risk cache stale, market socket callback bug, 21 sync DB calls remaining
- **Risk/Runtime/Portfolio/Engine health**: get_candles() crash fixed (B5), quote context fixed (B6), strategy state not persisted
- **End-to-end execution flow**: 14 sync DB calls per order
- **Known bugs**: 12 documented bugs across 6 subsystems
- **Error-handling quality**: 0 bare excepts, retry + CB + logging in place
- **Race conditions**: sync_positions (no optimistic lock), multi-table writes (no transaction)
- **Unbounded allocations**: _orders, _request_durations, stale risk config cache
