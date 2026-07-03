# Architecture

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         traefik (proxy)                     │
│  *.trademetrix.tech → 443 → backend container              │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI (apps/api — port 8000)                 │
│                                                             │
│  /api/v1/*          → route handlers                       │
│  /ws/*              → WebSocket (market data)              │
│  /admin/*           → SSR admin pages (jinja2)             │
│                                                             │
│  Middleware:                                                │
│    • CORSMiddleware                                         │
│    • SessionMiddleware (csrf_token cookie)                  │
│    • CSRFCheck (skips GET/HEAD/OPTIONS + SAFE_PATHS)       │
│    • RateLimitMiddleware (Redis-backed, 60/30/10 per min)   │
│    • AuthenticationCheck (skips /auth/*, /public/*)         │
│                                                             │
│  Backing services:                                          │
│    • Supabase (auth + postgres)                             │
│    • Redis (OTP TTL, rate-limit counters, WS state)         │
│    • PostgreSQL direct (positions, orders, trades, logs)    │
│                                                             │
│  Market Data:                                               │
│    • MarketSimulator (24/7, 65 symbols, realistic prices)   │
│    • Broker feed (when OAuth'd, per adapter stream())       │
│    • AlertChecker (runs on ticks, fires notifications)      │
│    • DataSocket (WebSocket → clients)                       │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│           Next.js (apps/web — port 3000)                    │
│                                                             │
│  /              → Marketing landing page (server component) │
│  /portal/*      → Client trading portal                    │
│  /admin/*       → Admin control center                     │
│                                                             │
│  Data flow:                                                 │
│    • SSR: fetch() to FastAPI for initial page data          │
│    • WebSocket: use-market-data.tsx for live ticks          │
│    • API calls: lib/api.ts wrapper                          │
└─────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
trademetrix-terminal/
├── apps/
│   ├── api/                        # FastAPI backend
│   │   ├── main.py                 # App factory, middleware, router includes
│   │   ├── config.py               # Settings from env (pydantic)
│   │   ├── core/                   # Core services
│   │   │   ├── ratelimit.py        # Redis rate-limiter + middleware
│   │   │   ├── notifications.py    # Fast2SMS, Twilio, SMTP delivery
│   │   │   └── ...                 # (other core modules)
│   │   ├── brokers/                # Broker adapter layer
│   │   │   ├── base.py             # Abstract BaseAdapter
│   │   │   ├── registry.py         # Metadata for all 10 brokers
│   │   │   ├── factory.py          # Adapter lookup by broker name
│   │   │   ├── fyers_adapter.py    # Fyers (REST + WS)
│   │   │   ├── zerodha_adapter.py  # Zerodha (REST + HTTP polling stream)
│   │   │   ├── angelone_adapter.py # Angel One (REST + WS)
│   │   │   ├── dhan_adapter.py     # Dhan (REST + WS)
│   │   │   ├── upstox_adapter.py   # Upstox (REST)
│   │   │   ├── fivepaisa_adapter.py# 5Paisa (REST + HTTP polling)
│   │   │   ├── aliceblue_adapter.py# AliceBlue (REST)
│   │   │   ├── finvasia_adapter.py # Finvasia (REST)
│   │   │   ├── flattrade_adapter.py# FlatTrade (REST)
│   │   │   └── kotakneo_adapter.py # Kotak Neo (REST + WS)
│   │   ├── market/                 # Market data engine
│   │   │   ├── data_socket.py      # WebSocket manager (subscribe/broadcast)
│   │   │   ├── simulator.py        # Price simulator (24/7, realistic)
│   │   │   ├── alert_checker.py    # Evaluates alerts on each tick
│   │   │   └── shared_socket.py    # Singleton socket instance
│   │   ├── middleware/
│   │   │   ├── csrf.py             # CSRF protection
│   │   │   └── auth.py             # Auth check middleware
│   │   ├── routes/                 # API route handlers
│   │   │   ├── v1_otp.py           # OTP auth endpoints
│   │   │   ├── v1_brokers.py       # Broker CRUD + metadata
│   │   │   ├── v1_tradingview.py   # TradingView webhook
│   │   │   ├── v1_positions.py     # Positions + P&L
│   │   │   ├── v1_orders.py        # Order management
│   │   │   ├── v1_feed.py          # Market feed start/stop
│   │   │   ├── v1_admin.py         # Admin endpoints
│   │   │   ├── v1_alerts.py        # Price alerts CRUD
│   │   │   ├── v1_portfolio.py     # Portfolio data
│   │   │   └── v1_broadcast.py     # Broadcast messages
│   │   ├── models/                 # SQLAlchemy models
│   │   │   └── models.py           # All DB models
│   │   ├── services/               # Business logic
│   │   │   └── ...                 # (various service modules)
│   │   └── templates/              # Jinja2 admin templates
│   │       └── admin.html          # Admin control panel
│   │
│   └── web/                        # Next.js frontend
│       ├── app/
│       │   ├── page.tsx            # Marketing landing page
│       │   ├── layout.tsx          # Root layout
│       │   ├── portal/
│       │   │   ├── page.tsx        # Portal dashboard
│       │   │   └── ...             # (portal sub-pages)
│       │   └── admin/
│       │       └── page.tsx        # Admin control center
│       ├── components/
│       │   ├── app-layout.tsx      # App shell (header, sidebar, ticker)
│       │   ├── market-ticker.tsx   # Scrolling price ticker
│       │   ├── status-bar.tsx      # Connection status indicator
│       │   ├── sidebar.tsx         # Navigation sidebar
│       │   └── ...                 # (other components)
│       ├── lib/
│       │   ├── api.ts              # HTTP client wrapper
│       │   └── use-market-data.tsx  # WebSocket hook with buffering
│       └── styles/
│           └── components.css      # Shared styles
│
├── infra/
│   ├── production/
│   │   └── docker-compose.yml     # Production deployment
│   └── ...                         # (other infra configs)
│
└── scripts/                        # Utility scripts
```

## Data Flow

### Auth Flow
```
Client                    FastAPI                    Supabase/Redis
──────                    ──────                    ─────────────
 POST /auth/send-otp  →   generate 6-digit code
                          SHA256 hash → Redis (5min TTL)
                          deliver_otp() → SMS/Email/Console
                          ← { debug_otp (dev only) }
 POST /auth/verify-otp →  fetch hash from Redis
                          compare SHA256(input)
                          → Supabase Auth sign-in
                          ← { session, profile }
```

### Market Data Flow
```
Broker Adapter / Simulator
        │
        ▼
  shared_socket  (singleton, publishes ticks)
        │
        ├──▶ AlertChecker (evaluates rules, fires notifications)
        │
        └──▶ DataSocket (WebSocket → browser clients)
                 │
                 ▼
          use-market-data.tsx
           (200ms buffer → React state)
```

### Order Flow
```
Portal (BUY/SELL form)
        │
        ▼
  POST /api/v1/orders/place
        │
        ▼
  Broker Adapter.place_order()
        │
        ▼
  DB insert (orders table)
        │
        ▼
  WebSocket broadcast (position update)
```

## Key Design Decisions

1. **Simulator-first fallback**: If broker has no `access_token`, `start_market_feed` catches the RuntimeError and starts MarketSimulator instead. Portal always gets data.

2. **OTP stored in Redis**: SHA256 hashes with 5-min TTL — no DB migration, auto-expiry, no cleanup needed.

3. **Broker metadata registry**: `/brokers/registry.py` centralizes all broker-specific UI info (field labels, auth types, OAuth URLs). Frontend renders dynamically from `GET /metadata` — adding a broker needs no frontend changes.

4. **Tick buffering**: WebSocket data arrives at high frequency; `use-market-data.tsx` buffers in a `useRef` and flushes to state every 200ms to avoid React re-render storms.

5. **Feed lifecycle**: `start_market_feed` always stops existing feed and alert checker before starting — prevents zombie tasks. Alert checker subscribes via `shared_socket.subscribe("*")` and starts/stops with the feed.

6. **Broker adapter stream()**: WebSocket-capable brokers (Fyers, Angel, Dhan, KotakNeo) use `websockets` library; others (Zerodha, 5Paisa) fall back to HTTP polling — works with existing dependencies, no extra installs.

7. **verify-otp profile creation**: Fetches ALL Supabase Auth users, filters client-side by exact email match, then upserts profile by auth user ID. Handles the case where Auth user exists but profile is missing.

8. **`save_credentials` flexible mapping**: Accepts `api_key`, `client_id`, `client_code`, `access_token` — auto-maps to stored fields. Frontend can send whatever field name the broker metadata defines.

## Security

- **CSRF**: Double-submit cookie pattern. `csrf_token` cookie set on login; all POST/PUT/DELETE requests must include `X-CSRF-Token` header matching the cookie.
- **Session**: `tm_session` cookie (httponly, secure, samesite=none). Validated against Redis on each request.
- **Rate limiting**: Redis-backed sliding window. 60 req/min for auth, 30 for general, 10 for sensitive endpoints.
- **OTP**: SHA256 hashed before storage; plaintext never persisted. 5-min TTL enforced by Redis.
- **Credentials**: Broker API keys encrypted at rest (`encrypted_api_key` / `encrypted_secret_key` / `encrypted_access_token` columns).

## Routes Quick Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /auth/send-otp | No | Send OTP to email |
| POST | /auth/register-with-otp | No | Register + send OTP |
| POST | /auth/verify-otp | No | Verify OTP, get session |
| POST | /auth/logout | Yes | Destroy session |
| GET | /brokers/metadata | No | Broker field definitions |
| GET | /brokers/credentials | Yes | List saved broker connections |
| POST | /brokers/save-credentials | Yes | Save/update broker credentials |
| POST | /brokers/remove/{id} | Yes | Remove broker connection |
| POST | /brokers/{broker}/authorize | Yes | Get OAuth authorize URL |
| POST | /brokers/{broker}/callback | Yes | Handle OAuth callback |
| POST | /feed/start | Yes | Start market data feed |
| POST | /feed/stop | Yes | Stop market data feed |
| GET | /feed/status | Yes | Feed + alert checker status |
| GET | /positions | Yes | Current positions + P&L |
| GET | /orders | Yes | Order history |
| POST | /orders/place | Yes | Place new order |
| GET | /portfolio | Yes | Portfolio summary |
| POST | /alerts/create | Yes | Create price alert |
| GET | /alerts/list | Yes | List user's alerts |
| POST | /alerts/toggle/{id} | Yes | Enable/disable alert |
| POST | /alerts/delete/{id} | Yes | Delete alert |
| POST | /admin/kill-switch | Admin | Emergency stop |
| GET | /admin/users | Admin | List all users |
| GET | /admin/trades | Admin | All trades view |
| GET | /admin/audit-log | Admin | Activity audit trail |
| GET | /admin/risk | Admin | Risk metrics |
| POST | /broadcast/send | Admin | Send broadcast to users |
| POST | /admin/user/{id}/assign-broker | Admin | Assign broker to user |
| GET | /journal/entries | Yes | Get trade journal entries |
| POST | /journal/save | Yes | Save trade journal entry |
