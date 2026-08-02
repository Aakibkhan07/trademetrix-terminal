# Unified Broker SDK v2 — Enterprise Architecture

Status: IMPLEMENTED (Phases 1–2) · Owner: Platform Engineering · Target: real-money multi-broker trading

## 1. Mission

One broker-agnostic interface for the entire application (engine, OMS, strategies, UI, backtests).
Adding or swapping a broker changes exactly one thing: the broker adapter registered in the
SDK registry. The trading engine must never know which broker is connected.

```
Engine / OMS / Strategies / UI / Backtest
                 │  (never touches broker code)
                 ▼
        BrokerExecutionAdapter (per-user facade)
                 │
                 ▼
   ┌────────────────────────────────────────────┐
   │           UNIFIED BROKER SDK v2            │
   │  interface ─ registry ─ factory ─ errors   │
   │  capabilities ─ transport ─ auth ─ ws      │
   │  rate limit ─ retry ─ circuit breaker      │
   │  health ─ metrics ─ audit ─ translation    │
   └────────────────────────────────────────────┘
                 │
                 ▼
       Broker Adapters (Fyers, Angel, Dhan, …)
```

## 2. Current state (audit, 2026-08-03)

| Concern | Status today |
|---|---|
| Adapter surface | `BaseBroker` ABC: authenticate, place/modify/cancel, orderbook, positions, holdings, funds, quotes, historical, stream, disconnect + margin estimate + unsubscribe |
| Adapters | fyers, angelone, dhan, zerodha, upstox, aliceblue, fivepaisa, finvasia, flattrade, kotakneo, groww (11) |
| Registry | `brokers/registry.py` UI metadata only; `brokers/__init__.py` class map + `create_broker()` → `CircuitBreakerBroker(Adapter())` |
| Capabilities | static `BROKER_CAPABILITIES` dict in `execution/broker_adapter.py` (10 booleans) |
| Reliability | `core/resilience.py` CircuitBreaker + retry; `execution/rate_limiter.py` per-broker bucket; `brokers/circuit_breaker_broker.py` wrapper |
| Transport | generic `brokers/sdk/transport.py` `HttpTransport` (sliding limiter, jittered backoff, Retry-After, WAF-aware, cache, dedup, correlation ids, Prometheus counters, health) with pluggable strategies; Fyers uses it via a thin facade |
| Errors | typed taxonomy in `brokers/sdk/errors.py` (`BrokerError` + WAF/auth/rate-limit/timeout/connection/validation/order-rejected) + `translate_broker_error` |
| Observability | `core/prometheus.py` broker op metrics + `broker_http_*` transport counters; `/health/metrics` with `fyers` block; structured `fyers.request`/`fyers.retry`/`fyers.waf` logs with `corr=` |

Gaps vs mission: no typed error taxonomy, no `UnsupportedFeatureError` contract, no capability
*discovery* (static dict only), transport/retry/circuit logic not generalized, no auth layer
abstraction, no unified WS layer, no broker health monitor, no per-call audit, no cert suite.

## 3. Target architecture (Clean Architecture)

Layers (dependency rule: outer → inner only):

1. **Domain** — `core/models.py` (NormalizedOrder, OrderResult, Position, Holding, Funds, Quote, Candle, Tick, Session) — already broker-agnostic; unchanged.
2. **Application** — engine, OMS, strategies, backtest — depend on `BrokerExecutionAdapter`, never on adapters.
3. **Infrastructure / SDK** — `brokers/sdk/`:
   - `errors.py` — typed error taxonomy + error translator
   - `capabilities.py` — `Capability` enum + `BrokerCapabilities` (superset, backward-compatible) + authoritative matrix
   - `interface.py` — `BrokerPort` (v2 surface) + `BrokerAdapterBase` (compat adapter implementing v2 from BaseBroker)
   - `registry.py` — `BrokerRegistry` (single source of truth: adapter class + metadata + capabilities)
   - `transport.py` (Phase 2) — generic `HttpTransport` (rate limit, retry, dedup, cache, WAF) extracted from fyers_http
   - `auth.py` (Phase 3) — OAuth/token/session lifecycle abstraction
   - `websocket.py` (Phase 3) — unified WS client with reconnect/heartbeat
   - `health.py` (Phase 3) — per-broker health monitor, connection scoring, dead-connection detection
   - `audit.py` (Phase 3) — per-call broker audit trail
4. **Adapters** — one file per broker implementing `BaseBroker` (transport-backed), registered in the registry.

### Required v2 method surface (every adapter exposes these)

`connect()` · `disconnect()` · `refresh_token()` · `get_profile()` · `get_funds()` ·
`get_holdings()` · `get_positions()` · `get_orders()` · `place_order()` · `modify_order()` ·
`cancel_order()` · `exit_position()` · `get_quotes()` · `get_option_chain()` ·
`get_historical_data()` · `subscribe_market_data()` · `unsubscribe_market_data()` · `health()` · `capabilities()`

Backward compatibility: `BrokerAdapterBase` implements the v2 names in terms of the existing
`BaseBroker` methods (`get_orders → get_orderbook`, `get_historical_data → get_historical`,
`subscribe_market_data → stream`, etc.). Anything without a base implementation raises
`UnsupportedFeatureError` instead of failing unpredictably.

## 4. Capability matrix (authoritative, `brokers/sdk/capabilities.py`)

`✓` = supported · `–` = `UnsupportedFeatureError` (never an unpredictable failure)

| Capability | fyers | angelone | dhan | zerodha | upstox | aliceblue | finvasia | flattrade | fivepaisa | kotakneo |
|---|---|---|---|---|---|---|---|---|---|---|
| Orders | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Order modification | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Order cancellation | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Bracket orders | ✓ | ✓ | – | ✓ | ✓ | – | – | – | – | ✓ |
| Cover orders | – | ✓ | – | ✓ | ✓ | – | – | – | – | – |
| GTT | – | ✓ | ✓ | ✓ | ✓ | – | – | – | – | ✓ |
| Multi-leg orders | – | ✓ | – | – | – | – | – | – | – | – |
| Option chain | ✓ | – | – | – | – | – | – | – | – | – |
| Historical data | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| WebSocket | ✓ | ✓ | ✓ | – | ✓ | ✓ | ✓ | ✓ | – | ✓ |
| Market depth | – | ✓ | ✓ | – | ✓ | – | – | – | – | – |
| Greeks | – | – | – | – | – | – | – | – | – | – |
| Indices | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Currency | ✓ | – | – | – | – | – | – | – | – | – |
| Commodity | – | – | – | – | – | – | – | – | – | – |
| Margin calculator | ✓ | – | – | – | – | – | – | – | – | – |
| Quotes | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Positions | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Holdings | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

Derived from the production-proven static matrix (`execution/broker_adapter.py`) + Fyers
verification; adjust only with evidence from certification runs.

## 5. Reliability engine (unified pipeline)

Every transport request passes through, in order:

```
caller → [capability gate] → [sliding rate limiter] → [dedup/in-flight merge] → [cache read]
      → [circuit breaker] → [wire call] → [error translator] → [retry w/ Retry-After + jitter]
      → [metrics + audit + correlation id]
```

Rules: writes never auto-retry (place/modify/cancel) · 403 (WAF) never retries · 429/1015 honors
`Retry-After` else jittered backoff (base 0.25s cap 8s) · 5xx retried (max 3) · 4xx translated to
typed errors, never retried · order submission idempotency via client-order-id where the broker
supports it (Dhan request_id, Fyers orderTag) · duplicate request prevention via in-flight merging.

## 6. Sequence diagrams

### 6.1 Connect + place order (engine → broker, broker-agnostic)

```mermaid
sequenceDiagram
    participant E as Engine/OMS
    participant X as BrokerExecutionAdapter
    participant R as Registry
    participant A as Adapter (transport)
    participant B as Broker API

    E->>X: place_order(order)
    X->>R: capabilities(broker)
    R-->>X: BrokerCapabilities
    X->>X: validate_order (capability gate)
    X->>X: acquire_broker_token (execution bucket)
    X->>A: place_order(order)
    A->>A: rate limiter (per-token)
    A->>A: circuit breaker check
    A->>B: POST /orders/sync (idempotency key)
    alt transient failure (429/5xx/network)
        A->>A: jittered backoff + Retry-After
        A->>B: retry (max 3)
    end
    B-->>A: order id + status
    A-->>X: OrderResult
    X-->>E: OrderResult (FILLED/PENDING/…)
    Note over A: metrics, audit log, correlation id recorded
```

### 6.2 Market data (WS preferred, REST fallback)

```mermaid
sequenceDiagram
    participant S as data_socket
    participant A as Adapter
    participant W as Broker WS
    participant R as REST (transport)

    S->>A: subscribe_market_data(symbols)
    A->>W: WS connect (auth)
    W-->>A: tick stream
    A-->>S: on_tick(Tick)
    Note over A: heartbeat monitor
    W--x A: dead connection detected
    A->>A: exponential reconnect (cap 30s)
    A->>R: get_quotes(missed) — REST catch-up (0.5s TTL, dedup)
    A->>W: WS reconnect
```

### 6.3 Error translation

```mermaid
sequenceDiagram
    participant A as Adapter
    participant T as ErrorTranslator
    participant C as Caller
    A->>T: (status_code, body, exception)
    alt 429 / Cloudflare 1015
        T-->>A: BrokerRateLimitError (retryable, Retry-After)
    else 403 (Cloudflare)
        T-->>A: BrokerWAFError (never retry)
    else 401 / token expired
        T-->>A: BrokerAuthError (refresh + retry once)
    else 4xx broker rejection
        T-->>A: OrderRejectedError / BrokerValidationError
    else 5xx / network / timeout
        T-->>A: BrokerConnectionError / BrokerTimeoutError (retryable)
    end
    A-->>C: typed error (code, broker, retryable, correlation_id)
```

## 7. Observability (Phase 3 additions)

Prometheus (new broker_* metrics): `broker_requests_total{broker,operation,status}`,
`broker_request_duration_ms{broker,operation}`, `broker_rpm_usage{broker,client}`,
`broker_reconnects_total{broker}`, `broker_uptime_seconds{broker}`, `broker_circuit_state{broker}`,
`broker_ws_*{broker}` (connected, messages, missed), `broker_order_latency_ms{broker,type}`.
Health: `/brokers/admin/rate-limit` (done), per-broker `/health` block with connection score
(0–100 from heartbeat age, recent failures, circuit state). Every broker call logs one structured
line with correlation id: `broker.call {broker, operation, status, latency_ms, retries, cached, dedup, correlation_id}`.

## 8. Phased roadmap (each phase ends green: `pytest tests/` + deploy)

| Phase | Scope | Exit gate |
|---|---|---|
| **1** (done 2026-08-03) | `brokers/sdk/`: errors, capabilities matrix, registry, interface; wire execution layer + UI metadata to registry | 644 passed; typed-error tests; prod cert 11/11 |
| **2** (done 2026-08-03) | Generalize transport: `brokers/sdk/transport.py` `HttpTransport` extracted from `fyers_http.py` (rate limit, retry, dedup, cache, WAF, correlation ids, metrics, health); Fyers uses it via thin facade; before/after benchmark | 662 passed; `docs/BrokerTransportBenchmark.md` |
| **3** | Auth layer (unified token/session lifecycle incl. refresh_token), WS layer (reconnect/heartbeat), health monitor, audit logger, error-translator adoption in all adapters | all adapters cert (mock) |
| **4** | Adapter port: Fyers → full v2 surface (get_profile, get_option_chain, exit_position); Angel/Dhan v2 aliases; capability discovery endpoint (`GET /brokers/{name}/capabilities`) | per-broker cert green |
| **5** | Certification suite on live sandbox (auth→quotes→order lifecycle→funds→holdings→positions→reconnect→rate limit→breaker→health) for fyers/angel/dhan | cert report `docs/BrokerCertification.md` |
| **6** | Performance: thousands of users — transport sharing audit, cache hit-rate, WS-first enforcement, memory profile; benchmarks report | `docs/BrokerBenchmarks.md` |

New broker onboarding after Phase 4 = write one adapter file + one registry entry + run cert suite.

## 9. Migration plan (zero breakage)

1. **Phase 1 additive only**: `brokers/sdk/` is new; no existing file's behavior changes.
2. Execution layer capabilities re-pointed to SDK matrix (same values; verified by tests).
3. `brokers/registry.py` metadata re-pointed to SDK registry (same payload).
4. Adapters keep `BaseBroker`; v2 method names added via `BrokerAdapterBase` mixin as aliases —
   old callers untouched.
5. Engine/OMS continue via `BrokerExecutionAdapter` (already broker-agnostic).
6. Transport generalization (Phase 2) behind the same `get_transport()` entry point — Fyers
   callers unchanged.
7. Each phase deployed via `deploy.sh`; feature-flag nothing — additive code only.

## 10. Rollback strategy

- Every phase is additive: removing it = revert the commit(s). No data migration is required.
- Transport/registry entry points return to previous behavior by reverting the wiring commit
  (`execution/broker_adapter.py`, `brokers/__init__.py`).
- Capabilities: if a capability flag is later found wrong, flip the single matrix cell and
  re-run cert — no code change in consumers.
- Live trading risk: order-path behavior is unchanged in Phases 1–3 (writes still retries=0,
  idempotency keys as today); only observability and typed errors change.
- Backup snapshot before each deploy (`infra/scripts/backup.sh`) + git revert + redeploy is the
  documented DR path (see `DISASTER_RECOVERY.md`).

## 11. Phase 2 — generic `HttpTransport` (done 2026-08-03)

### Design decisions

1. **Generic core, broker facade.** `brokers/sdk/transport.py` owns every piece of
   machinery with **zero broker-specific logic** (enforced by
   `test_transport_has_no_broker_specific_logic` — no broker names, no
   `broker == ...` branches). `brokers/fyers_http.py` is now a thin facade
   supplying `TransportConfig` (budgets, hosts, retry knobs) + strategy
   overrides; its public API is byte-for-byte the same
   (`FyersTransport`, `FyersResponse`, `FyersWAFError`, `TokenRateLimiter`,
   `get_transport`, `fyers_rate_snapshot`) so all 7 consumer sites were
   untouched.
2. **Strategy extension points** (per the Phase-2 mandate, no `if broker`):
   - `AuthStrategy` — `authorization()` header + `sign()` hook for HMAC-style
     signing (Fyers: `{client_id}:{access_token}`).
   - `HeaderStrategy` — static header set + Content-Type logic (Fyers:
     browser-identical headers for Cloudflare).
   - `URLBuilder` — path → absolute URL + stats stub (Fyers: `api-t1.fyers.in`
     + `public.fyers.in` CSV stubs, preserving legacy stats keys).
   - `ResponseParser` — raw client response → `TransportResponse`.
   - `ErrorTranslator` — status → typed `BrokerError` (Fyers: 403 →
     `FyersWAFError`, which now also subclasses SDK `BrokerWAFError`).
   - `RetryPolicy` — retryable statuses, Retry-After, jittered backoff.
   - `RateLimiter` (a.k.a. `TokenRateLimiter`) — the rate-limit policy
     (sliding window + burst), byte-identical to the pre-refactor limiter.
3. **New capabilities**: per-request `correlation_id` (defaults to a uuid,
   logged as `corr=` on every `request`/`retry`/`waf` record), `health()`
   (liveness + latency + last error), Prometheus counters
   (`broker_http_calls/wire_calls/cache_hits/dedup_hits/retries/
   rate_limited/waf_blocks/failures_total` + `broker_http_latency_seconds`),
   and `waf_statuses`/`rate_limit_statuses`/`retryable_http` config sets.
4. **Shared pools preserved**: one transport + one limiter per `client_id`
   via the facade registry — all adapter/caller instances for a token share
   the connection pool and RPM ledger.
5. **Verification**: full regression **662 passed, 1 xfailed** (baseline 644);
   before/after benchmark (identical canned workload vs git HEAD) shows **Δ = 0
   on every accounting counter** (calls/wire/cache/dedup/retries/rate-limited/
   WAF/failures) and ~+0.09 ms + ~63 B per request from correlation-id +
   metric emission — see `docs/BrokerTransportBenchmark.md`.
6. **Test-only change**: two `asyncio.sleep` patch targets moved from
   `brokers.fyers_http` to `brokers.sdk.transport` (where sleep now executes).

### Onboarding another broker (post-Phase 4)

```python
from brokers.sdk.transport import HttpTransport, TransportConfig

config = TransportConfig(broker="acme", base_url="https://api.acme.in",
                         rpm=60, burst=5, impersonate="chrome131",
                         log_prefix="acme")
class AcmeAuth(AuthStrategy): ...   # tokens/signing
class AcmeHeaders(HeaderStrategy): ...
class AcmeURL(URLBuilder): ...
class AcmeErrors(ErrorTranslator): ...  # status -> BrokerError subclasses
transport = HttpTransport(config, client_id=cid, access_token=tok,
                          auth=AcmeAuth(), headers=AcmeHeaders(),
                          url_builder=AcmeURL(), translator=AcmeErrors())
```

No machinery changes required — the transport never branches on broker.
