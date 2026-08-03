# Paper Trading UI — Design & Roadmap (2026-08-03)

## Goal

Deliver the 🧪 **Paper Trading** milestone on the roadmap (after Broker SDK ✅ and
Execution Engine ✅): an end-to-end user-facing workflow —

create a strategy → start paper trading → watch live positions and P&L update
in real time → review completed trades → stop or restart seamlessly.

Principles: **correctness, usability, observability** first; reuse the frozen
Broker SDK and the Execution Engine; **no new infrastructure** (no new stores,
no new streams infrastructure — reuse the existing per-user SSE
`/api/v1/events/stream`).

## Current state (verified)

- Execution Engine v1.0 deployed (commit `c7dfdf4`): typed domain bus,
  TradeManager ledger, PositionManager (event-driven netting), PnL Engine,
  Portfolio Engine, facade; legacy bridge wired (fix `4278f42`). Engine state
  is **process-local in-memory** (known limitation: no durable replay).
- Strategy runtime: `builder` (create/validate/ready/deploy/start/stop), graph
  runner (`start_graph_strategy`, `stop_graph_strategy`,
  `get_runtime_dashboard`) — order path routes through OMS (frozen SDK).
- Fills reach the engine: OMS `OrderCompleted` / `PaperOrder*` → legacy bridge
  → typed bus → trade → position → PnL → portfolio chain.
- Live updates infra already exists: `/api/v1/events/stream` (SSE, cookie-auth,
  per-user filter) + `apps/web/lib/use-events.ts` hook.
- Frontend has `/strategies` (deploy wizard, runtime dashboard, logs, score)
  but **no live positions/P&L view and no closed-trades review** for the
  engine, and no single paper-trading workspace.

## Design

### Backend (additive, read-mostly)

1. **Engine → SSE bridge** (`execution_engine/events.py::bridge_engine_events`)
   — forwards typed-bus TRADE/POSITION/PORTFOLIO events onto the legacy bus so
   the existing per-user `/events/stream` delivers live canonical events.
   Loop-safe: engine event names (`trade.executed`, `position.updated`,
   `portfolio.revalued` …) are not in the legacy→engine `_TYPE_MAP`, so the
   forward bridge drops them on the way back. Idempotent module flag, wired in
   `init_execution_engine()` (no new infrastructure — same bus, same endpoint).
2. **Read-only paper endpoints** `routes/v1_paper.py` (prefix `/paper`,
   auth-gated, scoped to `current_user.id`, broker filter `paper`):
   - `GET /paper/status` — engine wiring observability (bridge wired, bus
     running, subscriber counts) for the UI's live badge.
   - `GET /paper/account` — P&L account (equity, realized, unrealized, daily,
     peak, drawdown).
   - `GET /paper/positions` — engine positions for the paper broker.
   - `GET /paper/trades?limit=` — closed fills from the engine ledger.
   - `GET /paper/portfolio` — portfolio snapshot aggregates.
3. **Correctness fix**: `get_runtime_dashboard()` is not user-scoped — any
   authenticated user sees every running strategy. Verified defect; scope
   runtime stats by `user_id` (runner records it at start) and filter the
   dashboard (`/builder/dashboard` + new `/paper/strategies`) to the caller.
4. **No schema / no config / no new deps.** Engine stays in-memory; empty
   states documented (state resets on API restart until durable store §4).

## §7 — Runtime persistence + recovery (implemented)

Engine state is durable across API restarts via `execution_engine/persistence.py`
+ the `execution_checkpoints` table (Supabase):

- **What is checkpointed (minimum required runtime state):** per user, open
  positions + FIFO lots (`FifoLots.to_lots`) + P&L accounts, written after
  every portfolio rebuild (coordinator subscribes to the canonical
  `PORTFOLIO_SNAPSHOT` event); plus each **running** graph strategy's restart
  spec (user, symbol, interval, paper/live), written on start and removed on
  stop. A per-user SHA digest skips writes when nothing changed.
- **Recovery** (`recover_runtime_state`, called in `main.py` lifespan at
  startup): restores engine accounting state first (replace-in-place, no event
  replay), rebuilds the portfolio snapshot, then re-starts every persisted
  running strategy (idempotent `already_running` guard). Fail-open: a broken
  store/DB never blocks startup.
- **Deterministic**: canonical JSON round-trip (pydantic `model_dump` /
  `model_validate`); verified byte-identical in `test_runtime_recovery.py`.
- **Tests**: 8 automated restart tests (determinism, idempotency, hash-guard,
  no-store no-op, strategy persist/recover/delete, event-writer path).
- **Backend**: Supabase store injected at startup; tests use
  `InMemoryCheckpointStore`, so the engine stays I/O-free without one.

### Frontend (usability)

5. **New `/paper` page** — "Paper Trading" workspace (sidebar under *Trade*):
   - Strategy selector + Start Paper / Stop / Restart (reuses
     `api.builder.deploy` / `start` / `stop`; restart = stop + start).
   - Live account cards (Equity / Realized / Unrealized / Daily P&L).
   - Open positions table (qty, avg entry, realized, unrealized).
   - Closed trades table (time, symbol, side, qty, price, charges, strategy).
   - Running-strategies panel (candles/signals/orders/filled/rejected/errors).
   - Live updates: existing `useEvents()` SSE hook (`*` → debounced refetch)
     + 3s polling fallback + connection badge (live / polling / offline).
   - Entry points: `?strategy=<id>` deep link from `/strategies` rows.
6. `lib/api.ts` — `paper` client group (5 GETs).

## Reuse / gaps

| Need | Source |
|---|---|
| Create/validate/ready strategy | existing `builder` API + UI |
| Deploy paper + start runner | existing `builder.deploy` (`mode=paper`) |
| Stop / restart | existing `builder.stop` / `start` |
| Live events | existing `/events/stream` + `useEvents()` (back-bridged) |
| Positions / P&L / trades | new `/paper/*` (engine state, read-only) |
| Durability across API restart | `execution_checkpoints` table + `execution_engine/persistence.py` (see §7) |

## Testing & rollout

- API: new `tests/test_v1_paper.py` (auth gate, account/positions/trades/
  portfolio after injected fills, status wiring, dashboard scoping);
  full regression `pytest tests/` must stay green.
- Web: `tsc --noEmit` + prod build.
- Deploy: hot-deploy API files + web `.next`; prod smoke: run engine smoke
  gate, then curl `/paper/*` with an injected fill and verify live numbers,
  then browser-level check via puppeteer E2E.
