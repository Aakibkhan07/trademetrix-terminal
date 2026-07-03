"""Tests for OMS persistence layer — mocks supabase to verify save/load/remove."""

import os

os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SECRET_KEY", "test-secret-key:32-chars-for-testing!!")
os.environ["ENCRYPTION_KEY"] = "MWVizZu2ZaJoSu6BoPII1xFR-gpEmktStXfpzDLh7_I="

from unittest.mock import MagicMock, patch

import pytest

from oms.models import BracketOrder, OCOOrder, OmniOrder
from oms.persistence import (
    load_active_bracket_orders,
    load_active_oco_orders,
    load_active_orders,
    remove_order,
    save_bracket_order,
    save_oco_order,
    save_order,
)


def _sample_order(**kwargs) -> OmniOrder:
    overrides = {
        "oms_order_id": "test_001",
        "user_id": "user_1",
        "broker": "paper",
        "symbol": "RELIANCE",
        "side": "BUY",
        "quantity": 10,
        "price": 2500.0,
        "state": "NEW",
    }
    overrides.update(kwargs)
    return OmniOrder(**overrides)


def _sample_bracket() -> BracketOrder:
    return BracketOrder(
        oms_order_id="br_001",
        parent_order_id="test_001",
        user_id="user_1",
        symbol="RELIANCE",
        quantity=10,
        entry_price=2500.0,
        stop_loss_price=2400.0,
        target_price=2600.0,
        active=True,
    )


def _sample_oco() -> OCOOrder:
    return OCOOrder(
        oms_order_id="oco_001",
        user_id="user_1",
        symbol="RELIANCE",
        quantity=10,
        order_a_id="a_001",
        order_b_id="b_001",
        active=True,
    )


class TestSaveAndRemoveOrder:
    @pytest.mark.asyncio
    async def test_save_order_calls_upsert(self):
        mock_table = MagicMock()
        mock_supabase = MagicMock()
        mock_supabase.table.return_value = mock_table

        with patch("oms.persistence.get_supabase", return_value=mock_supabase):
            order = _sample_order()
            await save_order(order)

        mock_supabase.table.assert_called_once_with("oms_orders")
        mock_table.upsert.assert_called_once()
        args, _ = mock_table.upsert.call_args
        data = args[0]
        assert data["oms_order_id"] == "test_001"
        assert data["user_id"] == "user_1"
        assert data["state"] == "NEW"

    @pytest.mark.asyncio
    async def test_remove_order_calls_delete(self):
        mock_table = MagicMock()
        mock_supabase = MagicMock()
        mock_supabase.table.return_value = mock_table

        with patch("oms.persistence.get_supabase", return_value=mock_supabase):
            await remove_order("test_001")

        mock_supabase.table.assert_called_once_with("oms_orders")
        mock_table.delete.assert_called_once()
        mock_table.delete.return_value.eq.assert_called_once_with("oms_order_id", "test_001")

    @pytest.mark.asyncio
    async def test_save_bracket_order_calls_upsert(self):
        mock_table = MagicMock()
        mock_supabase = MagicMock()
        mock_supabase.table.return_value = mock_table

        with patch("oms.persistence.get_supabase", return_value=mock_supabase):
            bracket = _sample_bracket()
            await save_bracket_order(bracket)

        mock_supabase.table.assert_called_once_with("oms_bracket_orders")
        mock_table.upsert.assert_called_once()
        data = mock_table.upsert.call_args[0][0]
        assert data["oms_order_id"] == "br_001"
        assert data["parent_order_id"] == "test_001"
        assert data["active"] is True

    @pytest.mark.asyncio
    async def test_save_oco_order_calls_upsert(self):
        mock_table = MagicMock()
        mock_supabase = MagicMock()
        mock_supabase.table.return_value = mock_table

        with patch("oms.persistence.get_supabase", return_value=mock_supabase):
            oco = _sample_oco()
            await save_oco_order(oco)

        mock_supabase.table.assert_called_once_with("oms_oco_orders")
        mock_table.upsert.assert_called_once()
        data = mock_table.upsert.call_args[0][0]
        assert data["oms_order_id"] == "oco_001"
        assert data["active"] is True

    @pytest.mark.asyncio
    async def test_save_handles_db_error_gracefully(self):
        mock_table = MagicMock()
        mock_table.upsert.side_effect = Exception("table does not exist")
        mock_supabase = MagicMock()
        mock_supabase.table.return_value = mock_table

        with patch("oms.persistence.get_supabase", return_value=mock_supabase):
            await save_order(_sample_order())

    @pytest.mark.asyncio
    async def test_remove_handles_db_error_gracefully(self):
        mock_table = MagicMock()
        mock_table.delete.side_effect = Exception("table does not exist")
        mock_supabase = MagicMock()
        mock_supabase.table.return_value = mock_table

        with patch("oms.persistence.get_supabase", return_value=mock_supabase):
            await remove_order("test_001")


class TestLoadActiveOrders:
    @pytest.mark.asyncio
    async def test_load_active_orders_returns_parsed_rows(self, monkeypatch):
        fake_rows = [
            {"oms_order_id": "o1", "state": "QUEUED", "user_id": "u1", "broker": "paper", "symbol": "SBIN", "side": "BUY", "quantity": 5, "price": 800.0},
            {"oms_order_id": "o2", "state": "SENT", "user_id": "u1", "broker": "paper", "symbol": "TCS", "side": "SELL", "quantity": 3, "price": 3500.0},
        ]

        import oms.persistence as p

        async def fake_execute(q):
            return fake_rows

        monkeypatch.setattr(p, "async_safe_execute", fake_execute)

        mock_supabase = MagicMock()
        with patch("oms.persistence.get_supabase", return_value=mock_supabase):
            result = await load_active_orders()

        assert len(result) == 2
        assert result[0]["oms_order_id"] == "o1"
        assert result[1]["oms_order_id"] == "o2"

    @pytest.mark.asyncio
    async def test_load_active_orders_returns_empty_on_error(self, monkeypatch):
        import oms.persistence as p

        async def fake_execute(q):
            raise Exception("db error")

        monkeypatch.setattr(p, "async_safe_execute", fake_execute)

        mock_supabase = MagicMock()
        with patch("oms.persistence.get_supabase", return_value=mock_supabase):
            result = await load_active_orders()

        assert result == []

    @pytest.mark.asyncio
    async def test_load_active_bracket_orders(self, monkeypatch):
        fake_rows = [
            {"oms_order_id": "br_001", "parent_order_id": "p1", "active": True, "user_id": "u1", "symbol": "SBIN", "quantity": 5, "entry_price": 800.0, "stop_loss_price": 780.0, "target_price": 830.0},
        ]

        import oms.persistence as p

        async def fake_execute(q):
            return fake_rows

        monkeypatch.setattr(p, "async_safe_execute", fake_execute)

        mock_supabase = MagicMock()
        with patch("oms.persistence.get_supabase", return_value=mock_supabase):
            result = await load_active_bracket_orders()

        assert len(result) == 1
        assert result[0]["oms_order_id"] == "br_001"

    @pytest.mark.asyncio
    async def test_load_active_oco_orders(self, monkeypatch):
        fake_rows = [
            {"oms_order_id": "oco_001", "user_id": "u1", "active": True, "symbol": "SBIN", "quantity": 5, "order_a_id": "a1", "order_b_id": "b1"},
        ]

        import oms.persistence as p

        async def fake_execute(q):
            return fake_rows

        monkeypatch.setattr(p, "async_safe_execute", fake_execute)

        mock_supabase = MagicMock()
        with patch("oms.persistence.get_supabase", return_value=mock_supabase):
            result = await load_active_oco_orders()

        assert len(result) == 1
        assert result[0]["oms_order_id"] == "oco_001"


@pytest.mark.asyncio
async def test_recover_active_orders_round_trip(monkeypatch):
    from oms.manager import order_manager

    original_orders = order_manager._orders.copy()
    original_brackets = order_manager._bracket_orders.copy()
    original_ocos = order_manager._oco_orders.copy()

    try:
        order_manager._orders.clear()
        order_manager._bracket_orders.clear()
        order_manager._oco_orders.clear()

        saved_order = _sample_order(oms_order_id="roundtrip_1", state="QUEUED")

        import oms.manager as mgr

        async def fake_load_active():
            return [saved_order.model_dump(mode="json")]

        async def fake_load_brackets():
            return []

        async def fake_load_ocos():
            return []

        monkeypatch.setattr(mgr, "load_active_orders", fake_load_active)
        monkeypatch.setattr(mgr, "load_active_bracket_orders", fake_load_brackets)
        monkeypatch.setattr(mgr, "load_active_oco_orders", fake_load_ocos)

        enqueued_items = []

        async def fake_enqueue(item):
            enqueued_items.append(item)

        monkeypatch.setattr(mgr.order_queue, "enqueue", fake_enqueue)

        await order_manager._recover_active_orders()

        assert "roundtrip_1" in order_manager._orders
        recovered = order_manager._orders["roundtrip_1"]
        assert recovered.oms_order_id == "roundtrip_1"
        assert recovered.state == "QUEUED"
        assert recovered.user_id == "user_1"
        assert recovered.broker == "paper"
        assert recovered.symbol == "RELIANCE"
        assert recovered.side == "BUY"
        assert recovered.quantity == 10
        assert recovered.price == 2500.0

        assert len(enqueued_items) == 1
        assert enqueued_items[0].oms_order_id == "roundtrip_1"

    finally:
        order_manager._orders.clear()
        order_manager._orders.update(original_orders)
        order_manager._bracket_orders.clear()
        order_manager._bracket_orders.update(original_brackets)
        order_manager._oco_orders.clear()
        order_manager._oco_orders.update(original_ocos)


@pytest.mark.asyncio
async def test_recover_bracket_and_oco_orders(monkeypatch):
    from oms.manager import order_manager

    original_orders = order_manager._orders.copy()
    original_brackets = order_manager._bracket_orders.copy()
    original_ocos = order_manager._oco_orders.copy()

    try:
        order_manager._orders.clear()
        order_manager._bracket_orders.clear()
        order_manager._oco_orders.clear()

        import oms.manager as mgr

        async def fake_load_active():
            return [{"oms_order_id": "recovered_1", "state": "NEW", "user_id": "u1", "broker": "paper", "symbol": "SBIN", "side": "BUY", "quantity": 5, "price": 800.0}]

        async def fake_load_brackets():
            return [{"oms_order_id": "br_rec", "parent_order_id": "recovered_1", "active": True, "user_id": "u1", "symbol": "SBIN", "quantity": 5, "entry_price": 800.0, "stop_loss_price": 780.0, "target_price": 830.0, "entry_filled": False, "sl_order_id": "", "target_order_id": "", "trailing_sl_pct": 0.0}]

        async def fake_load_ocos():
            return [{"oms_order_id": "oco_rec", "user_id": "u1", "active": True, "symbol": "SBIN", "quantity": 5, "order_a_id": "a1", "order_b_id": "b1", "order_a_filled": False, "order_b_filled": False}]

        monkeypatch.setattr(mgr, "load_active_orders", fake_load_active)
        monkeypatch.setattr(mgr, "load_active_bracket_orders", fake_load_brackets)
        monkeypatch.setattr(mgr, "load_active_oco_orders", fake_load_ocos)
        monkeypatch.setattr(mgr.order_queue, "enqueue", lambda x: x)

        await order_manager._recover_active_orders()

        assert "recovered_1" in order_manager._orders
        assert "recovered_1" in order_manager._bracket_orders
        assert "oco_rec" in order_manager._oco_orders

        bracket = order_manager._bracket_orders["recovered_1"]
        assert bracket.oms_order_id == "br_rec"
        assert bracket.active is True

        oco = order_manager._oco_orders["oco_rec"]
        assert oco.active is True
        assert oco.order_a_id == "a1"

    finally:
        order_manager._orders.clear()
        order_manager._orders.update(original_orders)
        order_manager._bracket_orders.clear()
        order_manager._bracket_orders.update(original_brackets)
        order_manager._oco_orders.clear()
        order_manager._oco_orders.update(original_ocos)
