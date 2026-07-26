import asyncio
import logging
from datetime import UTC, datetime

from core.db import async_supabase, get_supabase
from core.safe_query import async_safe_execute
from execution.broker_adapter import BrokerExecutionAdapter

logger = logging.getLogger(__name__)

PENDING_ORDER_MAX_AGE_SECONDS = 300

async def reconcile_pending_orders():
    supabase = get_supabase()
    cutoff = datetime.now(UTC).isoformat()
    orders = await async_safe_execute(
        supabase.table("orders")
        .select("user_id, broker, broker_order_id, client_order_id, symbol, side, quantity, status, created_at")
        .in_("status", ["PENDING", "SENT", "NEW"])
        .lte("created_at", cutoff)
    ) or []
    if not orders:
        logger.info("No pending orders to reconcile")
        return {"reconciled": 0, "orders": []}

    results = []
    for o in orders:
        uid = o["user_id"]
        broker = o.get("broker", "")
        bo_id = o.get("broker_order_id", "")
        if not bo_id or not broker:
            status = "FAILED"
            await _mark_order(uid, bo_id, status, "No broker_order_id")
            results.append({"order_id": bo_id, "status": status})
            continue
        try:
            adapter = BrokerExecutionAdapter(uid, broker)
            connected = await adapter.connect()
            if not connected:
                status = "FAILED"
                await _mark_order(uid, bo_id, status, "Broker unreachable")
                results.append({"order_id": bo_id, "status": status})
                continue
            remote = await adapter.get_order(bo_id)
            if remote and remote.status:
                rs = remote.status.value if hasattr(remote.status, "value") else str(remote.status)
                if rs in ("FILLED", "COMPLETE", "TRADED", "EXECUTED"):
                    status = "FILLED"
                    await _mark_order(uid, bo_id, status, "Reconciled from broker")
                elif rs in ("REJECTED", "CANCELLED", "EXPIRED"):
                    status = rs
                    await _mark_order(uid, bo_id, status, f"Reconciled from broker ({rs})")
                else:
                    await _touch_order(uid, bo_id)
                    status = rs
                results.append({"order_id": bo_id, "status": status, "remote_status": rs})
            else:
                await _touch_order(uid, bo_id)
                results.append({"order_id": bo_id, "status": "UNCHANGED"})
        except Exception as e:
            logger.warning("Recovery check failed for order=%s user=%s: %s", bo_id, uid, e)
            results.append({"order_id": bo_id, "status": "ERROR"})

    return {"reconciled": len(results), "orders": results}

async def _mark_order(user_id: str, broker_order_id: str, status: str, message: str):
    try:
        supabase = get_supabase()
        await async_supabase(lambda: supabase.table("orders").update({
            "status": status, "message": message, "filled_at": datetime.now(UTC).isoformat() if status == "FILLED" else None,
        }).eq("user_id", user_id).eq("broker_order_id", broker_order_id).execute())
    except Exception as e:
        logger.error("Failed to mark order %s: %s", broker_order_id, e)

async def _touch_order(user_id: str, broker_order_id: str):
    try:
        supabase = get_supabase()
        await async_supabase(lambda: supabase.table("orders").update({
            "updated_at": datetime.now(UTC).isoformat(),
        }).eq("user_id", user_id).eq("broker_order_id", broker_order_id).execute())
    except Exception:
        pass
