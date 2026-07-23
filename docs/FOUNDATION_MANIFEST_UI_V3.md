# FOUNDATION MANIFEST — UI v3 Terminal Redesign

## 1. Frontend Framework State

| Property | Value |
|----------|-------|
| Next.js | 14.1.0 |
| Router | App Router (`app/` directory) |
| React | 18.x |
| TypeScript | strict |
| Styling | Flat CSS files (no Tailwind, no CSS-in-JS) |
| CSS structure | `styles/tokens.css` + `styles/components.css` → imported via `app/globals.css` |
| Fonts (current) | Inter (body/display) + JetBrains Mono (mono) via `<link>` in `layout.tsx` |
| Fonts (target) | Outfit (display) + DM Sans (body) via `next/font/google` |

**Current tokens differ from mockup** — existing `:root` uses `--bg: #0f1419` (dark blue), mockup uses `--bg: #050508` (near-black). Will override in terminal-specific scope.

## 2. WebSocket Client

**File**: `lib/use-market-data.tsx`

| Property | Value |
|----------|-------|
| Auth | Cookie-based (httpOnly `tm_session`, SameSite=none) |
| URL | Derived from `NEXT_PUBLIC_API_URL`, swapping http→ws, appending `/api/v1/marketdata/ws` |
| Auto-reconnect | Yes, 3s delay via `setTimeout` on close |
| Tick buffer | Batched 200ms flush via `setInterval` |
| Subscribe | `ws.send(JSON.stringify({ action: 'subscribe', symbols: [...] }))` |
| Unsubscribe | `ws.send(JSON.stringify({ action: 'unsubscribe', symbols: [...] }))` |
| Start feed | `POST /marketdata/feed/start` → sets mode (simulator|broker) |
| Stop feed | `POST /marketdata/feed/stop` |

**Tick message schema** (from `TickData` interface):

```typescript
interface TickData {
  symbol: string
  last_price: number
  bid: number
  ask: number
  bid_qty: number
  ask_qty: number
  volume: number
  oi: number
  change: number
  change_pct: number
  timestamp: string
  exchange: string
}
```

**Usage**: `const { ticks, connected, feedMode, subscribe, unsubscribe, startFeed, stopFeed } = useMarketData()`

## 3. API Client

**File**: `lib/api.ts`

| Property | Value |
|----------|-------|
| Base URL | `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000/api/v1`) |
| Auth | Cookie-based (`tm_session` httpOnly) + CSRF header (`X-CSRF-Token`) |
| CSRF | Loaded from `csrf_token` cookie, auto-bootstrapped via `GET /auth/csrf` |
| Methods | `api.get<T>(path)`, `api.post<T>(path, body)`, `api.put<T>(path, body)`, `api.patch<T>(path, body)`, `api.delete<T>(path)` |
| Error | `ApiError(status, message)` thrown on non-OK responses |

## 4. Relevant API Endpoints (found in codebase)

### Positions
```
GET /engine/positions → { positions: Position[] }
GET /engine/funds → { funds: { total_margin, used_margin, available_margin, broker } }
```

### Orders
```
GET /engine/orders → { orders: Order[] }
POST /engine/orders/{id}/cancel → { ... }
POST /engine/trade → { result: { success, message, ... } }
```

### Risk / Mode
```
GET /risk/live/status → { is_live: boolean }
POST /risk/live/enable → { message: "LIVE trading enabled" }  (body: { confirm: true })
POST /risk/live/disable → { message: "LIVE trading disabled" }
GET /risk/kill-switch → { kill_switch_enabled: boolean }
GET /risk/settings → { settings: RiskSettings[] }
```

### User Strategies
```
GET /user-strategies/ → { strategies: UserStrategy[] }
POST /user-strategies/{id}/deploy (body: { mode: "PAPER"|"LIVE" }) → { strategy_id, mode, results }
```

### Market Data
```
GET /marketdata/historical?symbol=X&interval=Y&days=Z → Candle[]
GET /marketdata/option-chain?symbol=X → { ... }
GET /marketdata/watchlist → { indices, stocks }
GET /marketdata/feed/start → { broker }
POST /marketdata/feed/stop → { ... }
```

### Engine Status
```
GET /engine/runs → { runs: Run[] }
```

### Analytics (not found — GAP)
No dedicated analytics/performance endpoint found. Dash uses inline data from positions.

### Market Brief / Scenario Narrative (not found — GAP)
No daily brief endpoint found.

## 5. Existing Terminal Route

**Path**: `app/terminal/page.tsx`
**Structure**: Single `'use client'` page with inline:
- Quick Order ticket (symbol, side, qty, type, product, price)
- Live quote ticker
- Positions table (5 cols: Symbol, Qty, Avg, P&L, Type)
- Orders table (7 cols + cancel action)
- Margin info card
- Auto-calls `startFeed()` on mount

**Builder sub-route**: `app/terminal/builder/page.tsx` — multi-leg strategy builder with deployment
**Option chain sub-route**: `app/terminal/option-chain/` — inline option chain display

## 6. Existing Types / Stores / Hooks

| Module | Export | Purpose |
|--------|--------|---------|
| `lib/auth-context.tsx` | `useAuth()` | User, tier, isAdmin, signin/signout |
| `lib/use-market-data.tsx` | `useMarketData()`, `MarketDataProvider` | Ticks, connected, feedMode, subscribe/unsubscribe |
| `lib/use-events.ts` | `useEvents()` | SSE execution events, subscribe(cb) |
| `lib/use-toast.tsx` | `useToast()`, `ToastProvider` | toast(type, message) |
| `lib/api.ts` | `api` | REST client with all endpoint methods |
| `styles/tokens.css` | CSS custom properties | Current design tokens |
| `styles/components.css` | CSS classes | `.t-*` component classes (t-panel, t-btn, t-input, t-table, etc.) |

## 7. GAPS

| Missing | Impact | TODO |
|---------|--------|------|
| Performance/analytics endpoint (daily P&L, win rate, active strategies) | StatCards will use mock data | TODO(DATA): create `/analytics/daily-summary` endpoint |
| Daily market brief / scenario narrative endpoint | MarketPulse card needs it | TODO(DATA): create `/ai/daily-brief` endpoint |
| OI ladder / option chain per-strike data | OILadder needs structured strike data | Use existing `/marketdata/option-chain` if available |
| Platform strategy run state (RUNNING/WAITING/PAUSED + live P&L) | StrategyDeck needs live state | TODO(DATA): add live status to user-strategies endpoint |
| Live MTM computed per-position from WS | Can compute client-side from ticks × position qty | Already partially done in existing terminal |
| Design mockup uses Outfit + DM Sans | Must switch from Inter + JetBrains Mono | Load via `next/font/google` |

## 8. Design Tokens Mapping

```
mockup :root          → current tokens.css     → action
--bg: #050508         → --bg: #0f1419           → Override in terminal scope
--panel: rgba(255,255,255,.032) → --panel: rgba(255,255,255,.03) → Close, use mockup value
--line: rgba(139,92,246,.16)  → --border: rgba(255,255,255,.08)  → Add mockup token
--violet: #8b5cf6     → --violet: #7c5cfc       → Use mockup value #8b5cf6
--cyan: #22d3ee       → --cyan: #00d4ff         → Use mockup value #22d3ee
--green: #34d399      → --green: #22c55e        → Use mockup value
--red: #f87171        → --red: #ef4444          → Use mockup value
--amber: #fbbf24      → --amber: #f59e0b        → Use mockup value
--text: #eceaf4        → --text: #ffffff         → Use mockup value
--dim: #9995b3         → --text-sub: #a1a5b3     → Use mockup value
--faint: #5b5875       → --text-faint: #5f6368   → Use mockup value
--radius: 16px         → --radius-xl: 16px       → Add as --radius
--font-display: 'Outfit'  → --font-display: 'Inter' → Change to Outfit
--font-body: 'DM Sans'    → --font-sans: 'Inter'    → Change to DM Sans
```
