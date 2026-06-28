# Trade Metrix Terminal — Architecture

## Overview

```
┌─────────────────────────────────────────────────────────┐
│                      Web (Next.js 14)                    │
│  app/marketdata  │  app/backtest  │  app/dashboard       │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP/WSS
┌──────────────────────▼──────────────────────────────────┐
│                   API (FastAPI)                          │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Auth Routes  │  │  Risk Routes │  │ Strategy Rts │  │
│  ├──────────────┤  ├──────────────┤  ├──────────────┤  │
│  │  Market Data  │  │  Backtest    │  │  Engine      │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Core Services                        │   │
│  │  Config │ Logging │ Cache │ Vault │ Sentry        │   │
│  │  HTTP Pool │ Circuit Breaker │ Rate Limit          │   │
│  │  Prometheus Metrics │ Resilience                    │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │           Broker Adapters                         │   │
│  │  FyersAdapter │ DhanAdapter │ ZerodhaAdapter      │   │
│  │  (REST + WebSocket streaming)                     │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                   External Services                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐   │
│  │ PostgreSQL│  │  Redis   │  │  Brokers (F/D/Z)     │   │
│  │ (Supabase)│  │  (Cache) │  │  (WebSocket feeds)   │   │
│  └──────────┘  └──────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Design Decisions

### Shared HTTP Client
A singleton `SharedHttpClient` manages connection pooling (100 max connections, 20 keepalive). All broker adapters and auth routes reference it instead of owning individual clients. Avoids socket exhaustion under load.

### WebSocket Architecture
- **Simulator**: `MarketSimulator` generates synthetic ticks on startup for dev/demo
- **Live brokers**: Each `BaseBroker.stream()` connects to the broker's WebSocket API with auto-reconnect and exponential backoff
- **SharedDataSocket**: Pub/sub relay — broker feeds push ticks → `SharedDataSocket.broadcast_tick()` → all connected frontend WS clients

### Circuit Breaker Pattern
Each external dependency (Redis, DB, each broker) has a `CircuitBreaker` with:
- 5 failure threshold → open
- 30s cooldown → half-open
- 3 success → closed
Exposed via `/metrics/prometheus` as `circuit_breaker_state` gauge.

### Security
- JWT auth (access + refresh tokens)
- WebSocket auth validated on connect via `access_token` query param
- Rate limiting: 120 req/min/IP via sliding window
- Request validation: content-type enforcement, 100KB body limit, security headers
- Secrets vault: `.env.vault` encrypted with `DOTENV_KEY`

### Monitoring Stack
- **Sentry**: Error tracking (FastAPI + logging integrations)
- **Prometheus**: `/metrics/prometheus` endpoint with HTTP counters, histograms, circuit breaker states, process metrics
- **Structured JSON logging**: All logs are JSON for ingestion by Loki/Elasticsearch
- **Health checks**: `/health/live` and `/health/ready` endpoints

## Data Flow: Market Data

```
Broker WS → BaseBroker.stream() → SharedDataSocket.broadcast_tick()
                                        ↓
                              WebSocket connection handler
                                        ↓
                              Frontend (SSE/WS client)
```

## Data Flow: Order Placement

```
Frontend → POST /api/v1/engine/execute → RiskManager.validate()
                                              ↓
                                    BaseBroker.place_order()
                                              ↓
                                    OrderManager.track()
                                              ↓
                                    WebSocket status update
```

## Database

9 tables: users, sessions, orders, positions, holdings, audit_logs, risk_settings, strategies, plans.

Alembic migration at `apps/api/alembic/versions/001_initial_schema.py`.

## Deployment Topography

- **Dev**: Docker Compose with Supabase local, Redis, API, Web
- **Staging**: Docker Compose with Postgres, Redis, API, Web, Prometheus, Grafana
- **Prod**: Same as staging + cloud PG, multi-replica API behind LB
