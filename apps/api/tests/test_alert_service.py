from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from application.services.alert_service import AlertService


@pytest.fixture
def svc() -> AlertService:
    return AlertService()


@pytest.fixture
def mock_db() -> Generator[dict, None, None]:
    with (
        patch("application.services.alert_service.get_supabase") as mock_get,
        patch("application.services.alert_service.async_supabase") as mock_async,
        patch("application.services.alert_service.async_safe_execute") as mock_execute,
        patch("application.services.alert_service.async_safe_single") as mock_single,
        patch("application.services.alert_service.record_audit") as mock_audit,
    ):
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_get.return_value.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.order.return_value = mock_select
        mock_single.return_value = None
        mock_execute.return_value = None
        yield {
            "get_supabase": mock_get,
            "async_supabase": mock_async,
            "async_safe_execute": mock_execute,
            "async_safe_single": mock_single,
            "record_audit": mock_audit,
            "table": mock_table,
            "select": mock_select,
        }


def make_alert(overrides=None) -> dict:
    row = {
        "id": "alert-1", "user_id": "u1", "symbol": "RELIANCE",
        "condition": "above", "target_price": 2500.0, "is_active": True,
        "triggered_at": None, "note": "test alert", "created_at": "2025-01-01T00:00:00",
    }
    if overrides:
        row.update(overrides)
    return row


class TestListAlerts:
    @pytest.mark.asyncio
    async def test_returns_alerts(self, svc, mock_db) -> None:
        mock_db["async_safe_execute"].return_value = [make_alert()]

        result = await svc.list_alerts("u1")

        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["symbol"] == "RELIANCE"

    @pytest.mark.asyncio
    async def test_returns_empty_when_none(self, svc, mock_db) -> None:
        mock_db["async_safe_execute"].return_value = None

        result = await svc.list_alerts("u1")

        assert result == {"alerts": []}

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, svc, mock_db) -> None:
        mock_db["async_safe_execute"].return_value = []

        result = await svc.list_alerts("u1")

        assert result == {"alerts": []}


class TestCreateAlert:
    @pytest.mark.asyncio
    async def test_creates_and_returns_formatted(self, svc, mock_db) -> None:
        alert = make_alert()
        mock_db["async_supabase"].return_value.data = [alert]

        result = await svc.create_alert("u1", "RELIANCE", "above", 2500.0, "test alert")

        assert result["id"] == "alert-1"
        assert result["symbol"] == "RELIANCE"
        assert result["condition"] == "above"
        assert result["target_price"] == 2500.0
        assert result["is_active"] is True
        assert result["note"] == "test alert"
        mock_db["record_audit"].assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_bad_condition(self, svc, mock_db) -> None:
        with pytest.raises(HTTPException) as exc:
            await svc.create_alert("u1", "RELIANCE", "invalid", 2500.0, "")
        assert exc.value.status_code == 400
        assert "condition must be" in exc.value.detail


class TestDeleteAlert:
    @pytest.mark.asyncio
    async def test_deletes_existing(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {"id": "alert-1"}

        result = await svc.delete_alert("u1", "alert-1")

        assert result is None
        mock_db["async_supabase"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = None

        with pytest.raises(HTTPException) as exc:
            await svc.delete_alert("u1", "nonexistent")
        assert exc.value.status_code == 404
        assert "Alert not found" in exc.value.detail


class TestToggleAlert:
    @pytest.mark.asyncio
    async def test_toggles_active_to_false(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {"id": "alert-1", "is_active": True}

        result = await svc.toggle_alert("u1", "alert-1")

        assert result == {"is_active": False}

    @pytest.mark.asyncio
    async def test_toggles_inactive_to_true(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {"id": "alert-1", "is_active": False}

        result = await svc.toggle_alert("u1", "alert-1")

        assert result == {"is_active": True}

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = None

        with pytest.raises(HTTPException) as exc:
            await svc.toggle_alert("u1", "nonexistent")
        assert exc.value.status_code == 404
        assert "Alert not found" in exc.value.detail


class TestNotificationPrefs:
    @pytest.mark.asyncio
    async def test_returns_defaults_when_no_prefs(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = None

        result = await svc.get_notification_prefs("u1")

        assert result == {"channels": ["email"]}

    @pytest.mark.asyncio
    async def test_returns_existing_prefs(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {"id": "prefs-1", "channels": ["email", "sms"]}

        result = await svc.get_notification_prefs("u1")

        assert result == {"channels": ["email", "sms"]}

    @pytest.mark.asyncio
    async def test_updates_existing_prefs(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = {"id": "prefs-1", "channels": ["email"]}

        result = await svc.update_notification_prefs("u1", ["sms", "whatsapp"])

        assert result == {"channels": ["sms", "whatsapp"]}
        mock_db["async_supabase"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_inserts_new_prefs(self, svc, mock_db) -> None:
        mock_db["async_safe_single"].return_value = None

        result = await svc.update_notification_prefs("u1", ["email"])

        assert result == {"channels": ["email"]}
        mock_db["async_supabase"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_on_invalid_channel(self, svc, mock_db) -> None:
        with pytest.raises(HTTPException) as exc:
            await svc.update_notification_prefs("u1", ["email", "telegram"])
        assert exc.value.status_code == 400
        assert "Invalid channel" in exc.value.detail
