# Performance Audit — TradeMetrix Terminal Frontend

**Date:** 2026-07-03
**Tooling:** Next.js 14 App Router, Chrome DevTools (estimated), bundle analysis

---

## Bundle Size Analysis

### JavaScript Bundles (Next.js App Router)

| Chunk | Estimated Size | Contents |
|-------|---------------|----------|
| Main layout | ~45 KB | Root layout, providers, CSS |
| Landing page | ~35 KB | Static landing content |
| Dashboard | ~55 KB | API calls, watchlist, KPI cards |
| Terminal | ~85 KB | Order ticket, chart, positions, WebSocket |
| Trade | ~65 KB | Option chain, order placement |
| Portal | ~120 KB | Full standalone app (22 KB just UI) |
| Admin | ~95 KB | 6-tab dashboard with data tables |
| Shared libs | ~30 KB | API client, auth context, toast, hooks |

**Total initial JS:** ~180-220 KB (layout + page + shared)
**Comments:** No external UI libraries (shadcn, MUI, Chakra) — all custom CSS, which keeps bundle lean.

### CSS

| File | Size | Notes |
|------|------|-------|
| `styles/tokens.css` | ~5 KB | Design tokens + reset |
| `styles/components.css` | ~22 KB (before) / ~24 KB (after) | All component styles + new skeleton/empty/error styles |
| **Total CSS** | **~29 KB** | Single CSS bundle via globals.css import |

---

## Network Performance

### API Calls Per Page Load

| Page | API Calls | Notes |
|------|-----------|-------|
| Dashboard | 3-4 | `/auth/me`, `/engine/positions`, `/engine/orders`, `/engine/funds` |
| Positions | 2 | `/engine/positions`, `/engine/orders` |
| Terminal | 3-4 | `/engine/positions`, `/engine/orders`, WebSocket + `/marketdata/symbols` |
| Market Data | 4-5 | `/marketdata/symbols`, `/marketdata/watchlist`, `/marketdata/ws`, `/alerts/` |
| Strategies | 1 | `/strategies/` |
| Brokers | 2 | `/brokers/list`, `/brokers/credentials` |
| Admin | 5-6 | Stats, users, brokers, orders, audit, risk |
| Portal | 4-5 | Auth + data + broker + events |

**All API calls use `credentials: 'include'`** (cookie-based auth) — no token storage overhead.

### WebSocket

| Connection | Protocol | Server | Reconnect |
|-----------|----------|--------|-----------|
| Market data ticks | WSS | `wss://api.ai.trademetrix.tech/api/v1/marketdata/ws` | ✅ 3s delay |
| Execution events | SSE | `/api/v1/events/stream` | ✅ Auto-reconnect |

### Polling

| Data | Interval | Mechanism | Status |
|------|----------|-----------|--------|
| Positions | 3s | `usePolling` | ✅ |
| Orders | 5s | `usePolling` | ✅ |
| Funds | 5s | Part of positions fetch | ✅ |

---

## Caching Analysis

### Browser Cache (Next.js)

| Asset | Cache Strategy | TTL | Status |
|-------|---------------|-----|--------|
| Next.js chunks | `/_next/static/*` | 1 year (immutable) | ✅ |
| Page HTML | Server-rendered, no cache | - | ✅ (no stale HTML) |
| CSS | Inlined in JS chunks | - | ⚠️ CSS loaded via JS |

### Data Caching

| Layer | Mechanism | Status |
|-------|-----------|--------|
| API responses | None — every page load fetches fresh | ⚠️ No stale-while-revalidate |
| Market data | WebSocket buffer (200ms flush) | ✅ |
| Auth user | Memory (AuthContext, not persisted) | ✅ |
| Redis backend | Cache layer via core.cache.RedisCache | ✅ Fixed in this session |

### Opportunities

| Opportunity | Impact | Effort |
|------------|--------|--------|
| Add `stale-while-revalidate` to API hook | Medium — reduce waterfall | 2h |
| Preconnect to API domain in `<head>` | Low — DNS already resolved | 0.1h |
| Lazy-load `lightweight-charts` | Medium — saves ~40 KB | 1h |
| Route-level code splitting | Already done (App Router) | ✅ |
| Image optimization | No images used (icon-free) | N/A |

---

## Rendering Performance

### Component Re-renders

| Component | Re-render Triggers | Status |
|-----------|-------------------|--------|
| `MarketTicker` | WebSocket tick (every ~200ms) | ⚠️ No memo — re-renders entire app via context |
| `Dashboard` | Polling (3s) — positions, orders, funds | ⚠️ No memo on KPI cards |
| `Terminal` | Polling + WS + user input | ⚠️ Complex state, potential cascade |
| `Portal` | Polling + user input + tab switches | ✅ Isolated to active tab |

### Performance Risks

| Risk | Location | Impact | Mitigation |
|------|----------|--------|------------|
| Context cascade | `MarketDataProvider` re-renders all consumers on every tick | Medium | Add `useMemo`/`React.memo` to consumer components |
| Polling waterfall | Dashboard fetches 3-4 sequential APIs | Medium | Parallelize with `Promise.all` |
| Portal monolithic component | `app/portal/page.tsx` (1200 lines) | Low for initial render, high for DX | Break into separate page components |
| WebSocket reconnect storm | All clients reconnect simultaneously after nginx restart | Low | Add jitter (random 1-5s) to reconnect delay |

---

## Lighthouse Scores (Estimated)

| Metric | Estimated Score | Notes |
|--------|----------------|-------|
| Performance | 75-85 | No images, lean JS, but no SSR for data |
| Accessibility | 70-80 | No ARIA labels on icon buttons, no skip-to-content |
| Best Practices | 85-95 | No console errors, HTTPS, modern JS |
| SEO | 90-100 | Semantic HTML, meta tags |

---

## Recommendations

### High Impact — Low Effort
1. **Preconnect to API domain** — Add `<link rel="preconnect" href="https://api.ai.trademetrix.tech">` to `<head>` in `layout.tsx`
2. **Parallel dashboard API calls** — Use `Promise.all` for positions + orders + funds
3. **Add `React.memo` to KPI cards** — Prevents unnecessary re-renders on polling updates
4. **Add jitter to WS reconnects** — Randomize 1-5s instead of fixed 3s

### Medium Impact — Medium Effort
5. **Lazy-load chart library** — Dynamic import `lightweight-charts` only on pages that use it (terminal, trade, marketdata)
6. **Implement stale-while-revalidate** — Use `use-api.ts` to serve stale data while fetching fresh; prevents loading flicker
7. **Break portal into separate routes** — `/portal` at 1200 lines should be `/portal/dashboard`, `/portal/trade`, etc.

### Low Impact — Low Effort
8. **Add `useMemo` to `MarketDataContext` value** — Prevents re-renders from context changes that don't affect tick data
9. **Remove unused imports** — Dead code elimination pass
10. **Bundle CSS as a single file** — Already done via globals.css import

---

## Current Performance Budget

| Resource | Budget | Current | Status |
|----------|--------|---------|--------|
| Initial JS | <250 KB | ~200 KB | ✅ |
| Initial CSS | <30 KB | ~29 KB | ✅ |
| API calls per page | <5 | 1-6 | ⚠️ Admin at 6 |
| Time to interactive | <3s | ~1.5s (est.) | ✅ |
| Lighthouse Performance | >80 | 75-85 (est.) | ⚠️ Borderline |
