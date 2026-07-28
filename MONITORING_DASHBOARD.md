# Monitoring Dashboard Setup — TradeMetrix Terminal v1.0.0-rc

## Prometheus Metrics Export

The API exposes a `/metrics` endpoint with the following metric families:

### API Performance
```
http_requests_total{method, path, status}
http_request_duration_seconds{method, path} — buckets: 5ms to 10s
```

### Broker Operations
```
broker_request_duration_seconds{broker, operation} — buckets: 50ms to 30s
broker_requests_success_total{broker, operation}
broker_requests_failure_total{broker, operation}
rate_limit_breaches_total{broker}
```

### Circuit Breakers
```
circuit_breaker_state{breaker} — 0=closed, 1=half_open, 2=open
```

### System Resources
```
process_memory_bytes{type: rss|vms}
process_cpu_percent
```

### Connections
```
active_connections
```

### Database
```
db_query_duration_seconds{table, operation} — buckets: 10ms to 5s
```

### Market Data
```
market_ticks_total{broker}
market_ticks_errors_total{error_type}
market_ticks_reconnects_total{broker}
```

### Health
```
api_health_status — 1=healthy, 0=unhealthy
```

## Grafana Dashboard Panels

### Panel 1: System Overview
- **CPU Usage** — Gauge (0-100%), threshold: 80% yellow, 90% red
- **Memory RSS** — Gauge (MB), threshold: 400MB yellow, 512MB red
- **Active Connections** — Stat
- **API Health** — Stat (1/0)

### Panel 2: API Latency (p50, p95, p99)
- **Query:** `histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))`
- **Query:** `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))`
- **Query:** `histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))`
- **Threshold:** p99 > 2s = red

### Panel 3: Broker Latency by Broker
- **Query:** `histogram_quantile(0.95, sum(rate(broker_request_duration_seconds_bucket[5m])) by (le, broker))`
- **Legend:** `{{broker}}`
- **Threshold:** p95 > 5s = yellow, > 10s = red

### Panel 4: Broker Error Rate
- **Query:** `rate(broker_requests_failure_total[5m]) / (rate(broker_requests_success_total[5m]) + rate(broker_requests_failure_total[5m])) * 100`
- **Legend:** `{{broker}}`
- **Threshold:** > 5% = yellow, > 20% = red

### Panel 5: Circuit Breaker States
- **Query:** `circuit_breaker_state{breaker=~"broker_.*"}`
- **Legend:** `{{breaker}}`
- **Display:** State table — closed (0), half_open (1), open (2)

### Panel 6: Orders Per Second
- **Query:** `rate(http_requests_total{path=~"/v.*/order.*"}[1m])`
- **Type:** Stat

### Panel 7: Redis Performance
- **External data source:** Prometheus Redis exporter
- **Metrics:** `redis_memory_used_bytes`, `redis_connected_clients`, `redis_commands_total`

### Panel 8: PostgreSQL Performance
- **External data source:** Prometheus Postgres exporter
- **Metrics:** `pg_stat_activity_count`, `pg_stat_database_xact_commit`, `pg_stat_database_blks_hit`

### Panel 9: Queue Depth (Webhook Retry)
- **Custom metric:** Export from `infrastructure/queue.py`
- **Metric name:** `webhook_retry_queue_depth`

### Panel 10: WebSocket Clients
- **Query:** `active_connections`
- **Type:** Time series + Stat

### Panel 11: Rate Limit Breaches
- **Query:** `rate(rate_limit_breaches_total[5m])`
- **Legend:** `{{broker}}`
- **Threshold:** > 0.1/s = alert

### Panel 12: Market Tick Rates
- **Query:** `rate(market_ticks_total[1m])`
- **Legend:** `{{broker}}`
- **Type:** Bar gauge

## Alert Rules

| Alert Name | Condition | Severity | Channel |
|------------|-----------|----------|---------|
| APIUnreachable | `api_health_status == 0` for 30s | SEV1 | Telegram, Email |
| HighAPILatency | p99 > 2s for 5min | SEV2 | Telegram |
| BrokerCircuitOpen | `circuit_breaker_state{breaker=~"broker_.*"} == 2` for 1min | SEV2 | Telegram |
| HighBrokerErrorRate | broker error rate > 20% for 5min | SEV2 | Telegram |
| HighBrokerLatency | broker p95 > 10s for 5min | SEV2 | Telegram |
| HighMemoryUsage | RSS > 512MB | SEV3 | Telegram |
| HighCPUUsage | CPU > 80% for 5min | SEV3 | Telegram |
| DatabaseSlow | p95 DB query > 1s for 5min | SEV2 | Telegram |
| RateLimitExceeded | rate > 0.1/s | SEV3 | Telegram |
| BrokerFeedDown | `market_ticks_total` rate = 0 for 5min | SEV2 | Telegram |

## Import Instructions

1. Install Prometheus + Grafana (included in docker-compose.yml)
2. Import the dashboard JSON (located at `infra/grafana-dashboard.json`)
3. Configure alert channels (Telegram bot)
4. Set up data sources:
   - Prometheus: `http://prometheus:9090`
   - (Optional) Redis: `redis://redis:6379`
   - (Optional) PostgreSQL: `postgres://postgres:password@db:5432/postgres`
