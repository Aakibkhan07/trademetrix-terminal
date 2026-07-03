"""Tests for Production Sprint 3: sync DB elimination, token refresh, OMS memory cap."""

import os

os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SECRET_KEY", "test-secret-key:32-chars-for-testing!!")
os.environ["ENCRYPTION_KEY"] = "MWVizZu2ZaJoSu6BoPII1xFR-gpEmktStXfpzDLh7_I="

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.safe_query import async_safe_execute, async_safe_single, async_safe_insert, async_safe_update


# ── Blocker 1: Async-safe query wrappers ──────────────────────────────

class TestAsyncSafeQueryWrappers:
    @pytest.mark.asyncio
    async def test_async_safe_single_returns_data(self):
        mock_result = MagicMock()
        mock_result.data = {"id": "abc"}
        mock_query = MagicMock()
        mock_query.maybe_single.return_value.execute.return_value = mock_result

        with patch("core.safe_query.async_supabase", new=AsyncMock(return_value=mock_result)):
            result = await async_safe_single(mock_query)
            assert result == {"id": "abc"}

    @pytest.mark.asyncio
    async def test_async_safe_single_returns_none_on_exception(self):
        mock_query = MagicMock()
        mock_query.maybe_single.return_value.execute.side_effect = Exception("DB error")

        with patch("core.safe_query.async_supabase", new=AsyncMock(side_effect=Exception("DB error"))):
            result = await async_safe_single(mock_query)
            assert result is None

    @pytest.mark.asyncio
    async def test_async_safe_execute_returns_data(self):
        mock_result = MagicMock()
        mock_result.data = [{"id": "a"}, {"id": "b"}]
        mock_query = MagicMock()
        mock_query.execute.return_value = mock_result

        with patch("core.safe_query.async_supabase", new=AsyncMock(return_value=mock_result)):
            result = await async_safe_execute(mock_query)
            assert result == [{"id": "a"}, {"id": "b"}]

    @pytest.mark.asyncio
    async def test_async_safe_execute_returns_empty_on_exception(self):
        with patch("core.safe_query.async_supabase", new=AsyncMock(side_effect=Exception("DB error"))):
            result = await async_safe_execute(MagicMock())
            assert result == []

    @pytest.mark.asyncio
    async def test_async_safe_insert(self):
        mock_result = MagicMock()
        mock_result.data = [{"id": "new"}]
        with patch("core.safe_query.async_supabase", new=AsyncMock(return_value=mock_result)):
            result = await async_safe_insert("test_table", {"foo": "bar"})
            assert result == {"id": "new"}

    @pytest.mark.asyncio
    async def test_async_safe_update(self):
        mock_result = MagicMock()
        mock_result.data = [{"id": "updated"}]
        with patch("core.safe_query.async_supabase", new=AsyncMock(return_value=mock_result)):
            result = await async_safe_update("test_table", {"foo": "bar"}, "id", "123")
            assert result == {"id": "updated"}


# ── Blocker 2: Token refresh ─────────────────────────────────────────

class TestTokenManager:
    @pytest.mark.asyncio
    async def test_per_account_locking(self):
        from brokers.token_manager import TokenManager
        tm1 = TokenManager("user1", "zerodha")
        tm2 = TokenManager("user1", "zerodha")
        assert tm1._lock_key == tm2._lock_key
        lock1 = await tm1._get_lock()
        lock2 = await tm2._get_lock()
        assert lock1 is lock2

    @pytest.mark.asyncio
    async def test_token_refresh_retry_on_failure(self):
        mock_adapter_cls = MagicMock()
        mock_adapter = AsyncMock()
        mock_adapter.authenticate.side_effect = [
            Exception("Network error"),
            Exception("Network error"),
            MagicMock(access_token="new_token", expires_at=None),
        ]
        mock_adapter_cls.return_value = mock_adapter

        mock_cred_data = MagicMock()
        mock_cred_data.data = {
            "encrypted_api_key": "gAAAAAB...",
            "encrypted_secret_key": "gAAAAAB...",
            "encrypted_access_token": "gAAAAAB...",
        }

        from brokers.token_manager import TokenManager
        tm = TokenManager("user1", "test_broker")

        with (
            patch("brokers.token_manager.get_broker", return_value=mock_adapter_cls),
            patch.object(tm, "_load_credentials", AsyncMock(return_value={"client_id": "c", "secret_key": "s", "access_token": ""})),
            patch.object(tm, "save_access_token", AsyncMock()),
        ):
            session = await tm.get_session()
            assert session["access_token"] == "new_token"
            assert mock_adapter.authenticate.call_count == 3

    @pytest.mark.asyncio
    async def test_token_refresh_timeout_raises(self):
        mock_adapter_cls = MagicMock()
        mock_adapter = AsyncMock()
        mock_adapter.authenticate.side_effect = asyncio.TimeoutError("timeout")
        mock_adapter_cls.return_value = mock_adapter

        from brokers.token_manager import TokenManager, TOKEN_REFRESH_MAX_RETRIES
        tm = TokenManager("user1", "test_timeout")

        with (
            patch("brokers.token_manager.get_broker", return_value=mock_adapter_cls),
            patch.object(tm, "_load_credentials", AsyncMock(return_value={"client_id": "c", "secret_key": "s", "access_token": ""})),
            patch.object(tm, "save_access_token", AsyncMock()),
        ):
            with pytest.raises(RuntimeError, match="timed out"):
                await tm.get_session()
            assert mock_adapter.authenticate.call_count == TOKEN_REFRESH_MAX_RETRIES + 1

    @pytest.mark.asyncio
    async def test_token_persists_to_db(self):
        mock_adapter_cls = MagicMock()
        mock_adapter = AsyncMock()
        mock_adapter.authenticate.return_value = MagicMock(access_token="persisted_token", expires_at=None)
        mock_adapter_cls.return_value = mock_adapter

        from brokers.token_manager import TokenManager
        tm = TokenManager("user1", "test_persist")

        save_mock = AsyncMock()
        with (
            patch("brokers.token_manager.get_broker", return_value=mock_adapter_cls),
            patch.object(tm, "_load_credentials", AsyncMock(return_value={"client_id": "c", "secret_key": "s", "access_token": ""})),
            patch.object(tm, "save_access_token", save_mock),
        ):
            await tm.get_session()
            save_mock.assert_awaited_once_with("persisted_token", None)

    @pytest.mark.asyncio
    async def test_race_condition_prevented(self):
        from brokers.token_manager import TokenManager
        tm = TokenManager("user1", "test_race")

        call_count = 0

        async def slow_authenticate(creds):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)
            return MagicMock(access_token="token", expires_at=None)

        mock_adapter = AsyncMock()
        mock_adapter.authenticate = slow_authenticate
        mock_adapter_cls = MagicMock(return_value=mock_adapter)

        with (
            patch("brokers.token_manager.get_broker", return_value=mock_adapter_cls),
            patch.object(tm, "_load_credentials", AsyncMock(return_value={"client_id": "c", "secret_key": "s", "access_token": ""})),
            patch.object(tm, "save_access_token", AsyncMock()),
        ):
            results = await asyncio.gather(tm.get_session(), tm.get_session(), tm.get_session())
            assert call_count == 1
            for r in results:
                assert r["access_token"] == "token"


# ── Blocker 3: OMS memory growth ─────────────────────────────────────

class TestOMSMemoryCap:
    @pytest.fixture(autouse=True)
    def reset_oms_singleton(self):
        from oms.manager import OrderManager
        OrderManager._reset_instance()
        yield
        OrderManager._reset_instance()

    @pytest.mark.asyncio
    async def test_orders_dict_is_ordered_dict(self):
        from oms.manager import order_manager
        from collections import OrderedDict
        assert isinstance(order_manager._orders, OrderedDict)

    @pytest.mark.asyncio
    async def test_add_order_moves_to_end(self):
        from oms.manager import OrderManager
        from oms.models import OmniOrder, OMSOrderState

        mgr = OrderManager(max_orders=10)
        o1 = OmniOrder(oms_order_id="o1", user_id="u1", state=OMSOrderState.NEW)
        o2 = OmniOrder(oms_order_id="o2", user_id="u1", state=OMSOrderState.NEW)
        mgr._add_order(o1)
        mgr._add_order(o2)
        keys = list(mgr._orders.keys())
        assert keys[-1] == "o2"
        mgr._add_order(o1)
        keys = list(mgr._orders.keys())
        assert keys[-1] == "o1"

    @pytest.mark.asyncio
    async def test_evicts_terminal_order_when_at_capacity(self):
        from oms.manager import OrderManager
        from oms.models import OmniOrder, OMSOrderState

        mgr = OrderManager(max_orders=3)
        o1 = OmniOrder(oms_order_id="term", user_id="u1", state=OMSOrderState.FILLED)
        o2 = OmniOrder(oms_order_id="active", user_id="u1", state=OMSOrderState.NEW)
        mgr._add_order(o1)
        mgr._add_order(o2)
        o3 = OmniOrder(oms_order_id="o3", user_id="u1", state=OMSOrderState.NEW)
        mgr._add_order(o3)
        assert len(mgr._orders) == 3

        o4 = OmniOrder(oms_order_id="o4", user_id="u1", state=OMSOrderState.QUEUED)
        mgr._add_order(o4)
        assert "term" not in mgr._orders
        assert len(mgr._orders) == 3

    @pytest.mark.asyncio
    async def test_evicts_oldest_when_no_terminal_orders(self):
        from oms.manager import OrderManager
        from oms.models import OmniOrder, OMSOrderState

        mgr = OrderManager(max_orders=2)
        o1 = OmniOrder(oms_order_id="o1", user_id="u1", state=OMSOrderState.NEW)
        o2 = OmniOrder(oms_order_id="o2", user_id="u1", state=OMSOrderState.NEW)
        mgr._add_order(o1)
        mgr._add_order(o2)
        o3 = OmniOrder(oms_order_id="o3", user_id="u1", state=OMSOrderState.NEW)
        mgr._add_order(o3)
        assert "o1" not in mgr._orders
        assert len(mgr._orders) == 2

    @pytest.mark.asyncio
    async def test_eviction_logs_warning_for_active_eviction(self, caplog):
        import logging
        caplog.set_level(logging.WARNING)

        from oms.manager import OrderManager
        from oms.models import OmniOrder, OMSOrderState

        mgr = OrderManager(max_orders=1)
        o1 = OmniOrder(oms_order_id="o1", user_id="u1", state=OMSOrderState.SENT)
        o2 = OmniOrder(oms_order_id="o2", user_id="u1", state=OMSOrderState.SENT)
        mgr._add_order(o1)
        mgr._add_order(o2)
        assert any("evicting oldest active order" in msg for msg in caplog.messages)
