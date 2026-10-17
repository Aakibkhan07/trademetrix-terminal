"""Paper positions came back wrong after a reconnect. Three separate defects, one per test group.

The starting report was "paper positions are doubled". Doubling is the visible symptom; it is
not the cause, and chasing it directly is what the first version of this file did -- it asserted
that two concurrent restores double every holding, and passed while asserting nothing.

That claim is false and `scripts/probe_restore_interleaving.py` is where it was measured down.
The restore has exactly one suspension point, the order query, and everything after it --
`self._positions = {}`, the replay loop, the log -- is synchronous. A restore that resumes
therefore runs to completion without yielding, two restores cannot interleave inside the loop,
and the locked and unlocked paths produce identical positions. So:

  * a single restore was always correct, and two restores were always correct;
  * "two restores in the same second" in the startup log is `reconcile_pending_orders()`
    calling `connect()` once per pending order, not a race.

What was actually wrong, all three measured:

1. **The restore was not idempotent.** It replaced `_positions` and `_orders` but *added* to
   the account, and the field it added to -- `used_margin` -- was the one field `connect()`
   never reset. `used_margin` grew by the whole fill book on every reconnect while
   `total_margin` was reset to full capital, so `available_margin` walked to negative and then
   `_check_margin` rejected every paper order. Reconnects are routine: `reconcile_pending_orders()`
   calls `connect()` per pending order at startup, `reconciliation.py` per stored credential,
   and `_handle_token_expiry_and_retry` again mid-order.

2. **A fill landing during a restore was discarded.** The rebuild rebinds `self._positions`;
   a fill that wrote to the outgoing dict went with it. The user saw a position in their order
   history and not on the positions page. The write was also *outside* the restore's critical
   section, so even a fill that survived in memory was invisible to the rebuild that followed.

3. **Two audit rows for one fill would replay as two fills** (`_one_row_per_fill`). This one is
   a guard, not a measurement: driven end to end, three paper fills through the real
   `ExecutionManager.place_order` produce three rows, one per `broker_order_id`. It is kept
   because `orders` has two writers and partial unique indexes that cannot serve as an
   ON CONFLICT target, so a write outside the delete-then-insert sequence is a matter of when.

Groups 1 and 2 are the measured defects. Group 3 is a guard on a multi-writer table. Each
group below fails against the code as it was, and `scripts/mutation_restore_lock.py` re-breaks
all three to confirm it.
"""
import asyncio

import pytest

from core.models import Exchange, NormalizedOrder, OrderSide, OrderType, ProductType
from paper.models import PaperFill
from paper.paper_broker import PAPER_BROKER, PaperBroker

SYMBOL = "NSE:NIFTY50-INDEX"
PRICE = 23000.0
CAPITAL = 500_000.0


def _row(i: int, client_order_id: str = "", qty: int = 1) -> dict:
    return {
        "symbol": SYMBOL, "exchange": "NSE", "side": "BUY", "order_type": "MARKET",
        "product": "INTRADAY", "quantity": qty, "price": PRICE, "broker": PAPER_BROKER,
        "broker_order_id": f"paper_{i}" if i >= 0 else client_order_id,
        "client_order_id": client_order_id,
        "filled_quantity": qty, "average_price": PRICE, "status": "FILLED",
    }


class _Table:
    def table(self, _name): return self
    def select(self, *_a, **_k): return self
    def eq(self, *_a, **_k): return self
    def order(self, *_a, **_k): return self


@pytest.fixture
def audit(monkeypatch):
    """The `orders` table, shared by the restore's query and by `_persist_order`'s writes.

    Returns the live list so a test can append the row a fill would have written, which is
    what makes the restore-vs-fill ordering in group 2 a real test rather than a mock shape.
    """
    rows = [_row(i) for i in range(4)]

    async def fake_execute(_query):
        # Snapshot the rows BEFORE suspending, the way a database does: the row set is fixed
        # when the query is issued, not when the response arrives. This is what makes the
        # restore-vs-fill ordering testable -- a restore that reads before the fill's write
        # sees a stale book, which is exactly what happens in production.
        #
        # It must also actually suspend. Without a yield the "concurrent" restores run
        # straight through, never interleave, and every mutation of the lock in this file
        # passes. That is what the first version of this test did, and it reported the bug
        # as absent while production was losing positions.
        snapshot = list(rows)
        await asyncio.sleep(0.02)
        return snapshot

    import core.safe_query as sq
    monkeypatch.setattr(sq, "async_safe_execute", fake_execute)

    # The restore imports it inside the function, so patch the source module too.
    import core.db as db
    monkeypatch.setattr(db, "get_supabase", lambda: _Table())

    return rows


def _qty(broker: PaperBroker) -> int:
    pos = broker._positions.get(SYMBOL)  # noqa: SLF001
    return int(pos.quantity) if pos else 0


def _order(qty: int = 1) -> NormalizedOrder:
    return NormalizedOrder(
        symbol=SYMBOL, exchange=Exchange("NSE"), side=OrderSide("BUY"),
        order_type=OrderType("MARKET"), product=ProductType("INTRADAY"),
        quantity=qty, price=PRICE, broker=PAPER_BROKER, user_id="user-1",
    )


async def _fill(broker: PaperBroker, order_id: str, audit: list[dict], qty: int = 1) -> None:
    """`place_order`'s critical section: position, account, in-memory order, audit row."""
    fill = PaperFill(filled_quantity=qty, filled_price=PRICE, order_id=order_id)
    async with broker._positions_lock:  # noqa: SLF001
        broker._update_position(_order(qty), fill)  # noqa: SLF001
        broker._update_account(_order(qty), fill)  # noqa: SLF001
        broker._orders[order_id] = {"order": _order(qty), "fills": [fill]}  # noqa: SLF001
        audit.append(_row(-1, client_order_id=order_id, qty=qty))


# ── 1. the restore must be idempotent ────────────────────────────────────────────────

def test_a_restore_holds_exactly_the_audit_sum(audit):
    broker = PaperBroker("user-1")
    asyncio.run(broker._restore_positions())  # noqa: SLF001
    assert _qty(broker) == sum(int(r["filled_quantity"]) for r in audit)


def test_five_reconnects_do_not_multiply_the_used_margin(audit):
    """The measured failure: 4 rows of 23,000 restoring 9 times -> 828,000 used on 500,000."""
    broker = PaperBroker("user-1")

    async def reconnect_five_times():
        first = None
        for _ in range(5):
            await broker.connect()
            if first is None:
                first = broker._account.used_margin

    asyncio.run(reconnect_five_times())
    assert broker._account.used_margin == pytest.approx(4 * PRICE), (
        f"used_margin is {broker._account.used_margin:,.0f} after five reconnects -- the restore "
        "is adding the fill book to the account instead of rebuilding it"
    )
    assert broker._account.used_margin > 0, "the account was reset to zero, not rebuilt"


def test_available_margin_stays_capital_minus_the_fill_book(audit):
    broker = PaperBroker("user-1")
    asyncio.run(broker.connect())
    assert broker._account.available_margin == pytest.approx(CAPITAL - 4 * PRICE)


def test_a_reconnect_leaves_the_account_trading(audit):
    """`used_margin` past `total_margin` is what locks the user out of paper entirely."""
    broker = PaperBroker("user-1")

    async def nine_reconnects_then_an_order():
        for _ in range(9):
            await broker.connect()
        return await broker._check_margin(_order())  # noqa: SLF001

    assert asyncio.run(nine_reconnects_then_an_order()) is True, (
        "a fresh paper order was rejected for margin after nine reconnects"
    )


def test_the_restore_alone_rebuilds_the_account(audit):
    """`connect()` resets the account too, so this is belt-and-braces -- and it is the
    property that matters: the restore must not *add* to the account it finds. A caller that
    reaches the restore without a preceding connect would otherwise get a second fill book
    applied on top of the first."""
    broker = PaperBroker("user-1")
    broker._account.used_margin = 400_000.0  # noqa: SLF001

    async def twice():
        await broker._restore_positions()  # noqa: SLF001
        await broker._restore_positions()  # noqa: SLF001

    asyncio.run(twice())
    assert broker._account.used_margin == pytest.approx(4 * PRICE), (
        f"two restores left used_margin at {broker._account.used_margin:,.0f}"
    )


def test_connect_resets_used_margin_rather_than_only_the_price_fields(audit):
    """`_reset_account` exists because four of the five capital fields were reset in place."""
    broker = PaperBroker("user-1")
    broker._account.used_margin = 400_000.0  # noqa: SLF001
    broker._account.m2m_unrealised = 12_000.0  # noqa: SLF001
    asyncio.run(broker.connect())
    assert broker._account.used_margin == pytest.approx(4 * PRICE)
    assert broker._account.m2m_unrealised == pytest.approx(0.0)


# ── 2. a fill during a restore must survive it, in both orders ───────────────────────

@pytest.mark.parametrize("restore_first", [True, False], ids=["restore-first", "fill-first"])
def test_a_fill_racing_a_restore_is_neither_lost_nor_double_counted(audit, restore_first):
    """Both orders matter: a fix that only handles one is a fix for a race nobody may hit."""
    broker = PaperBroker("user-1")

    async def scenario():
        if restore_first:
            restore = asyncio.create_task(broker._restore_positions())  # noqa: SLF001
            await asyncio.sleep(0.01)          # the restore is now awaiting its query
            await _fill(broker, "live", audit)
            await restore
        else:
            await _fill(broker, "live", audit)
            await broker._restore_positions()  # noqa: SLF001
        return _qty(broker)

    assert asyncio.run(scenario()) == len(audit), (
        f"expected 4 restored + 1 live = 5 units, got {_qty(broker)}"
    )


def test_the_audit_write_is_inside_the_fill_critical_section():
    """Read from the source, because the order of two calls is not observable from outside.

    A restore rebuilds from the database, so a fill is only safe from a rebuild that has
    already written its row. If `_persist_order` moved back out of the lock this test is the
    only thing that would notice.

    Walked as an AST rather than searched as text: the comment above the lock names
    `_persist_order`, so `str.index` reports that mention and the guard would be reading its
    own explanation.
    """
    import ast
    import inspect
    import textwrap

    from paper.paper_broker import PaperBroker as B

    tree = ast.parse(textwrap.dedent(inspect.getsource(B.place_order)))

    critical: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncWith):
            continue
        held = node.items[0].context_expr
        if (isinstance(held, ast.Attribute) and getattr(held.value, "id", "") == "self"
                and held.attr == "_positions_lock"):
            critical = [ast.unparse(stmt) for stmt in node.body]

    joined = "\n".join(critical)
    assert "_update_position" in joined and "_persist_order" in joined, (
        "the critical section must hold the position update AND the audit write; a rebuild "
        "that starts after the fill cannot see a row the fill has not written yet. "
        f"Critical section holds: {critical}"
    )


def test_a_live_fill_after_restore_adds_exactly_once(audit):
    broker = PaperBroker("user-1")

    async def flow():
        await broker._restore_positions()  # noqa: SLF001
        await _fill(broker, "live", audit)

    asyncio.run(flow())
    assert _qty(broker) == len(audit)


# ── 3. one fill is one row, however many writers the audit has ───────────────────────
#
# A guard on a multi-writer table, NOT a fix for a measurement. The first version of this file
# called this "the actual doubling". Driving three paper fills through the real
# `ExecutionManager.place_order` produces three rows, one per `broker_order_id`: `place_order`
# sets `req.execution_request_id` before building the order, so both writers share a
# `client_order_id` and `_persist_order`'s delete collapses them. That claim came from a probe
# that built `NormalizedOrder` by hand with `client_order_id=""`, a state the real path never
# reaches. These two tests pin the property so the guard stays honest about what it is for.

def test_two_audit_rows_for_one_fill_replay_as_one_fill(monkeypatch):
    """Same broker order id, quantity and price, two rows."""
    rows = [_row(0, client_order_id="a"), _row(0, client_order_id="b"),
            *[_row(i) for i in range(1, 4)]]

    async def fake_execute(_q):
        await asyncio.sleep(0)
        return list(rows)

    import core.db as db
    import core.safe_query as sq
    monkeypatch.setattr(sq, "async_safe_execute", fake_execute)
    monkeypatch.setattr(db, "get_supabase", lambda: _Table())

    broker = PaperBroker("user-1")
    asyncio.run(broker.connect())
    assert _qty(broker) == 4, (
        f"5 audit rows describing 4 fills restored as {_qty(broker)} units"
    )


def test_two_genuine_partial_fills_of_one_order_are_both_kept(monkeypatch):
    """The dedupe key is (broker_order_id, quantity, price) precisely so this survives.

    A broker filling the same order twice in two lots is two fills. Deduplicating on the
    broker order id alone would erase the second one -- the fix that introduced the bug.
    """
    rows = [_row(0, qty=1), _row(0, qty=2), _row(1, qty=1)]

    async def fake_execute(_q):
        await asyncio.sleep(0)
        return list(rows)

    import core.db as db
    import core.safe_query as sq
    monkeypatch.setattr(sq, "async_safe_execute", fake_execute)
    monkeypatch.setattr(db, "get_supabase", lambda: _Table())

    broker = PaperBroker("user-1")
    asyncio.run(broker.connect())
    assert _qty(broker) == 4, "two partial fills of one order counted as one"


def test_the_dedupe_key_is_not_the_broker_order_id_alone():
    """A guard that the wrong key would satisfy."""
    rows = [_row(0), _row(0, qty=3)]
    assert len(PaperBroker._one_row_per_fill(rows)) == 2


# ── the claims that were wrong, pinned so they cannot come back ───────────────────────

def test_two_concurrent_restores_do_not_double_the_position(audit):
    """Kept, but now for the right reason: this asserts two restores are safe, NOT that
    removing the serialisation doubles. `scripts/probe_restore_interleaving.py` measures
    locked and unlocked as identical, because the replay loop has no suspension point."""
    broker = PaperBroker("user-1")

    async def both():
        await asyncio.gather(
            broker._restore_positions(),  # noqa: SLF001
            broker._restore_positions(),  # noqa: SLF001
        )

    asyncio.run(both())
    assert _qty(broker) == 4


def test_the_rebuild_and_the_fill_share_one_lock():
    broker = PaperBroker("user-1")
    assert isinstance(broker._positions_lock, asyncio.Lock)  # noqa: SLF001