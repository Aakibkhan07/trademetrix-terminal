from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from application.services.analytics_service import AnalyticsService


@pytest.fixture
def svc() -> AnalyticsService:
    return AnalyticsService()


class TestTrackEvent:
    def test_tracks_event(self, svc) -> None:
        result = svc.track_event("page_view", {"page": "/home"}, session_id="s1", user_id="u1")
        assert result["ok"] is True
        assert result["event"] == "page_view"
        assert len(svc._events) == 1
        assert svc._events[0]["user_id"] == "u1"

    def test_tracks_event_with_defaults(self, svc) -> None:
        result = svc.track_event("click")
        assert result["ok"] is True
        assert svc._events[0]["properties"] == {}
        assert svc._events[0]["session_id"] == ""

    def test_raises_on_empty_event_name(self, svc) -> None:
        with pytest.raises(ValueError, match="event is required"):
            svc.track_event("")

    def test_groups_events_by_session(self, svc) -> None:
        svc.track_event("e1", session_id="s1")
        svc.track_event("e2", session_id="s1")
        assert len(svc._sessions["s1"]) == 2


class TestListEvents:
    def test_lists_all_events(self, svc) -> None:
        svc.track_event("a")
        svc.track_event("b")
        result = svc.list_events()
        assert result["total"] == 2

    def test_filters_by_event_name(self, svc) -> None:
        svc.track_event("click")
        svc.track_event("page_view")
        svc.track_event("click")
        result = svc.list_events(event_filter="click")
        assert result["total"] == 2
        assert all(e["event"] == "click" for e in result["events"])

    def test_respects_limit(self, svc) -> None:
        for i in range(10):
            svc.track_event(f"e{i}")
        result = svc.list_events(limit=3)
        assert len(result["events"]) == 3
        assert result["total"] == 10


@pytest.mark.asyncio
class TestGetAdminOverview:
    @patch("application.services.analytics_service.get_supabase")
    @patch("application.services.analytics_service.async_supabase")
    async def test_returns_overview_with_counts(self, mock_async, mock_get, svc) -> None:
        mock_table = MagicMock()
        mock_get.return_value.table.return_value = mock_table

        mock_query = MagicMock()
        mock_query.execute.side_effect = [
            MagicMock(data=[{"id": "u1", "created_at": "2025-01-01T00:00:00"}, {"id": "u2", "created_at": "2025-01-02T00:00:00"}]),
            MagicMock(data=[{"user_id": "u1"}]),
            MagicMock(data=[{"user_id": "u1", "is_paper": False}]),
            MagicMock(data=[{"user_id": "u1"}]),
            MagicMock(data=[{"user_id": "u1", "created_at": "2025-01-01T00:00:00"}]),
        ]
        mock_table.select.return_value = mock_query

        def side_effect(fn) -> Any:
            return fn()

        mock_async.side_effect = side_effect

        result = await svc.get_admin_overview()
        assert result["total_users"] == 2
        assert "dau" in result
        assert "wau" in result
        assert "mau" in result
        assert "funnel" in result
        assert "daily_active_users" in result
        assert "event_counts" in result

    @patch("application.services.analytics_service.get_supabase")
    @patch("application.services.analytics_service.async_supabase")
    async def test_handles_empty_data(self, mock_async, mock_get, svc) -> None:
        mock_table = MagicMock()
        mock_get.return_value.table.return_value = mock_table

        mock_query = MagicMock()
        mock_query.execute.side_effect = [
            MagicMock(data=[]),
            MagicMock(data=[]),
            MagicMock(data=[]),
            MagicMock(data=[]),
            MagicMock(data=[]),
        ]
        mock_table.select.return_value = mock_query

        def side_effect(fn) -> Any:
            return fn()

        mock_async.side_effect = side_effect

        result = await svc.get_admin_overview()
        assert result["total_users"] == 0
        assert result["dau"] == 0
        assert result["broker_users"] == 0
        assert result["traded_users"] == 0
        assert result["total_tracked_events"] == 0
        assert result["total_tracked_users"] == 0
