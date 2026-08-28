"""
Platform notifier — implements the engine's Notifier port using the platform's
existing Resend email + Telegram push (core.notifications / core.telegram).

Best-effort: any failure is swallowed so a notification problem can never block
or break an execution batch.
"""

from __future__ import annotations

from functools import lru_cache

from supabase import create_client, Client

from ..config import get_settings
from core.notifications import send_email_resend
from core.telegram import TelegramGateway


@lru_cache(maxsize=1)
def _sb() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_key)


async def _email_for(user_id: str) -> str | None:
    try:
        res = (
            _sb()
            .table("profiles")
            .select("email")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0].get("email")
    except Exception:
        pass
    return None


class PlatformNotifier:
    async def notify(self, user_id: str, kind: str, message: str) -> None:
        try:
            email = await _email_for(user_id)
            if email:
                await send_email_resend(email, f"Trade Metrix — {kind}", message)
        except Exception:
            pass
        try:
            await TelegramGateway().notify_user(user_id, message)
        except Exception:
            pass
