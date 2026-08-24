"""Telegram per-user alerts — gateway, formatter, routes (v1.8.1)."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.telegram import (
    TelegramGateway,
    format_execution_event,
    telegram_gateway,
)
from execution.models import ExecutionEvent


@pytest.fixture(autouse=True)
def _reset_codes():
    import core.telegram as tg

    tg._link_codes.clear()
    yield
    tg._link_codes.clear()


@pytest.fixture
def gw_unconfigured():
    from core.config import settings

    original = settings.telegram_bot_token
    settings.telegram_bot_token = ""
    yield TelegramGateway()
    settings.telegram_bot_token = original


@pytest.fixture
def gw_configured():
    from core.config import settings

    original = settings.telegram_bot_token
    settings.telegram_bot_token = "12345:TESTTOKEN"
    yield TelegramGateway()
    settings.telegram_bot_token = original


class TestConfiguration:
    @pytest.mark.asyncio
    async def test_unconfigured_gateway_never_sends(self, gw_unconfigured):
        assert gw_unconfigured.configured is False
        assert await gw_unconfigured.send_message("123", "hi") is False
        assert await gw_unconfigured.get_bot_username() == ""

    @pytest.mark.asyncio
    async def test_polling_disabled_when_unconfigured(self, gw_unconfigured):
        await gw_unconfigured.start_polling()
        assert gw_unconfigured._running is False


class TestLinkCodes:
    @pytest.mark.asyncio
    async def test_create_and_consume_roundtrip(self, gw_configured):
        code = await gw_configured.create_link_code("user-1")
        assert code
        assert await gw_configured.consume_link_code(code) == "user-1"
        # single-use
        assert await gw_configured.consume_link_code(code) is None

    @pytest.mark.asyncio
    async def test_expired_code_rejected(self, gw_configured):
        code = await gw_configured.create_link_code("user-1")
        import core.telegram as tg

        tg._link_codes[code]["expires_at"] = 0.0
        assert await gw_configured.consume_link_code(code) is None

    @pytest.mark.asyncio
    async def test_unknown_code_returns_none(self, gw_configured):
        assert await gw_configured.consume_link_code("nope") is None


class TestEventFormatter:
    def _event(self, event_type="OrderCompleted", **kw):
        defaults = dict(
            event_type=event_type,
            user_id="u1",
            symbol="NSE:NIFTY50-INDEX",
            side="buy",
            message="",
            payload={"quantity": 75, "average_price": 24582.3},
            timestamp=datetime(2026, 8, 24, 9, 15, 0, tzinfo=timezone.utc),
        )
        defaults.update(kw)
        return ExecutionEvent(**defaults)

    def test_filled_event_formats(self):
        text = format_execution_event(self._event())
        assert "✅" in text and "OrderCompleted" in text
        assert "NIFTY50-INDEX" in text and "BUY" in text
        assert "₹24,582.30" in text and "Qty: 75" in text

    def test_ignored_event_types_return_none(self):
        assert format_execution_event(self._event(event_type="PnLUpdated")) is None

    def test_all_notifiable_types_format(self):
        from core.telegram import NOTIFY_EVENT_TYPES

        for et in NOTIFY_EVENT_TYPES:
            assert format_execution_event(self._event(event_type=et)) is not None

    def test_message_included_truncated(self):
        text = format_execution_event(self._event(message="x" * 500))
        assert len(text) < 600


class TestNotifyUser:
    @pytest.mark.asyncio
    async def test_notify_skips_unlinked_user(self, gw_configured):
        with patch.object(gw_configured, "get_link", new=AsyncMock(return_value=None)), \
             patch.object(gw_configured, "send_message", new=AsyncMock()) as sm:
            ok = await gw_configured.notify_user("u1", "hello")
        assert ok is False and sm.await_count == 0

    @pytest.mark.asyncio
    async def test_notify_sends_to_linked_chat(self, gw_configured):
        with patch.object(gw_configured, "get_link", new=AsyncMock(return_value={"chat_id": "4242"})), \
             patch.object(gw_configured, "send_message", new=AsyncMock(return_value=True)) as sm:
            ok = await gw_configured.notify_user("u1", "hello")
        assert ok is True
        sm.assert_awaited_once_with("4242", "hello")

    @pytest.mark.asyncio
    async def test_send_message_handles_http_failure(self, gw_configured):
        with patch("httpx.AsyncClient") as client_cls:
            client_cls.return_value.__aenter__ = AsyncMock(
                side_effect=lambda: (_ for _ in ()).throw(RuntimeError("network down"))
            )
            # __aenter__ side_effect with lambda won't work for async ctx; use simple failure path instead
        # simpler: patch _call to return None (transport failure)
        with patch.object(gw_configured, "_call", new=AsyncMock(return_value=None)):
            assert await gw_configured.send_message("1", "x") is False

    @pytest.mark.asyncio
    async def test_chat_not_found_drops_link(self, gw_configured):
        with patch.object(gw_configured, "_call", new=AsyncMock(return_value={"ok": False, "description": "Bad Request: chat not found"})), \
             patch.object(gw_configured, "unlink_by_chat", new=AsyncMock()) as unlink:
            ok = await gw_configured.send_message("4242", "x")
        assert ok is False
        unlink.assert_awaited_once_with("4242")


class TestRoutes:
    async def _client(self, auth_headers):
        from tests.conftest import _TEST_CSRF_TOKEN

        return {**auth_headers, "x-csrf-token": _TEST_CSRF_TOKEN}

    @pytest.mark.asyncio
    async def test_status_unlinked_and_unconfigured(self, client, auth_headers, monkeypatch):
        headers = await self._client(auth_headers)
        monkeypatch.setattr("core.config.settings.telegram_bot_token", "")
        with patch("core.telegram.TelegramGateway.get_link", new=AsyncMock(return_value=None)):
            r = await client.get("/api/v1/notifications/telegram/status", headers=headers)
        body = r.json()
        assert r.status_code == 200
        assert body["configured"] is False and body["linked"] is False

    @pytest.mark.asyncio
    async def test_link_returns_deep_link_when_configured(self, client, auth_headers, monkeypatch):
        headers = await self._client(auth_headers)
        monkeypatch.setattr("core.config.settings.telegram_bot_token", "12345:TOK")
        monkeypatch.setattr("core.config.settings.telegram_bot_username", "TradeMetrixAlertsBot")
        r = await client.post("/api/v1/notifications/telegram/link", headers=headers)
        body = r.json()
        assert r.status_code == 200
        assert body["url"].startswith("https://t.me/TradeMetrixAlertsBot?start=")

    @pytest.mark.asyncio
    async def test_link_returns_503_when_unconfigured(self, client, auth_headers, monkeypatch):
        headers = await self._client(auth_headers)
        monkeypatch.setattr("core.config.settings.telegram_bot_token", "")
        r = await client.post("/api/v1/notifications/telegram/link", headers=headers)
        assert r.status_code == 503

    @pytest.mark.asyncio
    async def test_unlink(self, client, auth_headers, monkeypatch):
        headers = await self._client(auth_headers)
        with patch("core.telegram.TelegramGateway.unlink", new=AsyncMock(return_value=True)) as un:
            r = await client.delete("/api/v1/notifications/telegram/link", headers=headers)
        assert r.status_code == 200 and r.json()["unlinked"] is True
        un.assert_awaited_once()


class TestStartHandler:
    @pytest.mark.asyncio
    async def test_handle_start_links_chat_and_confirms(self, gw_configured):
        update = {
            "update_id": 1,
            "message": {
                "text": "/start LINKCODE",
                "chat": {"id": 999},
                "from": {"username": "traderboy"},
            },
        }
        with patch.object(gw_configured, "consume_link_code", new=AsyncMock(return_value="user-9")), \
             patch.object(gw_configured, "save_link", new=AsyncMock()) as save, \
             patch.object(gw_configured, "send_message", new=AsyncMock(return_value=True)) as send:
            await gw_configured._handle_update(update)
        save.assert_awaited_once_with("user-9", "999", "traderboy")
        assert send.await_count == 1 and "connected" in send.await_args.args[1]
