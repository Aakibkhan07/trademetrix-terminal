"""Regression tests: Beta Hardening Sprint — safe_query robustness.

Covers: async_safe_single returning None gracefully when the underlying
PostgREST call yields None, instead of a misleading warning traceback.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.safe_query import async_safe_single


@pytest.mark.asyncio
async def test_async_safe_single_returns_none_when_execute_returns_none():
    with patch("core.safe_query.async_supabase", AsyncMock(return_value=None)):
        assert await async_safe_single(MagicMock()) is None


@pytest.mark.asyncio
async def test_async_safe_single_returns_data():
    class FakeResult:
        data = [{"id": 1}]

    with patch("core.safe_query.async_supabase", AsyncMock(return_value=FakeResult())):
        assert await async_safe_single(MagicMock()) == [{"id": 1}]


@pytest.mark.asyncio
async def test_async_safe_single_returns_none_on_exception():
    with patch("core.safe_query.async_supabase", AsyncMock(side_effect=Exception("DB down"))):
        assert await async_safe_single(MagicMock()) is None