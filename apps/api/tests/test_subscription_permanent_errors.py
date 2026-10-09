"""Regression: a feed must STOP on a permanent credential error, not retry forever.

Production incident: an undecryptable Fyers credential made ``feed_runner`` retry
every backoff step indefinitely. Measured 27,029 errors in 24h, the broker circuit
breaker opening several times a second, and CPU burned on work that could never
succeed. The feed could only recover when the user re-authenticated.

These tests pin the distinction that matters:
  * PERMANENT (undecryptable credential, rejected/expired token) -> stop, once
  * TRANSIENT (network timeout, broker 5xx) -> keep retrying with backoff
"""

from __future__ import annotations

import asyncio

import pytest

from market.subscription_manager import (
    PERMANENT_ERROR_MARKERS,
    SubscriptionManager,
    is_permanent_feed_error,
)


class TestClassification:
    @pytest.mark.parametrize(
        "message",
        [
            "Failed to decrypt broker credentials with primary and all old keys",
            "ValueError: Cannot decrypt broker credentials — key rotation may be incomplete",
            "Dhan authentication failed — invalid access_token",
            "Upstox authentication failed — invalid access_token",
            "Fyers access token has expired — user must re-authenticate via OAuth",
            "invalid_authentication",
        ],
    )
    def test_permanent_errors_are_recognised(self, message: str) -> None:
        assert is_permanent_feed_error(Exception(message)) is True

    @pytest.mark.parametrize(
        "message",
        [
            "ConnectError: connection refused",
            "ReadTimeout: read timed out",
            "HTTPStatusError: 503 Service Unavailable",
            "HTTPStatusError: 502 Bad Gateway",
            "upstream connect error or disconnect/reset",
            "Rate limit exceeded, retry later",
        ],
    )
    def test_transient_errors_are_not_permanent(self, message: str) -> None:
        """A network blip DOES recover, so the reconnect loop must keep running."""
        assert is_permanent_feed_error(Exception(message)) is False

    @pytest.mark.parametrize("exc", [asyncio.CancelledError(), KeyboardInterrupt()])
    def test_control_flow_exceptions_are_never_permanent(self, exc) -> None:
        """Treating CancelledError as permanent would silently break shutdown."""
        assert is_permanent_feed_error(exc) is False

    def test_markers_are_lowercase(self) -> None:
        """Matching is done on a lowercased string; an uppercase marker would never hit."""
        assert all(m == m.lower() for m in PERMANENT_ERROR_MARKERS)

    def test_no_marker_matches_a_generic_timeout(self) -> None:
        """Guards against a marker so broad it catches transient failures."""
        for msg in ("timeout", "timed out", "connection reset", "temporarily unavailable"):
            assert is_permanent_feed_error(Exception(msg)) is False


class TestFeedRunnerStops:
    @pytest.mark.asyncio
    async def test_feed_runner_returns_on_permanent_error(self) -> None:
        """The reconnect loop must exit, not sleep-and-retry, on a rejected token."""
        mgr = SubscriptionManager()
        mgr._running = True
        attempts = {"n": 0}

        async def boom(user_id, broker_type, symbols):
            attempts["n"] += 1
            raise ValueError("Dhan authentication failed — invalid access_token")

        mgr._reconnect_backoff["dhan"] = 0
        original = _patch_start(mgr, boom)
        try:
            await mgr._run_feed_once("dhan", "u1", ["NIFTY"])
        finally:
            original()
        assert attempts["n"] == 1, "permanent error must not be retried even once"

    @pytest.mark.asyncio
    async def test_feed_runner_retries_transient_error(self) -> None:
        """A transient failure must still back off and retry, then succeed."""
        mgr = SubscriptionManager()
        mgr._running = True
        calls = {"n": 0}

        async def flaky(user_id, broker_type, symbols):
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("upstream connect error")
            mgr._running = False

        mgr._reconnect_backoff["zerodha"] = 0
        original = _patch_start(mgr, flaky)
        try:
            await mgr._run_feed_once("zerodha", "u1", ["NIFTY"])
        finally:
            original()
        assert calls["n"] == 3, "transient errors must be retried until they clear"


def _patch_start(mgr: SubscriptionManager, fn):
    """Patch the socket call feed_runner uses, without touching the real socket."""
    import market.subscription_manager as mod

    original = mod.shared_socket.start_broker_feed
    mod.shared_socket.start_broker_feed = fn
    mgr._max_backoff = 0.001  # keep the test fast; backoff logic is covered above

    def restore():
        mod.shared_socket.start_broker_feed = original

    return restore