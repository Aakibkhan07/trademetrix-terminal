# Fyers Rate-Limit Compliance Audit

Date: 2026-08-03 · Branch: main · Status: IMPLEMENTED + unit-tested; live verification pending post-deploy

## Scope

Every outbound HTTP request the API makes to Fyers endpoints (`api-t1.fyers.in`, `public.fyers.in`),
plus the rate-limit controls added to stay under Fyers' limits.

Fyers does not publish a hard API rate limit for the v3 REST API; the community-observed ceiling is
**~200 requests/minute per access token** (spikes are answered with HTTP 429, and persistent abuse is
enforced via Cloudflare). Our compliance budget is **100 req/min sustained + 8 req/s burst per access
token** — 50% headroom under the observed ceiling.

## Budget constants (`brokers/fyers_http.py`)

| Constant | Value | Meaning |
|---|---|---|
| `FYERS_RPM_LIMIT` | 100 | sustained ceiling per token, sliding 60s window |
| `FYERS_BURST_PER_SECOND` | 8 | instantaneous burst ceiling |
| `BACKOFF_BASE_SECONDS` | 0.25 | first retry delay |
| `BACKOFF_CAP_SECONDS` | 8.0 | max backoff delay (full jitter) |
| `MAX_RETRIES` | 3 | default retry count (reads) |

Cloudflare semantics: **1015** = rate limited (retryable), **403** = WAF block (NEVER retry —
raise `FyersWAFError`), `Retry-After` header (when present) always wins over computed backoff.

## Endpoint inventory (all REST call sites)

| Endpoint | Method | Caller (`caller=` tag) | Frequency driver | Cache TTL | Dedup | Max retries | Worst-case logical RPM |
|---|---|---|---|---|---|---|---|
| `/api/v3/validate-authcode` | POST | `authenticate` (adapter) | token exchange, ~1/30d per token + reconnect | 0 | off | 2 | ≈0 |
| `/api/v3/orders/sync` | POST | `place_order` | user order submits | 0 | off | 0 | user-driven |
| `/api/v3/orders/sync` | PATCH | `modify_order` | user + bracket SL/target (order-path only) | 0 | off | 0 | user-driven |
| `/api/v3/orders/sync` | DELETE | `cancel_order` | user cancels | 0 | off | 0 | user-driven |
| `/api/v3/orders` | GET | `get_orderbook` | reconcile loop 5s + user polls | 3.0s | on | 3 | 12–60 |
| `/api/v3/positions` | GET | `get_positions` | portfolio polling | 5.0s | on | 3 | ≤20 |
| `/api/v3/holdings` | GET | `get_holdings` | user polling | 10.0s | on | 3 | ≤12 |
| `/api/v3/funds` | GET | `get_funds` | portfolio/margin polling | 5.0s | on | 3 | ≤20 |
| `/data/quotes` | GET | `get_quotes` | WS catch-up, bracket fallback, gate ITM snap | 0.5s | on | 3 | ≤120 (burst-capped 8/s) |
| `/data/history` (→ `/v3/history` fallback) | POST | `get_historical` | chart/backtest on-demand | 0 | off | 1/URL | on-demand |
| `/api/v3/span_margin` | POST | `get_margin_estimate` | order submit pre-check | 60s (per identical payload) | on | 3 | user-driven |
| `/data/options-chain-v3` | GET | `option_chain` (engine) | chain refresh | 10s (market_cache + transport) | on | 3 | ≤6 |
| `/data/options-chain-v3` | POST | `option-chain-route` (API) | web chain request | 10s | on | 1 | ≤6 |
| `public.fyers.in/sym_details/NSE_CM.csv` | GET | `symbol_master` sync | monthly + startup | 24h | — | 3 (backoff cap 8s) | ≈0 |
| `public.fyers.in/sym_details/NSE_FO.csv` | GET | `symbol_master` sync | monthly + startup | 24h | — | 3 (backoff cap 8s) | ≈0 |

Worst-case sustained wire RPM for a fully-loaded single token: reads ≈ 12 (orderbook) + 20 (positions)
+ 20 (funds) + 12 (holdings) + 120 (quotes) + 6 (chains) = **~190 theoretical**, but real-world:
quotes TTL 0.5s + dedup collapses bursts (reconcile/bracket/portfolio all dedupe onto shared single
poll), chains are cache-gated at 10s, and the sliding limiter hard-caps at **100 RPM / 8 per second**.
Order-path writes are user-driven and rare; nothing retries blindly (writes retries=0).

## Controls added

1. **Shared per-token transport** (`brokers/fyers_http.py`, new) — one `FyersTransport` per
   `client_id` (process-wide registry), so every adapter instance/caller for the same token shares a
   single limiter, connection pool, and RPM ledger. Prevented: per-instance limiters each blowing the
   token's ceiling.
2. **TokenRateLimiter** — sliding 60s window + per-second burst ceiling, enforced before the wire
   call; `Retry-After` from 429/1015 honored over computed backoff; jittered exponential backoff
   (base 0.25s, cap 8s) with `MAX_RETRIES=3`.
3. **WAF awareness** — 403 raises `FyersWAFError` immediately (zero retries; retrying a WAF block is
   how datacenter IPs get blacklisted). curl_cffi `impersonate="chrome131"` browser fingerprint
   retained to minimize WAF surface.
4. **Response caching** — GET responses cached for the TTLs above (in-memory, per transport);
   order writes never cached.
5. **Request dedup** — concurrent identical requests collapse into one wire call (in-flight future
   shared by all waiters; a waiter cancelling no longer corrupts the future).
6. **WebSocket-first for live data** — `data_socket` WS feed is the primary symbol stream; REST
   `get_quotes` is only: WS reconnection catch-up, bracket-monitor fallback (tick stale >5s), gate
   ITM spot snap, paper prime. `oms/manager._bracket_quote` prefers a fresh WS-fed
   `market_cache` tick and single-flights quotes per (user, symbol).
7. **Static/historical caching** — symbol CSVs cached 24h (`_fetch_csv` with backoff),
   option chains 10s (both call sites), span margin 60s per identical payload.
8. **One polling worker per session** — unchanged topology, verified compliant: single global
   `_reconcile_loop` (5s) and `_bracket_loop` (2s) in OMS, single WS feed per broker in
   `data_socket`, per-user paper quote priming cache-gated.
9. **Observability** — `GET /brokers/admin/rate-limit` (admin) → `fyers_rate_snapshot()`
   (per-token: calls, wire calls, cache/dedup hits, retries, rate-limited, WAF-blocked, failures,
   current RPM); `fyers` key in `/health/metrics`; structured logs `fyers.request`
   (endpoint, method, status, retries, latency_ms, cached, dedup, rate_rpm, caller) and
   `fyers.retry` (attempt, delay, reason).

## Existing layer kept

`execution/rate_limiter.py` `BROKER_RATE_LIMITS["fyers"] = {calls: 50, window: 60}` (execution-layer
token bucket) still applies per broker call — the transport limiter is an additional per-token
compliance layer, not a replacement.

## Verification

- `tests/test_fyers_http.py` (9 tests): success path, 429 + `Retry-After` honored, 1015 jittered
  backoff capped, WAF 403 zero-retry, plain 400 no-retry, 5-way dedup → 1 wire call, static cache,
  sliding window + burst ceiling, RPM accounting.
- `tests/test_broker_fyers.py` rewritten against mocked transport; `test_margin_estimate.py` updated
  to mock `_http.request` (transport-shape assertions).
- Full API regression: **573 passed, 1 xfailed** (10 new tests).
- Pending after deploy: `/brokers/admin/rate-limit` snapshot under budget on a live trading day;
  `/health/metrics` `fyers` block present; `fyers.request`/`fyers.retry` log lines visible.

## Live verification (post-deploy)

- Imports OK in container; `fyers` key present in `/health/metrics`; `GET /api/v1/brokers/admin/rate-limit`
  returns `{budget_rpm_per_token:100, burst_per_second:8, tokens:[...]}` (admin auth verified).
- A direct `get_funds` smoke call through the transport hit real Fyers and received a proper JSON
  response (401 → adapter fail-open zeros) — **no Cloudflare 403 WAF block** on the new path.
- Full RPM accounting (`tokens` populated, `fyers.request` log lines) requires a valid access token;
  the stored Fyers token expired 2026-08-01 and needs re-authorization via the portal
  (pre-existing gap, unaffected by this change). Until then, option-chain reads correctly fall back
  to NSE → mock with structured warnings.


## Residual risk

- Sustained multi-broker workloads share one token budget — safe because every endpoint's own
  polling frequency is cache-collapsed, but if user count grows, revisit per-user budgets rather
  than the 100 RPM default.
- Yahoo fallback for quotes is a separate provider (unlimited); it must never be mistaken for Fyers
  traffic in dashboards.
- `Retry-After` compliance depends on Fyers actually returning the header; when absent we use the
  jittered backoff, which is conservative by design.
