# Founder Dashboard

**Route:** `/admin/founder`  
**Auth:** Admin only (gated by `isAdmin` from `auth-context`)  
**Refresh:** Auto-polls every 5 seconds from existing API endpoints

## Metric Tiles

| # | Tile | Source Endpoint | Field / Derivation |
|---|------|----------------|-------------------|
| 1 | Total Users | `GET /admin/stats` | `total_users` |
| 2 | Active (24h) | `GET /admin/audit-log?limit=500` | Unique `user_id` count from recent entries |
| 3 | Online Now | `GET /admin/users` | Array length (all registered users, not real-time presence) |
| 4 | Admins | `GET /admin/stats` | `total_admins` |
| 5 | Orders Today | `GET /admin/orders?limit=5000` | Filter `created_at` to today's date |
| 6 | Paper Trades | `GET /admin/orders?is_paper=true` | `count` field |
| 7 | Live Trades | `GET /admin/orders?is_paper=false` | `count` field |
| 8 | Risk Rejections | `GET /admin/audit-log?limit=500` | Entries whose `action` contains "risk" or "reject" |
| 9 | Total Strategies | `GET /admin/stats` | `total_strategies` |
| 10 | Running | `GET /engine/runs` | Runs where `status === 'running'` or `status === 'active'` |
| 11 | Active Assignments | `GET /admin/stats` | `active_assignments` |
| 12 | Backtests | `GET /engine/runs` | Runs where `mode === 'backtest'` or `type === 'backtest'` |
| 13 | Broker Connections | `GET /admin/active-brokers` | `active_broker_count` |
| 14 | OAuthed Brokers | `GET /admin/active-brokers` | `oauthed_count` |
| 15 | Connected by Type | `GET /admin/brokers` | Grouped by `broker` field |
| 16 | CPU | `GET /health/metrics` | `system_cpu_percent` (or `cpu_percent`) |
| 17 | RAM | `GET /health/metrics` | `system_memory_percent` (derived from `used`/`total` if absent) |
| 18 | API Latency | `GET /api/v1/health/live` | Client-side `performance.now()` measurement |
| 19 | WebSocket | `GET /health/metrics` | `websocket_connections` (if exposed) |
| 20 | Prometheus | `GET http://localhost:9090/-/healthy` | Direct fetch (may be unreachable from browser) |
| 21 | Grafana | `GET http://localhost:3000/api/health` | Direct fetch (may be unreachable from browser) |
| 22 | Redis | `GET /health/metrics` | `redis_active` boolean |
| 23 | Redis Memory | `GET /health/metrics` | `redis_used_memory_human` |
| 24 | Error Rate | `GET /admin/audit-log?limit=500` | `errorEntries.length / totalEntries * 100` — entries with "error" or "fail" in action |

## Tiles marked "—"

The following metrics have no backend API endpoint and display "—":

- **Beta Users** — tracked client-side on `/admin/beta` only
- **Invite Codes** — managed client-side on `/admin/beta` only
- **OMS Queue Depth** — not exposed by any current API
- **API Requests/min** — not exposed in health/metrics in current build

## Architecture

```
┌─────────────────────────────┐
│  /admin/founder/page.tsx     │  Client Component
│  └── useApi() × 9           │  Parallel data fetches
│  └── fetchExternalHealth()  │  /health/live, /health/metrics, Prometheus, Grafana
│  └── setInterval(5000)      │  Refreshes all tiles by incrementing refreshKey
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  Existing API Layer          │
│  /admin/*, /engine/*,       │
│  /health/*                  │
└─────────────────────────────┘
```

- Admin page (`/admin`) adds a "Founder" tab in its navigation bar that links to `/admin/founder`.
- The dashboard does **not** introduce any new backend endpoints or mock data.
- Every tile either shows a real value or "—" if the underlying API does not expose the metric.

## Interpretation

- **Online Now** = count of registered users, not real-time WebSocket presence. Use Grafana + Prometheus for true concurrent user monitoring.
- **Error Rate** = based on audit log action keywords ("error", "fail"), not actual error counts from server logs. A 0% error rate may still have server-side errors not captured in the audit trail.
- **Prometheus / Grafana health** = direct HTTP checks to localhost. In production these will likely be unreachable from the browser (unless exposed via reverse proxy). Treat "unreachable" as normal for frontend-only access.
