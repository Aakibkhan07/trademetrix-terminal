"""The paper-bracket refresh must stop hammering a permanently broken credential.

Production incident: `_quote_price` falls back to a live Fyers REST call when the
Yahoo path yields nothing, on a 2s loop, for every open bracket. When the stored
Fyers credential could not be decrypted this raised on every pass -- measured 62
"Cannot decrypt broker credentials" errors in 5 minutes across 11 open brackets,
which kept `broker_fyers` circuit-broken for everyone.

A decrypt failure or a rejected token is per-user and permanent until they
re-authenticate, so the Fyers path is skipped for them after the first failure.
Transient failures must still retry: the token may be momentarily unavailable.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from oms.manager import OrderManager

PERMANENT = "ValueError: Cannot decrypt broker credentials — key rotation may be incomplete"


def _bracket(user_id: str = "u1", symbol: str = "NSE:NIFTY25OCT24000CE"):
    return SimpleNamespace(user_id=user_id, symbol=symbol, broker="paper", is_paper=True)


@pytest.fixture(autouse=True)
def _fresh_manager():
    """OrderManager is a singleton with an early-return __init__; reset the flag."""
    mgr = OrderManager()
    mgr._paper_fyers_unusable = {}
    yield mgr


class TestPermanentFailureIsRemembered:
    @pytest.mark.asyncio
    async def test_decrypt_failure_disables_fyers_for_that_user(self, _fresh_manager):
        mgr = _fresh_manager
        session = AsyncMock(return_value={"client_id": "X", "access_token": "T"})
        with (
            patch("brokers.token_manager.TokenManager") as tm,
            patch("brokers.fyers_adapter.FyersAdapter") as fa,
        ):
            tm.return_value.get_session = session
            fa.return_value.authenticate = AsyncMock(side_effect=ValueError(PERMANENT))
            fa.return_value.get_quotes = AsyncMock(return_value=[])
            await mgr._bracket_quote_fetch(_bracket())
        assert mgr._paper_fyers_unusable.get("u1") is True, (
            "a credential that cannot be decrypted must be marked, not retried forever"
        )

    @pytest.mark.asyncio
    async def test_fyers_is_not_called_again_after_permanent_failure(self, _fresh_manager):
        mgr = _fresh_manager
        mgr._paper_fyers_unusable["u1"] = True
        get_session = AsyncMock(return_value={"client_id": "X", "access_token": "T"})
        with (
            patch("brokers.token_manager.TokenManager") as tm,
            patch("brokers.fyers_adapter.FyersAdapter") as fa,
        ):
            tm.return_value.get_session = get_session
            await mgr._bracket_quote_fetch(_bracket())
        get_session.assert_not_called()
        fa.return_value.get_quotes.assert_not_called()

    @pytest.mark.asyncio
    async def test_one_users_broken_token_does_not_affect_another(self, _fresh_manager):
        """The failure is per-user; user B must still get its own attempt."""
        mgr = _fresh_manager
        mgr._paper_fyers_unusable["u1"] = True
        get_session = AsyncMock(return_value={"client_id": "X", "access_token": "T"})
        with (
            patch("brokers.token_manager.TokenManager") as tm,
            patch("brokers.fyers_adapter.FyersAdapter") as fa,
        ):
            tm.return_value.get_session = get_session
            fa.return_value.authenticate = AsyncMock(return_value=None)
            fa.return_value.get_quotes = AsyncMock(return_value=[])
            await mgr._bracket_quote_fetch(_bracket(user_id="u2"))
        get_session.assert_called_once()


class TestTransientFailureStillRetries:
    @pytest.mark.asyncio
    async def test_network_error_does_not_disable_the_path(self, _fresh_manager):
        mgr = _fresh_manager
        with (
            patch("brokers.token_manager.TokenManager") as tm,
            patch("brokers.fyers_adapter.FyersAdapter") as fa,
        ):
            tm.return_value.get_session = AsyncMock(
                return_value={"client_id": "X", "access_token": "T"})
            fa.return_value.authenticate = AsyncMock(
                side_effect=ConnectionError("upstream connect error"))
            await mgr._bracket_quote_fetch(_bracket())
        assert "u1" not in mgr._paper_fyers_unusable, (
            "a network blip recovers; disabling the path would strand a working user"
        )

    @pytest.mark.asyncio
    async def test_rejected_token_disables_the_path(self, _fresh_manager):
        """A broker saying 'invalid access_token' is as permanent as a decrypt failure."""
        mgr = _fresh_manager
        with (
            patch("brokers.token_manager.TokenManager") as tm,
            patch("brokers.fyers_adapter.FyersAdapter") as fa,
        ):
            tm.return_value.get_session = AsyncMock(
                return_value={"client_id": "X", "access_token": "T"})
            fa.return_value.authenticate = AsyncMock(
                side_effect=ValueError("Fyers authentication failed — invalid access_token"))
            await mgr._bracket_quote_fetch(_bracket())
        assert mgr._paper_fyers_unusable.get("u1") is True


class TestYahooFallbackStillApplies:
    @pytest.mark.asyncio
    async def test_quote_path_survives_when_fyers_is_skipped(self, _fresh_manager):
        """Skipping Fyers must not break price resolution via the Yahoo path."""
        mgr = _fresh_manager
        mgr._paper_fyers_unusable["u1"] = True
        quote = SimpleNamespace(last_price=1234.5, model_dump=lambda mode=None: {
            "last_price": 1234.5, "symbol": "NSE:NIFTY25OCT24000CE"})
        get_session = AsyncMock(return_value={"client_id": "X", "access_token": "T"})
        with (
            patch("providers.yahoo.fetch_quotes", AsyncMock(return_value=[quote])),
            patch("market.cache.market_cache") as cache,
            patch("brokers.token_manager.TokenManager") as tm,
            patch("brokers.fyers_adapter.FyersAdapter") as fa,
        ):
            cache.get_quote.return_value = {"last_price": 1234.5}
            tm.return_value.get_session = get_session
            price = await mgr._bracket_quote_fetch(_bracket())
        assert price == 1234.5, "Yahoo/cache path is primary and must still work"
        get_session.assert_not_called(), "Fyers must not be attempted when marked unusable"

    @pytest.mark.asyncio
    async def test_fyers_skipped_even_when_cache_is_cold(self, _fresh_manager):
        """With no cached price, the marked-unusable path must return 0 quietly.

        Before the fix this path raised on every 2s pass for every open bracket.
        """
        mgr = _fresh_manager
        mgr._paper_fyers_unusable["u1"] = True
        get_session = AsyncMock(return_value={"client_id": "X", "access_token": "T"})
        with (
            patch("providers.yahoo.fetch_quotes", AsyncMock(return_value=[])),
            patch("market.cache.market_cache") as cache,
            patch("brokers.token_manager.TokenManager") as tm,
            patch("brokers.fyers_adapter.FyersAdapter") as fa,
        ):
            cache.get_quote.return_value = None
            tm.return_value.get_session = get_session
            price = await mgr._bracket_quote_fetch(_bracket())
        assert price == 0.0
        get_session.assert_not_called()