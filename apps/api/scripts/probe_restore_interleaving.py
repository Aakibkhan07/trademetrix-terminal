"""What does the paper restore actually get wrong?

The first version of this file tested a claim taken from a docstring -- that two concurrent
`_restore_positions` calls double every holding. That claim is false, and measuring it is how
it was found: the restore has one `await` (the order query) and everything after it is
synchronous, so a restore that resumes runs to completion without yielding. Two restores
cannot interleave inside the loop, and the locked and unlocked paths are identical.

This version measures what is actually broken, all three demonstrably so:

  1. the restore was not idempotent for the account -- `used_margin` accumulated on every run
  2. a fill landing while a restore was rebuilding was discarded
  3. two audit rows for one fill replayed as two fills

Run from `apps/api`:

    .venv/bin/python scripts/probe_restore_interleaving.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import Exchange, NormalizedOrder, OrderSide, OrderType, ProductType  # noqa: E402
from paper.models import PaperFill  # noqa: E402
from paper.paper_broker import PAPER_BROKER, PaperBroker  # noqa: E402

SYMBOL = "NSE:NIFTY50-INDEX"
CAPITAL = 500_000.0
N_ORDERS = 4
PRICE = 23_000.0


def _row(i: int, client_order_id: str = "", qty: int = 1) -> dict:
    return {
        "symbol": SYMBOL, "exchange": "NSE", "side": "BUY", "order_type": "MARKET",
        "product": "INTRADAY", "quantity": qty, "price": PRICE, "broker": PAPER_BROKER,
        "broker_order_id": f"paper_{i}", "client_order_id": client_order_id,
        "filled_quantity": qty, "average_price": PRICE, "status": "FILLED",
    }


class _S:
    def table(self, _n): return self
    def select(self, *_a, **_k): return self
    def eq(self, *_a, **_k): return self
    def order(self, *_a, **_k): return self


def install(rows: list[dict], delay: float = 0.02):
    import core.db as db
    import core.safe_query as sq

    async def fake_execute(_q):
        await asyncio.sleep(delay)          # the only suspension in the restore
        return list(rows)

    sq.async_safe_execute = fake_execute
    db.get_supabase = lambda: _S()


def order_row(qty: int = 1) -> NormalizedOrder:
    return NormalizedOrder(
        symbol=SYMBOL, exchange=Exchange("NSE"), side=OrderSide("BUY"),
        order_type=OrderType("MARKET"), product=ProductType("INTRADAY"),
        quantity=qty, price=PRICE, broker=PAPER_BROKER, user_id="user-1",
    )


def qty(broker: PaperBroker) -> int:
    pos = broker._positions.get(SYMBOL)
    return int(pos.quantity) if pos else 0


async def live_fill(broker: PaperBroker, order_id: str = "live",
                    table: list[dict] | None = None) -> None:
    """What `place_order` does inside its critical section, lock included.

    `table` is the audit table the restore reads; appending to it is what `_persist_order`
    does, and is the whole reason that write is inside the lock.
    """
    fill = PaperFill(filled_quantity=1, filled_price=PRICE, order_id=order_id)
    async with broker._positions_lock:
        broker._update_position(order_row(), fill)
        broker._update_account(order_row(), fill)
        broker._orders[order_id] = {"order": order_row(), "fills": [fill]}
        if table is not None:
            table.append(_row(-1, client_order_id=order_id))


async def main() -> int:
    failures = 0

    # ── 1. is the restore idempotent? ────────────────────────────────────────────────
    rows = [_row(i) for i in range(N_ORDERS)]
    install(rows)
    broker = PaperBroker("user-1")
    gross = N_ORDERS * PRICE

    await broker.connect()
    first_used, first_avail = broker._account.used_margin, broker._account.available_margin
    for _ in range(4):
        await broker.connect()
    print(f"  one connect    : used={first_used:>10,.0f}  available={first_avail:>10,.0f}")
    print(f"  five connects  : used={broker._account.used_margin:>10,.0f}  "
          f"available={broker._account.available_margin:>10,.0f}")
    print(f"  positions      : {qty(broker)} units (audit says {N_ORDERS})")
    if broker._account.used_margin != first_used:
        print(f"  !! margin grew across reconnects: {first_used:,.0f} -> "
              f"{broker._account.used_margin:,.0f}")
        failures += 1
    if abs(broker._account.available_margin - (CAPITAL - gross)) > 1:
        print(f"  !! available margin is not capital minus the fill book")
        failures += 1
    if not await broker._check_margin(order_row()):
        print("  !! a fresh order is rejected for margin")
        failures += 1

    # ── 2. does a fill in flight during a restore survive it? ────────────────────────
    # Both orders of the two critical sections, because a fix that only handles one is a fix
    # for a race that a scheduler may never produce.
    for label, restore_first in (("restore acquires the lock first", True),
                                 ("the fill acquires the lock first", False)):
        table = [_row(i) for i in range(N_ORDERS)]
        install(table)
        broker2 = PaperBroker("user-1")

        async def scenario():
            if restore_first:
                restore = asyncio.create_task(broker2._restore_positions())
                await asyncio.sleep(0.01)        # the restore is now awaiting its query
                await live_fill(broker2, table=table)
                await restore
            else:
                await live_fill(broker2, table=table)
                await broker2._restore_positions()
            return qty(broker2)

        after = await scenario()
        print()
        print(f"  {label:36}-> position = {after} units "
              f"(audit says {N_ORDERS} + 1 live = {N_ORDERS + 1})")
        if after != N_ORDERS + 1:
            print(f"  !! the live fill was discarded or double counted")
            failures += 1

    # ── 3. do two audit rows for one fill replay as one fill? ─────────────────────────
    duplicated = [_row(0, client_order_id="a"), _row(0, client_order_id="b"),
                  *[_row(i) for i in range(1, N_ORDERS)]]
    install(duplicated)
    broker3 = PaperBroker("user-1")
    await broker3.connect()
    print()
    print(f"  {len(duplicated)} audit rows for {N_ORDERS} fills: position = {qty(broker3)} units")
    if qty(broker3) != N_ORDERS:
        print(f"  !! the restore replayed one fill twice")
        failures += 1

    print()
    if failures:
        print(f"  {failures} problem(s) still present")
        return 1
    print(f"  all three measured correct")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))