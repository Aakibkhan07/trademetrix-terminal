# Release Notes — Execution Engine v1.0 (2026-08-03)

## Summary

The Execution Engine is a new, canonical, event-driven execution layer
(`apps/api/execution_engine/`) composed on top of the **frozen Broker SDK v2**.
It formalizes the existing OMS → Execution → Paper → Portfolio → Risk stack
under one typed domain bus and fills the genuinely missing pieces: a formal
fills ledger, event-driven position netting with FIFO realized P&L, a P&L
engine with equity/drawdown, portfolio snapshots, canonical typed lifecycle
events, a legacy bridge, and Prometheus execution metrics.

## Added

- **`execution_engine/events.py`** — canonical typed bus: 6 domains
  (`order`/`execution`/`trade`/`position`/`portfolio`/`risk`), 24 typed events,
  thread-safe publish (`call_soon_threadsafe` when started; deterministic
  inline dispatch pre-startup with cascade draining), single async FIFO
  dispatcher, sequence + correlation ids, 2000-event ring buffer,
  `LoggingSink`, and `bridge_legacy_events()` (legacy string bus → canonical).
- **`execution_engine/state_machine.py`** — canonical `OrderState` (12 members
  incl. `FAILED`; `PARTIAL` legacy alias) + authoritative
  `STATE_TRANSITIONS` superset; `normalize()`, terminal/active helpers,
  `OrderStateMachine`.
- **`execution_engine/fifo.py`** — thread-safe FIFO lot engine:
  `apply(side, qty, price)` → realized P&L (positive = profit, both legs),
  reversal → opposite lot, VWAP snapshots, unrealized P&L.
- **`execution_engine/trades.py`** — `TradeLedger` (in-memory, capped per
  account) + optional `TradeStore` protocol; `TradeManager` records every fill
  and publishes `trade.executed`.
- **`execution_engine/positions.py`** — event-driven `PositionManager`: signed
  net positions per (user, broker, symbol), FIFO realized P&L, VWAP averages,
  mark-to-market, `position.opened/updated/closed` events.
- **`execution_engine/pnl.py`** — `PnLEngine`: per-account realised/
  unrealised/daily (IST window)/equity/peak/drawdown; recomputes from
  PositionManager (no drift); publishes `portfolio.revalued` incl.
  `open_positions`.
- **`execution_engine/portfolio_engine.py`** — `PortfolioEngine`:
  full-portfolio snapshots, optional `SnapshotStore`; publishes
  `portfolio.snapshot`; immune to its own snapshots (no fanout loops).
- **`execution_engine/engine.py`** — `ExecutionEngine` facade: `submit` with
  idempotency + canonical lifecycle events (order.submitted → outcome →
  execution.result), `cancel`/`modify` delegating to OMS; injectable gateway
  (default `engine.gate.execute_order`).
- **`execution_engine/metrics.py`** — Prometheus sink: order event counters,
  per-broker filled/partial/rejected/cancelled/failed, pending gauge, trades,
  risk decisions, per-broker P&L/equity/drawdown/open-positions gauges.
- **`execution_engine/init.py`** — `init_execution_engine(loop)` wires the
  whole chain (ORDER → TRADE → POSITION → PORTFOLIO_REVALUED →
  PORTFOLIO_SNAPSHOT), metrics + legacy bridge; `shutdown_execution_engine()`;
  `reset_execution_engine()` test hook. Called from `main.py` lifespan.
- **Legacy composition** — `portfolio/manager.py` `refresh()` now mirrors
  broker-truth state onto the canonical bus (`portfolio.snapshot`,
  `source: portfolio_manager`) — additive and fail-open.

## Fixed during build

- Infinite `portfolio.snapshot` fanout (PortfolioEngine reacting to its own
  snapshots) — now skips `PORTFOLIO_SNAPSHOT` self-events.
- Duplicate ring-buffer entries (`_finalize` run twice by publish paths) —
  now idempotent.
- FIFO realized P&L sign inversion on both the SELL-against-longs and
  BUY-against-shorts branches — closing above entry now realizes a profit.
- Duplicate `portfolio.snapshot` per fill — PortfolioEngine subscribes to the
  PORTFOLIO domain only.
- Inline-dispatch race: `apublish` now drains fire-and-forget cascade tasks,
  making `await apublish(...)` fully deterministic pre-startup.
- `EXECUTION_RESULT` KeyError on non-fill statuses (`filled_quantity` not set).
- Metrics label for `open_positions` — now carried on per-broker
  `portfolio.revalued` events.

## Verification

- New tests: `tests/test_execution_engine.py` (**40 tests**) — state machine,
  FIFO, bus (inline/started/thread-safe), trade ledger, position lifecycle,
  P&L/portfolio chain (FIFO round-trip = 267.5, equity peak/drawdown,
  no-self-trigger regression), facade outcomes, metrics, bootstrap, legacy
  composition.
- Full regression: `pytest tests/` → **756 passed, 1 xfailed**
  (baseline 717 for v1.3.1; +39 new).

## Known gaps (tracked, not regressions)

- Durable persistence for the fills ledger and portfolio snapshots is behind
  `TradeStore`/`SnapshotStore` protocols — a Supabase adapter is not wired yet
  (the legacy `orders` audit table remains the durable trail).
- `oms/state_machine.py` and `execution/models.py` still carry their legacy
  transition tables; they are not yet delegating to the canonical machine
  (deliberately deferred to keep the regression surface frozen).
- Paper engine and strategy-runtime formalization is out of scope for v1.0.
