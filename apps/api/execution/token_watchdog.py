import asyncio
import logging
from datetime import UTC, datetime

from core.db import async_supabase, get_supabase
from core.notifications import send_telegram_alert

logger = logging.getLogger(__name__)

TOKEN_WATCHDOG_INTERVAL = 900
TOKEN_EXPIRY_WARN_MINUTES = 60


async def _check_all_tokens():
    supabase = get_supabase()
    try:
        result = await async_supabase(lambda: supabase.table("broker_credentials")
            .select("user_id, broker, token_expires_at, profiles!user_id(email, full_name)")
            .eq("is_active", True)
            .execute()
        )
        rows = result.data or []
    except Exception as e:
        logger.warning("Token watchdog query failed: %s", e)
        return

    now = datetime.now(UTC)
    for row in rows:
        expiry_str = row.get("token_expires_at")
        if not expiry_str:
            continue
        try:
            expiry = datetime.fromisoformat(str(expiry_str).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue

        remaining = (expiry - now).total_seconds()
        if remaining < 0:
            profile = row.get("profiles") or {}
            msg = (
                f"\U0001f534 <b>Token Expired</b>\n"
                f"User: {profile.get('full_name', row['user_id'])}\n"
                f"Broker: {row['broker'].upper()}\n"
                f"Action: Re-authenticate immediately"
            )
            await send_telegram_alert(msg)
            logger.warning("Token expired user=%s broker=%s", row["user_id"], row["broker"])
        elif remaining < TOKEN_EXPIRY_WARN_MINUTES * 60:
            profile = row.get("profiles") or {}
            msg = (
                f"\u26a0\ufe0f <b>Token Expiring Soon</b>\n"
                f"User: {profile.get('full_name', row['user_id'])}\n"
                f"Broker: {row['broker'].upper()}\n"
                f"Expires: {expiry.strftime('%Y-%m-%d %H:%M UTC')}\n"
                f"Action: Re-authenticate to avoid interruption"
            )
            await send_telegram_alert(msg)


async def token_watchdog_loop():
    await asyncio.sleep(60)
    while True:
        try:
            await _check_all_tokens()
        except Exception as e:
            logger.warning("Token watchdog error: %s", e)
        await asyncio.sleep(TOKEN_WATCHDOG_INTERVAL)