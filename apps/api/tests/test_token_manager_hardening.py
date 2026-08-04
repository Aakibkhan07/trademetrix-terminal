"""Regression tests: Beta Hardening Sprint — graceful broker-token-expired.

Covers: fast-fail when the stored token is already past expiry, translation
of the open circuit breaker into a structured BrokerTokenExpiredError, and
the happy path still refreshing a valid session.
"""
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokers.token_manager import TokenManager
from core.exceptions import BrokerTokenExpiredError
from core.resilience import CircuitBreakerError


@pytest.mark.asyncio
async def test_refresh_fast_fails_on_expired_stored_token():
    tm = TokenManager("u1", "fyers")
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    with (
        patch.object(tm, "_load_credentials", AsyncMock(return_value={
            "client_id": "c", "access_token": "t", "token_expires_at": past})),
        patch("brokers.token_manager.create_broker") as mock_create,
    ):
        with pytest.raises(BrokerTokenExpiredError):
            await tm._refresh()
        mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_ignores_future_token_expiry():
    tm = TokenManager("u1", "fyers")
    future = (datetime.now(UTC) + timedelta(days=20)).isoformat()
    session = MagicMock()
    session.access_token = "new-token"
    session.expires_at = None
    breaker = AsyncMock()
    breaker.authenticate.return_value = session
    with (
        patch.object(tm, "_load_credentials", AsyncMock(return_value={
            "client_id": "c", "access_token": "t", "token_expires_at": future})),
        patch("brokers.token_manager.create_broker", return_value=breaker),
        patch.object(tm, "save_access_token", AsyncMock()),
    ):
        await tm._refresh()
    assert tm._session["access_token"] == "new-token"


@pytest.mark.asyncio
async def test_refresh_translates_circuit_breaker_to_token_expired():
    tm = TokenManager("u1", "fyers")
    breaker = AsyncMock()
    breaker.authenticate.side_effect = CircuitBreakerError("CircuitBreaker[broker_fyers] is open")
    with (
        patch.object(tm, "_load_credentials", AsyncMock(return_value={
            "client_id": "c", "access_token": "t", "token_expires_at": ""})),
        patch("brokers.token_manager.create_broker", return_value=breaker),
    ):
        with pytest.raises(BrokerTokenExpiredError):
            await tm._refresh()


@pytest.mark.asyncio
async def test_refresh_still_succeeds_with_valid_session():
    tm = TokenManager("u1", "fyers")
    session = MagicMock()
    session.access_token = "new-token"
    session.expires_at = None
    breaker = AsyncMock()
    breaker.authenticate.return_value = session
    with (
        patch.object(tm, "_load_credentials", AsyncMock(return_value={
            "client_id": "c", "access_token": "t", "token_expires_at": ""})),
        patch("brokers.token_manager.create_broker", return_value=breaker),
        patch.object(tm, "save_access_token", AsyncMock()),
    ):
        await tm._refresh()
    assert tm._session["access_token"] == "new-token"
    assert tm._session["client_id"] == "c"