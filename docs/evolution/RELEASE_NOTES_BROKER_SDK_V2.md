# Broker SDK v2 — Release Notes (v1.3.1 · SDK Complete)

**STATUS:** ✅ PRODUCTION COMPLETE (Phases 1–4) — 2026-08-03
**Tag:** `v1.3.1-broker-sdk-complete`
**Broker SDK freeze:** effective 2026-08-03 — no further architectural refactoring unless fixing a
production defect or adding a completely new broker. Feature work now moves to user-facing
capabilities.

**Validation gate:** API regression **715 passed, 1 xfailed** · live-cert framework unit-tested ·
Broker health/metrics/capabilities endpoints verified · deployed (deploy.sh, health-gated).

---

## Phase 1 — Foundation (v1.2.0)

- **`brokers/sdk/errors.py`** — typed `BrokerError` taxonomy (auth, rate-limit w/ Retry-After, WAF — never
  retried, connection, timeout, validation, order-rejected, insufficient margin, server) + `translate_*`.
- **`brokers/sdk/capabilities.py`** — `CapabilityFlag` enum + authoritative per-broker matrix; legacy
  `BROKER_CAPABILITIES` derives from it.
- **`brokers/sdk/registry.py`** — single source of truth (adapter class + UI metadata + capabilities);
  legacy `create_broker`/`get_broker_metadata` delegate to it.
- **`brokers/sdk/interface.py`** — 19-method v2 surface + `BrokerAdapterBase` (zero-behavior-change
  port of all 11 adapters); unimplemented features raise typed `UnsupportedFeatureError`.
- **`brokers/sdk/certification.py`** — Level A interface cert + Level B behavioral flow; all 11 brokers
  CERTIFIED (1 recorded gap later closed in Phase 4).
- Verification: regression 644 passed, 1 xfailed.

## Phase 2 — Generic transport (v1.3.0)

- **`brokers/sdk/transport.py`** — generic `HttpTransport`: per-token sliding-window rate limiter,
  jittered backoff honoring `Retry-After` (429/1015), zero-retry WAF (403), in-flight dedup, GET cache,
  correlation ids, `health()`, Prometheus counters. `brokers/fyers_http.py` became a thin facade — public
  API identical, all 7 consumers untouched.
- Verified with a before/after benchmark: Δ = 0 on every accounting counter; overhead ≈ +0.09 ms +
  ~63 B/request (`docs/BrokerTransportBenchmark.md`).
- Verification: regression 662 passed, 1 xfailed.

## Phase 3 — Reusable infrastructure (v1.3.1)

- **`events.py`** — typed broker audit event bus (`BrokerEventKind`) with sequence-numbered fan-out,
  logging/metrics sinks, ring buffer, health bridge.
- **`auth.py`** — unified token/session lifecycle: expiry detection (5-min buffer), single-flight
  refresh, re-auth state, `TokenStore`, per-account `SessionManager`, `AuthProvider` contract.
- **`websocket.py`** — backend-agnostic WS manager: reconnect/backoff (cap 60s), heartbeats + latency,
  subscription dedup + resubscribe, message routing.
- **`health.py`** — `BrokerHealthService`: component signals → canonical health state, event-driven.
- Verification: regression 690 passed, 1 xfailed (added `test_sdk_phase3.py`).

## Phase 4 — Observability + live certification (v1.3.1)

- **`metrics.py` + `observability.py`** — unified flat metrics snapshot + one-call app wiring
  (`wire_default_observability`), breaker-state bridge.
- **`fyers_provider.py`** — Fyers auth provider + live-observability glue.
- **Endpoints** — `GET /api/v1/brokers/health[/{broker}]`, `/metrics/{broker}`, `/capabilities`;
  `/health/metrics` `brokers` block.
- **Live certification** — `brokers/sdk/live_cert.py` (canonical engine workflow, order steps opt-in,
  per-step timeouts, JSON+MD reports) + `python -m brokers.live_cert --broker <name>` CLI.
- Verification: regression 715 passed, 1 xfailed (+53; 9 new live-cert tests).

---

## Remaining known limitations

1. **Fyers `get_option_chain` — live cert run pending a real token.** Functionality is in place and
   platform-covered by the transport; only the credential-backed live-cert exercise is outstanding (a
   validation gap, not a code defect).
2. **Live cred-backed certification for the other 10 brokers** — the framework is ready; runs await
   active credentials per broker.
3. **Durable broker audit-event store** — the event bus exists; a persistent consumer is not yet built.

## Next roadmap (post-freeze, user-facing focus)

- Broker **Devices**: option chain UI hardening (build on the existing gap-closing work).
- Markets: use the live-cert framework to produce per-broker certification reports as credentials come in.
- User-facing capabilities (trade insights, alerts, backtesting libraries) — no SDK redesigns unless a
  new broker warrants one.
- Performance phase (benchmarks) stays deferred; re-open only under the freeze exception.

---

## Operational notes

- Live certification: `cd apps/api && .venv/bin/python -m brokers.live_cert --broker fyers --allow-orders --out docs/evolution/certs/fyers_live.json` (on the API host with valid credentials).
- Architecture: `docs/evolution/BROKER_SDK_V2.md` · Transport benchmark: `docs/BrokerTransportBenchmark.md` · Live-cert reports: `docs/evolution/certs/`.
- Freeze scope: internals of `brokers/sdk/*`; adapters + auth providers are still extended for new brokers.