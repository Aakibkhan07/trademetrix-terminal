"""Per-user Telegram alerts — real implementation (v1.8.1).

Architecture:
- ONE platform bot (settings.telegram_bot_token, created via BotFather).
- Each USER links their own chat: the app issues a short-lived code, the user
  opens https://t.me/<bot>?start=<code> and sends /start; a background
  getUpdates poller matches the code and persists telegram_links(user_id,
  chat_id).
- Order/risk/strategy events from execution_event_bus are formatted and sent
  to the linked user's chat. No message ever crosses users.

Everything degrades gracefully when TELEGRAM_BOT_TOKEN is unset: linking
returns 503-style "not configured" and no polling runs — but nothing crashes.
"""

import asyncio
import logging
import secrets
import time
from datetime import UTC, datetime

from core.cache import cache
from core.config import settings

logger = logging.getLogger(__name__)

_LINK_CODE_TTL = 600  # 10 minutes
_POLL_INTERVAL = 2.0
_SEND_TIMEOUT = 10

_link_codes: dict[str, dict] = {}  # code -> {user_id, expires_at} (fallback when Redis down)

# Events worth pushing to a trader's pocket (order lifecycle + strategy + risk)
NOTIFY_EVENT_TYPES = {
    "OrderCompleted": "✅",
    "OrderRejected": "❌",
    "OrderFailed": "❌",
    "OrderCancelled": "⚪",
    "PositionOpened": "📈",
    "PositionClosed": "📉",
    "StrategyStarted": "▶️",
    "StrategyStopped": "⏹️",
    "RuntimeError": "🚨",
}


def _now() -> float:
    return time.monotonic()


class TelegramGateway:
    def __init__(self):
        self._bot_username: str = ""
        self._poll_offset: int = 0
        self._running = False

    @property
    def configured(self) -> bool:
        return bool(settings.telegram_bot_token)

    def _api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"

    async def _call(self, method: str, payload: dict) -> dict | None:
        if not self.configured:
            return None
        try:
            import httpx

            async with httpx.AsyncClient(timeout=_SEND_TIMEOUT) as client:
                resp = await client.post(self._api_url(method), json=payload)
                data = resp.json()
                if not data.get("ok"):
                    # 400 "chat not found" → stale link; caller cleans up
                    logger.warning("Telegram %s failed: %s", method, str(data)[:200])
                    return data
                return data
        except Exception as e:
            logger.warning("Telegram %s error: %s", method, e)
            return None

    async def get_bot_username(self) -> str:
        if self._bot_username:
            return self._bot_username
        if settings.telegram_bot_username:
            self._bot_username = settings.telegram_bot_username.lstrip("@")
            return self._bot_username
        data = await self._call("getMe", {})
        if data and data.get("ok"):
            self._bot_username = data["result"]["username"]
        return self._bot_username

    # ── link codes ──────────────────────────────────────────────────

    async def create_link_code(self, user_id: str) -> str | None:
        code = secrets.token_urlsafe(12)
        record = {"user_id": user_id, "expires_at": _now() + _LINK_CODE_TTL}
        try:
            await cache.set(f"tg_link:{code}", record, ttl_seconds=_LINK_CODE_TTL)
        except Exception:
            pass  # Redis down → in-memory fallback below
        _link_codes[code] = record
        return code

    async def consume_link_code(self, code: str) -> str | None:
        record = None
        try:
            record = await cache.get(f"tg_link:{code}")
            if record:
                await cache.delete(f"tg_link:{code}")
        except Exception:
            pass
        if not record:
            record = _link_codes.pop(code, None)
        else:
            _link_codes.pop(code, None)
        if not record or isinstance(record, dict) is False:
            return None
        if record.get("expires_at", 0) < _now():
            return None
        return record["user_id"]

    # ── links store ─────────────────────────────────────────────────

    async def save_link(self, user_id: str, chat_id: str, username: str = "") -> None:
        supabase = None
        try:
            from core.db import get_supabase

            supabase = get_supabase()
            await supabase.table("telegram_links").upsert(
                {
                    "user_id": user_id,
                    "chat_id": str(chat_id),
                    "username": username or "",
                    "linked_at": datetime.now(UTC).isoformat(),
                },
                on_conflict="user_id,chat_id",
            ).execute()
        except Exception as e:
            logger.error("Failed to save telegram link for %s: %s", user_id, e)
            raise

    async def get_link(self, user_id: str) -> dict | None:
        try:
            from core.db import get_supabase

            resp = (
                get_supabase()
                .table("telegram_links")
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            rows = resp.data or []
            return rows[0] if rows else None
        except Exception as e:
            logger.warning("telegram link lookup failed for %s: %s", user_id, e)
            return None

    async def unlink(self, user_id: str) -> bool:
        try:
            from core.db import get_supabase

            get_supabase().table("telegram_links").delete().eq("user_id", user_id).execute()
            return True
        except Exception as e:
            logger.warning("telegram unlink failed for %s: %s", user_id, e)
            return False

    async def chat_exists(self, chat_id: str) -> bool:
        """Probe with a silent chat action; False means the chat is gone."""
        data = await self._call("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        if data is None:
            return True  # transport failure → don't destroy the link
        err = str((data or {}).get("description", ""))
        return "chat not found" not in err.lower()

    # ── sending ─────────────────────────────────────────────────────

    async def send_message(self, chat_id: str, text: str) -> bool:
        if len(text) > 3900:
            text = text[:3900] + "\n…"
        data = await self._call(
            "sendMessage",
            {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
        )
        if data is None:
            return False
        err = str(data.get("description", "")).lower()
        if "chat not found" in err or "blocked" in err:
            logger.info("Telegram chat %s gone/blocked — dropping link", chat_id)
            try:
                await self.unlink_by_chat(chat_id)
            except Exception as e:
                logger.warning("unlink after chat-not-found failed: %s", e)
            return False
        return bool(data.get("ok"))

    async def unlink_by_chat(self, chat_id: str) -> None:
        try:
            from core.db import get_supabase

            get_supabase().table("telegram_links").delete().eq("chat_id", str(chat_id)).execute()
        except Exception as e:
            logger.warning("unlink_by_chat failed for %s: %s", chat_id, e)

    async def notify_user(self, user_id: str, text: str) -> bool:
        link = await self.get_link(user_id)
        if not link:
            return False
        return await self.send_message(link["chat_id"], text)

    # ── /start poller ───────────────────────────────────────────────

    async def start_polling(self) -> None:
        if not self.configured:
            logger.info("Telegram not configured — link polling disabled")
            return
        if self._running:
            return
        self._running = True
        asyncio.ensure_future(self._poll_loop())

    def stop_polling(self) -> None:
        self._running = False

    async def _poll_loop(self) -> None:
        logger.info("Telegram link poller started")
        while self._running:
            try:
                payload = {"timeout": 25, "offset": self._poll_offset, "allowed_updates": ["message"]}
                data = await self._call("getUpdates", payload)
                if data and data.get("ok"):
                    for update in data.get("result", []):
                        self._poll_offset = max(self._poll_offset, update["update_id"] + 1)
                        await self._handle_update(update)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Telegram poll error: %s", e)
                await asyncio.sleep(_POLL_INTERVAL)
        logger.info("Telegram link poller stopped")

    async def _handle_update(self, update: dict) -> None:
        msg = update.get("message") or {}
        text = (msg.get("text") or "").strip()
        chat = msg.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        from_user = msg.get("from") or {}
        if not chat_id:
            return

        if text.startswith("/start"):
            code = text[len("/start"):].strip()
            user_id = await self.consume_link_code(code) if code else None
            if user_id:
                await self.save_link(user_id, chat_id, from_user.get("username", ""))
                await self.send_message(
                    chat_id,
                    "✅ <b>Trade Metrix connected!</b>\n\nYou'll receive order fills, "
                    "rejections, strategy events and risk alerts here.\nSend /stop_alerts to disconnect.",
                )
                logger.info("Telegram chat %s linked to user %s", chat_id, user_id)
            else:
                await self.send_message(
                    chat_id,
                    "🔗 <b>Trade Metrix Alerts</b>\n\nOpen the Trade Metrix dashboard → "
                    "Settings → Telegram Alerts and click <b>Connect</b> to get your personal link.",
                )
        elif text.startswith("/stop_alerts"):
            await self.unlink_by_chat(chat_id)
            await self.send_message(chat_id, "🔕 Alerts disconnected. Re-link anytime from Settings.")
        elif text == "/status":
            await self.send_message(chat_id, "🟢 Trade Metrix bot is running.")


telegram_gateway = TelegramGateway()


def format_execution_event(event) -> str | None:
    """ExecutionEvent → human Telegram message (None = not worth sending)."""
    emoji = NOTIFY_EVENT_TYPES.get(event.event_type)
    if not emoji:
        return None
    ts = event.timestamp.strftime("%d %b %H:%M:%S") if event.timestamp else ""
    lines = [f"{emoji} <b>{event.event_type}</b>"]
    detail = []
    if event.symbol:
        detail.append(f"Symbol: <code>{event.symbol}</code>")
    if event.side:
        detail.append(f"Side: {event.side.upper()}")
    p = event.payload or {}
    for key in ("quantity", "qty", "filled_quantity"):
        if p.get(key):
            detail.append(f"Qty: {p[key]}")
            break
    for key in ("average_price", "price", "limit_price"):
        if p.get(key):
            try:
                detail.append(f"Price: ₹{float(p[key]):,.2f}")
            except (TypeError, ValueError):
                pass
            break
    if event.broker:
        detail.append(f"Broker: {event.broker}")
    if event.message:
        detail.append(f"<i>{event.message[:160]}</i>")
    if detail:
        lines.append(" · ".join(detail))
    lines.append(f"<i>{ts}</i>")
    return "\n".join(lines)


async def on_execution_event(event) -> None:
    """execution_event_bus subscriber — fire-and-forget safe."""
    try:
        text = format_execution_event(event)
        if text and event.user_id:
            await telegram_gateway.notify_user(event.user_id, text)
    except Exception as e:
        logger.warning("telegram on_execution_event failed: %s", e)
