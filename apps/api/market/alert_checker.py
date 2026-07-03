import logging
from datetime import UTC, datetime

from core.db import async_supabase, get_supabase
from core.models import Tick
from core.safe_query import safe_execute
from market.data_socket import shared_socket

logger = logging.getLogger(__name__)

_alert_task = None


async def _check_alerts(tick: Tick) -> None:
    supabase = get_supabase()
    symbol = tick.symbol.split(":")[0] if ":" in tick.symbol else tick.symbol
    alerts = safe_execute(
        supabase.table("user_alerts")
        .select("id, user_id, symbol, condition, target_price, is_active")
        .eq("symbol", symbol)
        .eq("is_active", True)
        .is_("triggered_at", "null")
    ) or []

    for alert in alerts:
        price = tick.last_price or 0
        condition = alert.get("condition")
        target = alert.get("target_price", 0)
        triggered = (condition == "above" and price >= target) or (condition == "below" and price <= target)
        if not triggered:
            continue

        await async_supabase(lambda: supabase.table("user_alerts").update({
            "triggered_at": datetime.now(UTC).isoformat(),
            "is_active": False,
        }).eq("id", alert["id"]).execute())

        try:
            await _send_alert_notification(alert["user_id"], alert["id"], symbol, condition, target, price)
        except Exception as e:
            logger.error("Alert notification failed user=%s alert=%s: %s", alert["user_id"], alert["id"], e)


async def _send_alert_notification(user_id: str, alert_id: str, symbol: str, condition: str, target: float, current: float) -> None:
    supabase = get_supabase()
    profile = await async_supabase(lambda: supabase.table("profiles").select("email, full_name, phone").eq("id", user_id).single().execute())
    if not profile.data:
        return
    p = profile.data
    email = p.get("email", "")
    phone = p.get("phone", "")
    name = p.get("full_name", "") or email

    direction = "above" if condition == "above" else "below"
    subject = f"Alert: {symbol} crossed {direction} ₹{target}"
    body = (
        f"Hi {name},\n\n"
        f"Your alert for {symbol} has been triggered!\n"
        f"Condition: Price went {direction} ₹{target}\n"
        f"Current Price: ₹{current:.2f}\n\n"
        f"— TradeMetrix"
    )

    from core.notifications import send_alert_email as _email, send_alert_sms as _sms, send_alert_whatsapp as _whatsapp

    prefs = safe_execute(
        supabase.table("notification_prefs").select("channels").eq("user_id", user_id)
    )
    channels = prefs[0].get("channels", ["email"]) if prefs else ["email"]

    sent = False
    if "whatsapp" in channels and phone:
        sent = await _whatsapp(phone, body) or sent
    if "sms" in channels and phone:
        sent = await _sms(phone, body) or sent
    if "email" in channels and email:
        sent = await _email(email, subject, body) or sent
    if not sent:
        logger.info("[DEV] Alert triggered but no notification sent: %s %s ₹%s", symbol, condition, target)


async def start_alert_checker() -> None:
    global _alert_task
    if _alert_task and not _alert_task.done():
        logger.info("Alert checker already running")
        return
    shared_socket.subscribe("*", _check_alerts)
    logger.info("Alert checker started — subscribed to all ticks")


async def stop_alert_checker() -> None:
    global _alert_task
    shared_socket.unsubscribe("*", _check_alerts)
    logger.info("Alert checker stopped")
