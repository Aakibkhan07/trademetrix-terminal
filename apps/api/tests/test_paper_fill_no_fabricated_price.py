"""A paper fill must be priced by a market, never invented.

## The bug

`_get_fill_price` had a branch that fabricated an **option premium** whenever nothing could price
the symbol. It picked an underlying from `market_cache`, and if even that was empty, fell back to a
**hardcoded** spot:

    spot = 81000.0 if "SENSEX" in sym else 24500.0

then priced the option off the distance from strike:

    dist = abs(strike - spot) / interval
    premium = max(12, 95 - dist * 14 - (10 if is_otm else 0))
    premium = round(max(8.0, premium + (hash(sym) % 7) - 3), 2)
    market_cache.put_quote(order.symbol, {"last_price": premium, "ltp": premium})

Three separate problems, in increasing order of severity:

1. The number was **made up**. A paper order "filled" at a price that never traded, which is the
   one thing a paper account exists to avoid being.
2. It was written into `market_cache` as though it were a quote, so every later reader of that
   symbol — including the quote endpoints — inherited the invented price.
3. `hash(sym) % 7` made it non-deterministic across processes, so the same option priced
   differently on two runs. Non-determinism in a price is not a rounding concern.

A non-option order with no quote ended at `order.price or 80.0 if is_opt else 0.0`, so options also
had a fabricated **floor** of 80.0 for any path that skipped the formula.

The branch also contradicted the contract two methods up in the same class, which returns
`PaperOrderStatus.PENDING` precisely when no quote resolves. A paper option order was therefore
filled where a cash order correctly stayed pending.

## Why "derive it from the underlying" was rejected

The formula could be fed a *real* cached underlying spot, which looks like a fix and is not one. A
distance-from-strike formula is not a quote; it is a second opinion about volatility, theta and
the volatility smile, computed without any of them. It would still be a number the market never
produced, and still would not match the broker when the two are compared. A paper fill is worth
the last traded price or nothing at all.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from core.models import (
    Exchange,
    InstrumentType,
    NormalizedOrder,
    OrderSide,
    OrderType,
    OptionType,
    ProductType,
)
from paper.fill_engine import FillEngine
from paper.models import PaperConfig

USER = "b3871483-62c4-4f10-9436-7f2b0634229a"


def _option(**over) -> NormalizedOrder:
    base = dict(
        user_id=USER,
        broker="paper",
        symbol="NSE:NIFTY25OCT24500CE",
        exchange=Exchange.NSE,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        product=ProductType.INTRADAY,
        quantity=1,
        price=0.0,
        instrument_type=InstrumentType.OPT,
        option_type=OptionType.CE,
        strike_price=24500.0,
        expiry_date="25OCT",
        is_paper=True,
    )
    base.update(over)
    return NormalizedOrder(**base)


def _engine() -> FillEngine:
    # `FillEngine` needs the paper config; defaults give INSTANT fills at no slippage, which is
    # what these tests want — a slippage would scale the price but not change whether it exists.
    return FillEngine(PaperConfig())


# ── no invented premium ────────────────────────────────────────────────────────

async def test_an_option_with_no_quote_does_not_get_an_invented_price():
    """The formula's own spot value must not come back out as a price.

    24500 was the hardcoded NIFTY spot and 81000 the hardcoded SENSEX one. A premium derived from
    either would be some other number, so the test asserts the strong property: nothing is
    returned at all when no market resolved.
    """
    with patch("paper.fill_engine.market_cache.get_quote", return_value=None):
        assert await await_price(_option()) == 0.0


async def test_an_option_does_not_fall_back_to_the_flat_80():
    """`order.price or 80.0` gave every unpriced option an 80-rupee floor.

    This is the case the formula's `try` swallowed: a non-zero-looking price on a symbol with no
    market.
    """
    with patch("paper.fill_engine.market_cache.get_quote", return_value=None):
        assert await await_price(_option(strike_price=60000.0, expiry_date="30DEC")) == 0.0


async def test_an_invented_price_is_never_cached_as_a_quote():
    """The cache poisoning is the part that outlives the order.

    `market_cache.put_quote` was called with the fabricated premium, so the invented number became
    the cached quote for that symbol. Any later reader inherited it. Nothing may be written here.
    """
    with patch("paper.fill_engine.market_cache.get_quote", return_value=None), patch(
        "paper.fill_engine.market_cache.put_quote"
    ) as put:
        await await_price(_option())
    put.assert_not_called()


async def test_a_deep_otm_option_gets_no_price_either():
    """The formula was most confident exactly where it was most wrong.

    Distance 360 strikes out produced a small fabricated premium that looked plausible. It is
    still fabricated, so it must be zero.
    """
    with patch("paper.fill_engine.market_cache.get_quote", return_value=None):
        assert await await_price(_option(strike_price=40000.0)) == 0.0


async def test_a_near_the_money_option_gets_no_price_either():
    with patch("paper.fill_engine.market_cache.get_quote", return_value=None):
        assert await await_price(_option(strike_price=24500.0)) == 0.0


# ── real prices are still honoured ──────────────────────────────────────────────

async def test_a_cached_quote_is_still_used():
    """Removing the fabrication must not remove the working path."""
    with patch(
        "paper.fill_engine.market_cache.get_quote",
        return_value={"last_price": 118.45, "ltp": 118.45},
    ):
        assert await await_price(_option()) == pytest.approx(118.45)


async def test_a_limit_price_is_still_used_when_nothing_is_cached():
    with patch("paper.fill_engine.market_cache.get_quote", return_value=None):
        assert await await_price(_option(order_type=OrderType.LIMIT, price=96.0)) == pytest.approx(96.0)


async def test_a_cash_order_with_no_quote_still_returns_zero():
    """Unchanged behaviour — the option branch was the outlier, not the rule."""
    cash = NormalizedOrder(
        user_id=USER, broker="paper", symbol="NSE:RELIANCE-EQ", exchange=Exchange.NSE,
        side=OrderSide.BUY, order_type=OrderType.MARKET, product=ProductType.INTRADAY,
        quantity=1, price=0.0, instrument_type=InstrumentType.EQ, is_paper=True,
    )
    with patch("paper.fill_engine.market_cache.get_quote", return_value=None):
        assert await await_price(cash) == 0.0


# ── the order outcome follows ──────────────────────────────────────────────────

async def test_an_unpriced_option_order_ends_pending_not_filled():
    """The user-visible consequence, which is what the whole thing is for.

    With no price the fill returns zero quantity, so `PaperBroker.place_order` takes the
    `filled_quantity <= 0` path and parks the order as PENDING — the same as a cash order with no
    market. Before, this order was reported FILLED at an invented premium.
    """
    with patch("paper.fill_engine.market_cache.get_quote", return_value=None):
        fill = await _engine().simulate_fill(_option(), USER)

    assert fill.filled_price == 0.0
    assert fill.filled_quantity == 0


async def await_price(order: NormalizedOrder) -> float:
    """Call the private method; the branch under test has no public entry point on its own."""
    return await _engine()._get_fill_price(order)