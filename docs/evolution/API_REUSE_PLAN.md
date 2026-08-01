# API_REUSE_PLAN.md

Backend is LOCKED. Every UI phase reuses existing endpoints via the canonical client
`lib/api.ts` (cookie auth + CSRF auto-attached). No new backend routes are required
for Phases 1–7.

## Canonical client
- `lib/api.ts` — `api.get/post/put/patch/delete` + namespaces; CSRF bootstrap eager on
  load; 403 → refresh + retry once. All new components use this client only.
- Absolute base: `NEXT_PUBLIC_API_URL` (prod `https://api.ai.trademetrix.tech/api/v1`).

## Phase 1 endpoint usage (Quick Order Drawer)

| Need | Endpoint (existing) | Notes |
|---|---|---|
| Submit order | `POST /engine/trade` (`api.engine.trade`) | Payload: symbol, exchange, side, order_type, product, quantity, price, instrument_type, strike_price, expiry_date, option_type, is_paper, source=`quick_order`. Engine path now routes through OMS + auto-bracket (SL/Target auto-attached on fill). |
| Invalidate after fill | `['orders']`, `['positions']` | `useExecuteTrade` mutation (E) already invalidates. |
| Live LTP | WS tick store (`useMarketData`) | Subscribe symbol on drawer open; fall back to quote on open if no tick yet. |
| Margin preview | `POST /margin-estimate/` (`api.marginEstimate`) | Leg-form body: `{index_symbol, legs:[{segment:'options', position:'buy', lots, option_type, expiry, strike_criteria:'atm_offset', strike_value}]}`. For EQ: client-side `qty × price`. |
| Charges estimate | — (no API) | Client-side labeled estimate: STT (0.1% options / 0.025% futures), exchange (0.05%), GST 18% on fees, SEBI ₹10/cr, stamp 0.003%. Shown as "estimated". |
| Broker funds | `GET /engine/funds` (`useFunds`) | Margin bar background. |
| Position context | `GET /engine/positions` (`usePositions`) | Optional: show current position qty in drawer. |

## Phase 2 (Watchlist)

| Need | Endpoint (existing) |
|---|---|
| Server watchlist seed | `GET /marketdata/watchlist` (`api.marketdata.watchlist`) → `{indices, stocks}` |
| Custom lists | localStorage (existing pattern `tm_watchlist_custom`) — no backend change |
| Alerts | `api.alerts.*` (existing bell flow) |
| Option chain from row | `GET /marketdata/option-chain?symbol=` (`api.marketdata.optionChain`) |
| Historical for sparkline | `GET /marketdata/historical` (`api.marketdata.historical`) |

## Phase 3 (Analyzer)
- Indicators/historical: `api.marketdata.historical` (reuse `components/chart.tsx`).
- Option chain/PCR/max pain: `api.market.optionChain` + `api.marketdata.optionChain`
  (existing terminal/option-chain page already consumes them).
- AI summary: `api.ai.chat` (existing /ai page pattern).
- Search: `GET /market/instruments?query=` (existing app-layout ⌘K pattern).

## Phase 4 (Strategy Builder)
- Blocks/categories/validate/compile/preview/publish/templates:
  `api.builder.*` (all existing — visual canvas at app/strategies/builder already uses them).

## Phase 5 (Backtest)
- `api.backtest.run/get/list/strategies` (existing). `BacktestResultsData` already
  carries slippage/brokerage/STT/exchange — no backend work.

## Phase 6 (Dashboard)
- `useOrders/usePositions/useFunds/useRuns`, `api.engine.positions/funds`,
  `api.marketdata.watchlist`, `api.alerts.list` — all existing.

## Phase 7 (Performance)
- Pure client: react-query tuning, memoization, virtualization, WS batching (existing).

## Rules
1. No new fetch wrappers — always `lib/api.ts` or existing hooks.
2. Do not copy raw-fetch patterns from admin tabs (relative `/api/v1/...`) into user UI.
3. Keep query keys/invalidation consistent with `lib/queries/*`.
