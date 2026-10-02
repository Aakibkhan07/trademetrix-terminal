"""A single fill must produce exactly one trade record.

## The bug

Every paper fill was recorded **twice** in `execution_engine.TradeLedger`:

    client=paper_1_179097  broker_oid=paper_1_179097  NSE:NIFTY50-INDEX  BUY 5 @22424.19
    client=e39181429f7dd6  broker_oid=paper_1_179097  NSE:NIFTY50-INDEX  BUY 5 @22424.19

One record came from the paper broker under its own order id, one from the execution manager under
the engine's `client_order_id`. Nothing reconciled them, so `GET /paper/trades` listed every trade
twice and every aggregate over the ledger — `turnover()`, `totals()` — double-counted the fill.

`broker_order_id` was the evidence all along: it is the one field both records agree on, and it is
what identifies the fill at the broker.

## Why the key includes quantity and price

A partially-filled order legitimately produces several fills against the **same** `broker_order_id`.
Deduplicating on the order id alone would discard those and lose filled quantity silently — a worse
failure than a duplicate, because it understates a position. A repeat of the *same* fill matches on
order id, quantity and price together, so partials survive and duplicates do not.

Records with no `broker_order_id` are always kept. There is nothing to compare them on, and dropping
unidentified rows would lose real trades.
"""
from __future__ import annotations

from execution_engine.trades import TradeLedger, TradeRecord


def _trade(**over) -> TradeRecord:
    base = dict(
        user_id="u1", broker="paper", symbol="NSE:NIFTY50-INDEX", side="BUY",
        quantity=5, price=22424.19, is_paper=True,
    )
    base.update(over)
    return TradeRecord(**base)


# ── the duplication ───────────────────────────────────────────────────────────

def test_the_same_fill_is_recorded_once():
    ledger = TradeLedger()
    first = _trade(client_order_id="paper_1_1", broker_order_id="paper_1_1", correlation_id="paper_1_1")
    # The execution manager sees the same fill and records it under its own client order id.
    second = _trade(client_order_id="e39181429f7dd6", broker_order_id="paper_1_1", correlation_id="e39181429f7dd6")

    ledger.add(first)
    ledger.add(second)

    rows = ledger.list("u1", broker="paper")
    assert len(rows) == 1, f"one fill was recorded {len(rows)} times"


def test_the_kept_record_is_the_first_one():
    """Refusing the duplicate must not reorder or replace what is already stored."""
    ledger = TradeLedger()
    original = _trade(client_order_id="paper_1_1", broker_order_id="paper_1_1")
    ledger.add(original)
    ledger.add(_trade(client_order_id="engine_id", broker_order_id="paper_1_1"))

    rows = ledger.list("u1", broker="paper")
    assert rows[0].client_order_id == "paper_1_1"


# ── what must NOT be deduplicated ─────────────────────────────────────────────

def test_partial_fills_against_one_order_are_all_kept():
    """The reason quantity is in the key.

    A broker order filled 5 then 3 more is two fills on one `broker_order_id`. Deduplicating on the
    order id alone would silently drop the second and understate the position.
    """
    ledger = TradeLedger()
    ledger.add(_trade(quantity=5, price=22424.19, broker_order_id="paper_1_1"))
    ledger.add(_trade(quantity=3, price=22480.0, broker_order_id="paper_1_1"))

    assert len(ledger.list("u1", broker="paper")) == 2


def test_same_quantity_at_a_different_price_is_a_separate_fill():
    ledger = TradeLedger()
    ledger.add(_trade(quantity=5, price=22424.19, broker_order_id="paper_1_1"))
    ledger.add(_trade(quantity=5, price=22499.0, broker_order_id="paper_1_1"))

    assert len(ledger.list("u1", broker="paper")) == 2


def test_distinct_orders_are_all_kept():
    ledger = TradeLedger()
    for i in range(4):
        ledger.add(_trade(broker_order_id=f"paper_{i}_1", client_order_id=f"paper_{i}_1"))

    assert len(ledger.list("u1", broker="paper")) == 4


def test_records_without_a_broker_order_id_are_never_dropped():
    """Nothing to compare against, so nothing may be discarded.

    Losing an unidentified real trade is worse than keeping a duplicate.
    """
    ledger = TradeLedger()
    for i in range(3):
        ledger.add(_trade(client_order_id=f"c{i}", broker_order_id=""))

    assert len(ledger.list("u1", broker="paper")) == 3


def test_dedupe_is_scoped_to_one_tenant_and_broker():
    """Two tenants trading the same symbol must not collide."""
    ledger = TradeLedger()
    ledger.add(_trade(user_id="u1", broker_order_id="paper_1_1"))
    ledger.add(_trade(user_id="u2", broker_order_id="paper_1_1"))

    assert len(ledger.list("u1", broker="paper")) == 1
    assert len(ledger.list("u2", broker="paper")) == 1


def test_totals_do_not_double_count():
    """The aggregate the duplication actually corrupted.

    `totals()` returns a dict keyed by `broker:symbol`, each holding quantity/turnover/charges and
    a trade count — so a duplicated fill showed up as `quantity: 10` and `trades: 2` for a single
    fill of 5.
    """
    import pytest

    ledger = TradeLedger()
    ledger.add(_trade(quantity=5, price=100.0, broker_order_id="paper_1_1"))
    # Both recorders share the broker order id — that is the whole basis for treating these as
    # one fill. The second record omits `broker_order_id` here, which the guard deliberately does
    # not collapse, so it has to carry it for this test to mean anything.
    ledger.add(
        _trade(quantity=5, price=100.0, broker_order_id="paper_1_1",
               client_order_id="engine", correlation_id="engine")
    )

    totals = ledger.totals("u1")
    assert len(totals) == 1, f"expected one bucket, got {list(totals)}"

    bucket = next(iter(totals.values()))
    assert bucket["quantity"] == 5, f"filled quantity doubled: {bucket}"
    assert bucket["trades"] == 1, f"trade count doubled: {bucket}"
    assert bucket["turnover"] == pytest.approx(500.0), f"turnover doubled: {bucket}"


def test_the_unfixed_behaviour_is_what_this_test_describes():
    """Locks the reproduction in place, so the fix cannot silently stop being necessary.

    Two records that differ only in `client_order_id` and `correlation_id` — exactly what the paper
    broker and the execution manager each produce for one fill — must collapse to one. If a future
    change gives both recorders the same `client_order_id` instead, this test stops reproducing the
    duplication and should be revisited rather than kept as-is.
    """
    ledger = TradeLedger()
    broker_side = _trade(client_order_id="paper_1_1", broker_order_id="paper_1_1", correlation_id="paper_1_1")
    engine_side = _trade(client_order_id="e39181429f", broker_order_id="paper_1_1", correlation_id="e39181429f")
    assert broker_side.client_order_id != engine_side.client_order_id
    assert broker_side.broker_order_id == engine_side.broker_order_id

    ledger.add(broker_side)
    ledger.add(engine_side)

    assert len(ledger.list("u1", broker="paper")) == 1


def test_partial_fills_still_sum_in_totals():
    """The guard must not cost quantity: 5 then 3 on one order is 8 filled."""
    ledger = TradeLedger()
    ledger.add(_trade(quantity=5, price=100.0, broker_order_id="paper_1_1"))
    ledger.add(_trade(quantity=3, price=100.0, broker_order_id="paper_1_1"))

    bucket = next(iter(ledger.totals("u1").values()))
    assert bucket["quantity"] == 8, f"a partial fill was dropped: {bucket}"
    assert bucket["trades"] == 2