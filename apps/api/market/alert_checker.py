import asyncio
import logging
from datetime import UTC, datetime

from core.db import async_supabase, get_supabase
from core.safe_query import async_safe_execute
from market.cache import market_cache

logger = logging.getLogger(__name__)

_alert_task = None
_cached_alerts: list[dict] = []
_last_refresh: float = 0
_ALERT_CACHE_TTL = 30.0


async def _refresh_alerts_cache() -> None:
    global _cached_alerts, _last_refresh
    supabase = get_supabase()
    rows = await async_safe_execute(
        supabase.table("user_alerts")
        .select("id, user_id, symbol, condition, target_price, is_active")
        .eq("is_active", True)
        .is_("triggered_at", "null")
    ) or []
    _cached_alerts = rows
    _last_refresh = __import__("time").time()
    logger.debug("Refreshed alert cache: %d active alerts", len(rows))


async def _ensure_alerts_fresh() -> None:
    import time
    if time.time() - _last_refresh > _ALERT_CACHE_TTL:
        await _refresh_alerts_cache()


async def _check_alerts_loop() -> None:
    await _refresh_alerts_cache()
    while True:
        await asyncio.sleep(2)
        try:
            await _ensure_alerts_fresh()
            if not _cached_alerts:
                continue
            all_ticks = market_cache.get_all_ticks()
            triggered = []
            for alert in _cached_alerts:
                symbol = alert.get("symbol", "")
                tick = all_ticks.get(symbol) or all_ticks.get(f"NSE:{symbol}")
                if not tick:
                    sym_key = next((k for k in all_ticks if symbol in k), None)
                    if sym_key:
                        tick = all_ticks[sym_key]
                if not tick:
                    continue
                price = tick.last_price or 0
                condition = alert.get("condition")
                target = alert.get("target_price", 0)
                if (condition == "above" and price >= target) or (condition == "below" and price <= target):
                    triggered.append(alert)
            for alert in triggered:
                await _fire_alert(alert)
        except Exception as e:
            logger.error("Alert check loop error: %s", e)


async def _fire_alert(alert: dict) -> None:
    supabase = get_supabase()
    alert_id = alert["id"]
    symbol = alert.get("symbol", "")
    condition = alert.get("condition", "")
    target = alert.get("target_price", 0)
    user_id = alert.get("user_id", "")
    price = market_cache.get_tick(symbol)
    current = price.last_price if price else 0

    await async_supabase(lambda: supabase.table("user_alerts").update({
        "triggered_at": datetime.now(UTC).isoformat(),
        "is_active": False,
    }).eq("id", alert_id).execute())

    try:
        await _send_alert_notification(user_id, alert_id, symbol, condition, target, current)
    except Exception as e:
        logger.error("Alert notification failed user=%s alert=%s: %s", user_id, alert_id, e)


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

    prefs = await async_safe_execute(
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
    _alert_task = asyncio.create_task(_check_alerts_loop())
    logger.info("Alert checker started — polling every 2s")


async def stop_alert_checker() -> None:
    global _alert_task
    if _alert_task and not _alert_task.done():
        _alert_task.cancel()
        _alert_task = None
    logger.info("Alert checker stopped")
