"""Paper order persistence has to actually write.

## The bug

`PaperBroker._persist_order` upserted with `on_conflict="user_id,client_order_id"`. `orders`
carries that pair as a **partial** unique index:

    CREATE UNIQUE INDEX idx_orders_client_order_id ON public.orders
        USING btree (user_id, client_order_id) WHERE (client_order_id <> ''::text)

Postgres infers a conflict target from a partial index only if the statement reproduces the index
predicate, and supabase-py has no way to send one. Every call therefore failed:

    Failed to persist paper order: {'code': '42P10', 'message': 'there is no unique or exclusion
    constraint matching the ON CONFLICT specification'}

Caught at WARNING/ERROR level inside a broad `except`, so it was never surfaced. What it costs:
`PaperBroker` rehydrates its ledger from this table on start ("Restored 1 filled orders, 1
positions"), so a restart silently loses every paper order and position the broker thought it had.
The user sees their paper portfolio empty after a deploy, with nothing in the logs but a line that
reads like a routine warning.

## Why the index cannot simply be made non-partial

`NormalizedOrder.id` defaults to `""`, and both `_persist_order` and
`execution/manager._insert_order_atomic` strip falsy fields — so the payload usually carries no
`client_order_id` at all, and `orders` holds many rows with `client_order_id = ''`. A non-partial
unique index over `(user_id, client_order_id)` would reject the second such row. The primary key is
no escape either: `id` is absent from the payload for the same reason.

So the row is replaced explicitly — delete the previous row for `(user_id, client_order_id)`, then
insert. `core/telegram.py` already uses delete+insert for the same PostgREST limitation.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.models import Exchange, NormalizedOrder, OrderSide, OrderType, ProductType
from paper.paper_broker import PaperBroker


def _order(**over) -> NormalizedOrder:
    base = dict(
        user_id="u1",
        broker="paper",
        symbol="NSE:TCS-EQ",
        exchange=Exchange.NSE,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        product=ProductType.INTRADAY,
        quantity=4,
        price=0.0,
        is_paper=True,
        source="manual",
        client_order_id="c-abc123",
        validity="DAY",
    )
    base.update(over)
    return NormalizedOrder(**base)


class _Recorder:
    """Captures the chain the broker builds, so a test can assert on the *shape* of the call."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.table_name = ""

    def table(self, name):
        self.table_name = name
        return _Query(self)


class _Query:
    def __init__(self, rec: _Recorder) -> None:
        self.rec = rec

    def _chain(self, op: str, *args):
        self.rec.calls.append((self.rec.table_name, op, *args))
        return self

    def delete(self):
        return self._chain("delete")

    def insert(self, data):
        return self._chain("insert", data)

    def upsert(self, data, **kw):
        return self._chain("upsert", data, kw)

    def eq(self, col, val):
        return self._chain(f"eq:{col}", val)

    def execute(self):
        # Every recorded tuple keeps its op in slot 1, so tests can read `c[1]` unconditionally.
        self.rec.calls.append(("execute", "execute"))
        return MagicMock(data=[])


@pytest.fixture
def broker_with_recorder(monkeypatch):
    broker = PaperBroker.__new__(PaperBroker)  # no connect(), no broker session
    rec = _Recorder()
    supabase = MagicMock()
    supabase.table.side_effect = lambda name: rec.table(name)
    monkeypatch.setattr("paper.paper_broker.get_supabase", lambda: supabase)
    return broker, rec


# ── the write happens at all ───────────────────────────────────────────────────

def test_the_paper_order_row_is_written(broker_with_recorder):
    broker, rec = broker_with_recorder
    broker._persist_order(_order(), None)

    ops = [c[1] for c in rec.calls]
    assert "insert" in ops, f"nothing was inserted: {rec.calls}"
    assert "upsert" not in ops, f"the impossible partial-index upsert is back: {rec.calls}"


def test_the_insert_carries_the_order(broker_with_recorder):
    broker, rec = broker_with_recorder
    broker._persist_order(_order(), None)

    inserted = next(c[2] for c in rec.calls if c[1] == "insert")
    assert inserted["client_order_id"] == "c-abc123"
    assert inserted["symbol"] == "NSE:TCS-EQ"
    assert inserted["quantity"] == 4


def test_the_previous_row_is_deleted_first(broker_with_recorder):
    """Delete-then-insert is the substitute for the conflict target.

    Without the delete, every state change on a resting paper order would append a new row, and
    the ledger restore on restart would read them all as separate orders.
    """
    broker, rec = broker_with_recorder
    broker._persist_order(_order(), None)

    ops = [c[1] for c in rec.calls]
    assert ops.index("delete") < ops.index("insert"), f"delete must precede insert: {rec.calls}"


def test_the_delete_is_scoped_to_this_tenant_and_order(broker_with_recorder):
    broker, rec = broker_with_recorder
    broker._persist_order(_order(), None)

    # c[1:] drops the table-name slot so the call reads as (op, value).
    calls = [c[1:] for c in rec.calls]
    assert ("eq:user_id", "u1") in calls, f"delete not scoped by tenant: {rec.calls}"
    assert ("eq:client_order_id", "c-abc123") in calls, f"not scoped by order: {rec.calls}"


def test_it_writes_to_the_shared_orders_table(broker_with_recorder):
    """Same table `execution/manager._insert_order_atomic` uses — the two must stay one row."""
    broker, rec = broker_with_recorder
    broker._persist_order(_order(), None)

    assert {c[0] for c in rec.calls if c[0] not in ("execute",)} == {"orders"}


# ── nothing is silently dropped ────────────────────────────────────────────────

def test_a_persistence_failure_is_still_logged_as_an_error(monkeypatch, caplog):
    """A failure must remain loud. The bug was never the exception — it was that nobody read it.

    This asserts the log stays at ERROR so the line cannot quietly become a WARNING again and get
    lost among the routine noise.
    """
    import logging

    broker = PaperBroker.__new__(PaperBroker)
    supabase = MagicMock()
    supabase.table.side_effect = RuntimeError("boom")
    monkeypatch.setattr("paper.paper_broker.get_supabase", lambda: supabase)

    with caplog.at_level(logging.ERROR, logger="paper.paper_broker"):
        broker._persist_order(_order(), None)

    assert any(r.levelno == logging.ERROR for r in caplog.records), "failure was not logged at ERROR"


def test_an_order_without_a_client_order_id_is_still_written(monkeypatch):
    """No `client_order_id` means nothing to delete — but the insert must still happen.

    `NormalizedOrder.id` defaults to `""` and falsy fields are stripped, so plenty of real orders
    reach here without one. Skipping the delete is correct; skipping the insert would lose them.
    """
    rec = _Recorder()
    broker = PaperBroker.__new__(PaperBroker)
    supabase = MagicMock()
    supabase.table.side_effect = lambda name: rec.table(name)
    monkeypatch.setattr("paper.paper_broker.get_supabase", lambda: supabase)

    broker._persist_order(_order(client_order_id=""), None)

    ops = [c[1] for c in rec.calls]
    assert "insert" in ops, f"an order with no client_order_id was dropped: {rec.calls}"
    assert "eq:client_order_id" not in ops, f"deleted on an empty key: {rec.calls}"