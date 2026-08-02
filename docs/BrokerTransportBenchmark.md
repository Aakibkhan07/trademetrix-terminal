# Broker Transport Benchmark — SDK v2 Phase 2 (generic `HttpTransport`)

**Date:** 2026-08-03
**Script:** `apps/api/benchmark_transport.py` (canned-client harness, no network)
**Method:** identical 261-request workload executed against the OLD
`brokers/fyers_http.py` transport (git `HEAD`) and the NEW facade
(`brokers/fyers_http.py` → generic `brokers/sdk/transport.py`), in the same
process, one after the other.

## Workload (261 logical requests)

| Scenario | Count |
|---|---|
| Cached GETs (`/api/v3/funds`, `cache_ttl=5`) | 100 |
| Uncached GETs (`/api/v3/orders`) | 100 |
| Dedup groups — 8 × 4 concurrent identical quote GETs | 32 |
| Retry-heavy GETs (429-then-exhausted ×6, 500-exhausted ×3) | 9 |
| WAF-blocked GETs (403, never retried) | 2 |
| Writes (`POST /orders/sync`, `retries=0`) | 20 |

## Results

| Metric | Before | After | Δ |
|---|---|---|---|
| Wall time (sum of request latencies) | 75.0 ms | 97.1 ms | +22.1 ms |
| Avg latency / request | 0.287 ms | 0.372 ms | +0.085 ms |
| p50 latency | 0.132 ms | 0.186 ms | +0.054 ms |
| Max latency | 4.62 ms | 5.93 ms | +1.31 ms |
| Peak tracemalloc memory | 71.7 KB | 88.2 KB | +16.5 KB |
| **Logical calls** | **263** | **263** | **0** |
| **Wire calls** | **167** | **167** | **0** |
| **Cache hits** (ratio 37.6%) | **99** | **99** | **0** |
| **Dedup hits** (ratio 9.1%) | **24** | **24** | **0** |
| **Retries** | **27** | **27** | **0** |
| **Rate-limited (429/1015)** | **24** | **24** | **0** |
| **WAF blocks** | **2** | **2** | **0** |
| **Failures** | **9** | **9** | **0** |
| Retry delays recorded | 27 | 27 | 0 |

## Interpretation

- **Behavioral parity is exact**: every rate-limit/retry/cache/dedup/WAF
  counter is identical (Δ = 0) under the same workload. The refactor changed
  no semantics.
- **Constant per-request overhead ≈ +0.09 ms and ≈ +63 B/request** — from
  correlation-id generation (`uuid4().hex[:12]`, added for tracing) and the
  Prometheus emit call (`from core.prometheus import ...` is a cached
  sys.modules lookup). Negligible against the 30 s HTTP timeout and the
  ~150 ms real Fyers round-trip.
- **Memory**: the earlier 7.8 MB "delta" was a one-time lazy import of
  `core.prometheus` inside the measured region; with the module pre-loaded
  (it is always resident in the API process), the real peak delta is 16.5 KB.
- **Rate-limit utilization**: budget was disabled (100 000 RPM) in the harness
  to isolate machinery; the limiter itself is byte-identical code (moved from
  `TokenRateLimiter` → `RateLimiter`, same class, same algorithm), so
  sustained-RPM behavior is unchanged by construction.

## Verification gate

Full regression: **662 passed, 1 xfailed** (baseline 644 + 18 new transport
tests). All 42 transport-related tests (fyers + generic + margin + broker
adapter) pass unchanged except two patch-target strings
(`brokers.fyers_http.asyncio.sleep` → `brokers.sdk.transport.asyncio.sleep`)
moved to where `asyncio.sleep` now executes.
