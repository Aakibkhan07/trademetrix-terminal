# Trade Metrix Terminal — API Reference

Base URL: `http://localhost:8000/api/v1`

All endpoints (except auth + health) require `Authorization: Bearer <access_token>` header.

---

## Authentication

### POST /auth/signup
```json
{"email": "user@example.com", "password": "SecurePass123!"}
```
→ `201` or `409`

### POST /auth/signin
```json
{"email": "user@example.com", "password": "SecurePass123!"}
```
→ `200` `{"access_token": "jwt...", "refresh_token": "jwt..."}`

### POST /auth/refresh
```json
{"refresh_token": "jwt..."}
```
→ `200` `{"access_token": "jwt..."}`

### GET /auth/me
→ `200` `{"id": "...", "email": "...", "full_name": "...", "subscription_tier": "..."}`

---

## Market Data

### WebSocket /marketdata/ws
Connect: `ws://localhost:8000/api/v1/marketdata/ws?access_token=<jwt>`

**Client → Server:**
```json
{"action": "subscribe", "symbols": ["NIFTY", "BANKNIFTY"]}
{"action": "unsubscribe", "symbols": ["NIFTY"]}
```

**Server → Client:**
```json
{"type": "tick", "symbol": "NIFTY", "last_price": 24500.50, "bid": 24500.0, "ask": 24501.0, ...}
{"type": "connection", "status": "connected", "simulator_active": true}
```

### POST /marketdata/simulator/start
`{"interval": 0.5}` — Start tick generator

### POST /marketdata/simulator/stop
Stop tick generator

---

## Backtest

### POST /backtest/run
```json
{
  "strategy": "trend_rider",
  "symbol": "NIFTY",
  "interval": "15m",
  "start": "2024-01-01",
  "end": "2024-12-31",
  "capital": 100000,
  "params": {"ema_fast": 10, "ema_slow": 30}
}
```
→ `200` BacktestResult with trades, equity curve, metrics

---

## Risk Management

### GET /risk/live/status
Current live trading status (on/off)

### POST /risk/kill-switch
```json
{"enabled": true}
```
Enable/disable kill switch

### GET /risk/settings
Get current risk settings

### PUT /risk/settings
Update risk limits (max position, daily loss, drawdown, etc.)

---

## Engine

### POST /engine/execute
Execute a strategy signal:
```json
{
  "strategy_id": "trend_rider",
  "symbol": "NIFTY",
  "side": "BUY",
  "quantity": 75,
  "order_type": "MARKET",
  "product": "INTRADAY"
}
```

---

## Brokers

### GET /brokers/list
List available brokers: `["fyers", "dhan", "zerodha"]`

### POST /brokers/{name}/connect
Authenticate with a specific broker (see broker-specific docs)

---

## Health & Monitoring

### GET /health/live
Liveness probe — always `200`

### GET /health/ready
Readiness probe — checks DB + Redis connectivity

### GET /metrics/prometheus
Prometheus metrics endpoint (OpenMetrics format)

### GET /metrics
Application metrics (CPU, memory, request stats, circuit breakers)
