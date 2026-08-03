# Known Limitations — Execution Engine v1.0 (2026-08-03)

Verified behavioral gaps that are **by-design today** and are tracked for a
future release. None of these caused a harness failure; none is a regression
against the current production data model. Each entry lists the observation,
the reason it is acceptable today, and the remediation path.

## 1. No per-account position/trade isolation

Positions are keyed `(user_id, broker, symbol)` (`positions.py:_key`) and the
trade ledger `(user_id, broker)` (`trades.py:_key`) — the `account` field is
recorded on positions/trades but is **not part of any key**. Two fills for the
same user+broker+symbol under different `account` values net into one position
(audit harness: two accounts × 10 qty → position 20).

- **Why acceptable today:** the credential model stores one broker account per
  (user, broker); a user's two different brokers are already isolated by the
  broker dimension. Multi-account-per-broker is not reachable in production.
- **Remediation:** extend keys to `(user_id, broker, account, symbol)` /
  `(user_id, broker, account)` when multi-account broker support lands; update
  the facade docstring claim "multi-account ... by construction" accordingly
  (`engine.py` currently scopes by user + broker only).

## 2. No fill-ack idempotency in the engine

`TradeManager._on_order_event` records a trade for every `order.filled` /
`order.partially_filled` event; an identical replayed ack double-counts
(audit harness: re-acked 10 qty → position 85 instead of 75). The engine
consumes at-least-once with no dedup key.

- **Why acceptable today:** production producers are effectively at-most-once —
  OMS fills are emitted once per terminal transition, guarded by
  `state_machine.can_transition` (direct path `oms/manager.py:458-479`) and the
  reconcile path (`_apply_remote_status` early-returns when the transition is
  illegal, `oms/manager.py:581`); the engine bridge forwards each legacy event
  exactly once. No production path emits a duplicate fill today.
- **Remediation:** dedup on `(order_id, filled_quantity, avg_price)` in
  `TradeManager._build_trade` if any producer ever gains replay semantics
  (e.g. broker WS reconnect replay).

## 3. Trade ledger is an in-memory, capped ring

`TradeLedger` keeps the most recent 20,000 trades per (user, broker) bucket and
`list()` defaults to the last 1,000 rows. Older fills are evicted; full history
is not reconstructable from the engine.

- **Why acceptable today:** the legacy `orders` audit table (Supabase) is the
  durable trail; the ledger is the formal fills book for live state, and the
  cap bounds memory (verified: 10k-fill stress kept buckets well under cap with
  zero ledger↔position divergence).
- **Remediation:** wire a Supabase `TradeStore` adapter (protocol already in
  `trades.py`).

## 4. Durable stores behind protocols, not wired

`TradeStore` (trades) and `SnapshotStore` (portfolio) exist as protocols; no
Supabase adapter is attached. Restart loses engine-side fill/snapshot history
(position state rebuilds only from events arriving after boot).

- **Why acceptable today:** position/ledger state is derived; the OMS recovers
  active orders from `oms_orders` on startup and re-emits lifecycle events, so
  engine state converges after boot without a store.
- **Remediation:** implement `TradeStore`/`SnapshotStore` adapters; backfill
  from the `orders` audit table on init.

## 5. Bus ordering is per-publisher, not global

Sequence ids are assigned under lock at publish time; dispatch follows queue
order. With multiple producer threads, delivery order can invert relative to
sequence (audit harness: single-publisher FIFO is strict — 5000/5000, 0
out-of-order; 4-thread storm delivered 20k with 0 dups but cross-thread
interleaving is expected). Consumers must not assume sequence == delivery order
across publishers.

- **Why acceptable today:** per-key ordering (one order's lifecycle) is
  deterministic — a single order is published from one thread; the dispatcher
  awaits handlers in FIFO order.
- **Remediation:** document, or partition dispatch per correlation id if a
  consumer ever needs global ordering.

## 6. Pre-startup / post-shutdown thread publishes drop async handlers

Before `execution_bus.start()` (or after `stop()`), a `publish()` from a
non-loop thread dispatches inline; async handlers have no running loop in that
thread and are dropped with a warning ("bus not started"). Production runs the
bus started via `init_execution_engine`, so the window is only during
startup/shutdown.

- **Why acceptable today:** producers in production are loop-thread or
  marshalled (`call_soon_threadsafe`) while the bus is started; the drop is
  logged, never silent.
- **Remediation:** buffer-and-replay non-loop publishes when the bus is not
  started (or start the bus in the producer thread's loop).

## 7. Legacy OMS state machines not yet delegated

`oms/manager.py` / `execution/models.py` keep their own transition tables; they
do not delegate to the canonical `execution_engine.state_machine`. Deliberate
(deferred in v1.0 to keep the regression surface frozen); canonical and legacy
tables agree on the fill/reject/cancel semantics exercised in production.

## 8. Paper pending orders emit no engine `order.pending`

`PaperOrderPending` is now bridged to `order.pending` (release audit fix), but
the paper broker's resting-order path predates the engine and its full state
machine is not canonical. Non-blocking for v1.0.

## 9. Single-process bus

The canonical bus is in-process; it does not span uvicorn workers. Multi-worker
deployments would require each worker's engine to be fed by a shared transport.
Current production runs a single API process, so this is consistent with the
OMS queue behavior (also single-process; see AGENTS.md session notes).
