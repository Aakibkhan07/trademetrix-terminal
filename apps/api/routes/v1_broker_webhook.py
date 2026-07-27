import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, Request

from core.cache import cache
from core.db import get_supabase
from core.notifications import send_telegram_alert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/brokers/webhook", tags=["broker-webhooks"])

WEBHOOK_SECRET_CACHE_KEY = "system:webhook_secret"

BROKER_ORDER_TYPES = {"BASKET", "NORMAL", "STOPLOSS", "AMO"}


@router.post("/order-update")
async def broker_order_update(request: Request, x_webhook_secret: str = Header(default="", alias="X-Webhook-Secret")):
    secret = await cache.get(WEBHOOK_SECRET_CACHE_KEY)
    if secret and x_webhook_secret != secret:
        logger.warning("Webhook rejected: invalid secret from %s", request.client.host if request.client else "unknown")
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    try:
        body = await request.json()
    except Exception:
        return {"success": False, "message": "Invalid JSON"}

    broker = body.get("broker", "")
    broker_order_id = body.get("order_id", "")
    status = body.get("status", "")
    filled_qty = body.get("filled_qty", 0)
    avg_price = body.get("avg_price", 0.0)
    rejection_reason = body.get("rejection_reason", "")
    order_type = body.get("order_type", "")

    if not broker or not broker_order_id:
        return {"success": False, "message": "broker and order_id required"}

    if order_type and order_type.upper() not in BROKER_ORDER_TYPES:
        logger.warning("Webhook: unexpected order_type=%s from broker=%s", order_type, broker)

    update = {"status": status, "updated_at": datetime.now(UTC).isoformat()}
    if filled_qty is not None:
        update["filled_quantity"] = filled_qty
    if avg_price is not None:
        update["average_price"] = avg_price
    if rejection_reason:
        update["message"] = rejection_reason

    try:
        supabase = get_supabase()
        result = await supabase.table("orders").update(update).eq("broker_order_id", broker_order_id).execute()
        if not result.data:
            logger.warning("Webhook: no order matched broker_order_id=%s", broker_order_id)
        logger.info("Order status updated via webhook: %s -> %s", broker_order_id, status)
        await send_telegram_alert(
            f"\U0001f514 <b>Order Update via Webhook</b>\n"
            f"Broker: {broker.upper()}\n"
            f"Order: {broker_order_id[:12]}...\n"
            f"Status: {status}\n"
            f"Filled: {filled_qty} @ {avg_price}"
        )
    except Exception as e:
        logger.warning("Failed to update order from webhook: %s", e)

    return {"success": True}