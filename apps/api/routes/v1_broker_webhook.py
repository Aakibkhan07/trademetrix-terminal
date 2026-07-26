import logging

from fastapi import APIRouter, Request

from core.db import get_supabase
from core.notifications import send_telegram_alert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/brokers/webhook", tags=["broker-webhooks"])

@router.post("/order-update")
async def broker_order_update(request: Request):
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

    if not broker or not broker_order_id:
        return {"success": False, "message": "broker and order_id required"}

    update = {"status": status, "updated_at": "now()"}
    if filled_qty:
        update["filled_quantity"] = filled_qty
    if avg_price:
        update["average_price"] = avg_price
    if rejection_reason:
        update["message"] = rejection_reason

    try:
        supabase = get_supabase()
        await supabase.table("orders").update(update).eq("broker_order_id", broker_order_id).execute()
        logger.info("Order status updated via webhook: %s \u2192 %s", broker_order_id, status)
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