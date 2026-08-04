"""Regression tests: Beta Hardening Sprint — paper bracket quotes.

Covers: paper bracket SL/TARGET price discovery must prefer the
broker-agnostic Yahoo feed when the market cache is stale, so paper trading
keeps working when the live broker token is expired (previously the code
depended on a live Fyers REST refresh — 5542 failures/48h on prod).
"""
from unittest.mock import AsyncMock, patch

import pytest

from core.models import Exchange, Quote
from oms.manager import OrderManager, PAPER_BROKER
from oms.models import BracketOrder


class FakeMarketCache:
    """Dict-backed stand-in for the market_cache singleton."""

    def __init__(self):
        self._quotes: dict[str, dict] = {}

    def get_quote(self, symbol: str):
        return self._quotes.get(symbol)

    def put_quote(self, symbol: str, data: dict) -> None:
        self._quotes[symbol] = data


def _bracket(symbol="NSE:NIFTY26AUGFUT") -> BracketOrder:
    return BracketOrder(
        oms_order_id="b1",
        user_id="u1",
        symbol=symbol,
        side="BUY",
        broker=PAPER_BROKER,
        quantity=10,
        entry_price=100.0,
        stop_loss_price=90.0,
        target_price=110.0,
    )


def _quote(symbol: str) -> Quote:
    return Quote(symbol=symbol, exchange=Exchange.NSE, last_price=105.0)


def _manager():
    mgr = OrderManager.__new__(OrderManager)
    mgr._warn_since = {}
    return mgr


@pytest.mark.asyncio
async def test_paper_bracket_quote_prefers_market_cache():
    mgr = _manager()
    bracket = _bracket()
    mc = FakeMarketCache()
    mc.put_quote(bracket.symbol, {"last_price": 105.5})
    with (
        patch("market.cache.market_cache.get_quote", side_effect=mc.get_quote),
        patch("market.cache.market_cache.put_quote", side_effect=mc.put_quote),
        patch("providers.yahoo.fetch_quotes", AsyncMock()) as fq,
        patch("brokers.token_manager.TokenManager") as tm,
    ):
        price = await mgr._bracket_quote_fetch(bracket)
    assert price == 105.5
    fq.assert_not_awaited()
    tm.assert_not_called()


@pytest.mark.asyncio
async def test_paper_bracket_quote_uses_yahoo_when_cache_stale():
    mgr = _manager()
    bracket = _bracket()
    mc = FakeMarketCache()
    with (
        patch("market.cache.market_cache.get_quote", side_effect=mc.get_quote),
        patch("market.cache.market_cache.put_quote", side_effect=mc.put_quote),
        patch("providers.yahoo.fetch_quotes", AsyncMock(return_value=[_quote(bracket.symbol)])) as fq,
        patch("brokers.token_manager.TokenManager") as tm,
    ):
        price = await mgr._bracket_quote_fetch(bracket)
    assert price == 105.0
    fq.assert_awaited_once_with(["NSE:NIFTY26AUGFUT"])
    tm.assert_not_called()


@pytest.mark.asyncio
async def test_paper_bracket_quote_does_not_need_live_token():
    mgr = _manager()
    bracket = _bracket()
    mc = FakeMarketCache()
    with (
        patch("market.cache.market_cache.get_quote", side_effect=mc.get_quote),
        patch("market.cache.market_cache.put_quote", side_effect=mc.put_quote),
        patch("providers.yahoo.fetch_quotes", AsyncMock(return_value=[_quote(bracket.symbol)])),
        patch("brokers.token_manager.TokenManager", side_effect=RuntimeError("must not be used")),
    ):
        price = await mgr._bracket_quote_fetch(bracket)
    assert price == 105.0


@pytest.mark.asyncio
async def test_paper_bracket_quote_returns_zero_when_all_sources_dead():
    mgr = _manager()
    bracket = _bracket()
    mc = FakeMarketCache()
    with (
        patch("market.cache.market_cache.get_quote", side_effect=mc.get_quote),
        patch("market.cache.market_cache.put_quote", side_effect=mc.put_quote),
        patch("providers.yahoo.fetch_quotes", AsyncMock(side_effect=Exception("yahoo down"))),
        patch("brokers.token_manager.TokenManager", side_effect=RuntimeError("breaker open")),
    ):
        price = await mgr._bracket_quote_fetch(bracket)
    assert price == 0.0