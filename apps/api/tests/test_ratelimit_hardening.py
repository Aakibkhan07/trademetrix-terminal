"""Regression tests: Beta Hardening Sprint — rate limiter budget.

Covers: the anonymous client-telemetry path (`/api/v1/analytics/track-batch`)
does not consume the shared per-IP budget, so a 5s analytics batch can never
starve functional endpoints.
"""
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.ratelimit import RateLimitMiddleware


def test_track_batch_is_budget_exempt():
    assert RateLimitMiddleware._is_budget_exempt("/api/v1/analytics/track-batch") is True
    assert RateLimitMiddleware._is_budget_exempt("/api/v1/analytics/track") is False
    assert RateLimitMiddleware._is_budget_exempt("/api/v1/engine/positions") is False


@pytest.mark.asyncio
async def test_track_batch_bypasses_shared_budget():
    mw = RateLimitMiddleware(MagicMock())
    req = types.SimpleNamespace(
        url=types.SimpleNamespace(path="/api/v1/analytics/track-batch"),
        client=types.SimpleNamespace(host="1.2.3.4"),
    )
    resp = types.SimpleNamespace(headers={})

    async def call_next(request):
        return resp

    with patch("core.ratelimit.cache.increment", new_callable=AsyncMock) as inc:
        out = await mw.dispatch(req, call_next)

    inc.assert_not_awaited()
    assert out is resp


@pytest.mark.asyncio
async def test_functional_path_still_consumes_budget():
    mw = RateLimitMiddleware(MagicMock(), requests_per_minute=120)
    req = types.SimpleNamespace(
        url=types.SimpleNamespace(path="/api/v1/engine/positions"),
        client=types.SimpleNamespace(host="1.2.3.4"),
    )
    resp = types.SimpleNamespace(headers={})

    async def call_next(request):
        return resp

    with patch("core.ratelimit.cache.increment", AsyncMock(return_value=1)) as inc:
        out = await mw.dispatch(req, call_next)

    inc.assert_awaited_once()
    assert out is resp