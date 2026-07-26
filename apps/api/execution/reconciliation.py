import asyncio
import logging
from datetime import UTC, datetime

from core.db import async_supabase, get_supabase
from core.notifications import send_telegram_alert
from core.safe_query import async_safe_execute

logger = logging.getLogger(__name__)

async def reconcile_user_positions(user_id: str, broker: str) -> dict:
    from execution.broker_adapter import BrokerExecutionAdapter
    adapter = BrokerExecutionAdapter(user_id, broker)
    connected = await adapter.connect()
    if not connected:
        return {"success": False, "message": "Broker unreachable"}

    remote_positions = await adapter.get_positions()
    if not remote_positions:
        return {"success": True, "message": "No remote positions", "mismatches": []}

    supabase = get_supabase()
    db_positions = await async_safe_execute(
        supabase.table("positions_snapshot")
        .select("symbol, quantity, product")
        .eq("user_id", user_id)
        .eq("broker", broker)
    ) or []

    db_by_symbol = {p["symbol"]: p for p in db_positions}
    mismatches = []

    for rp in remote_positions:
        symbol = rp.symbol
        dbp = db_by_symbol.get(symbol)
        remote_qty = rp.quantity or 0
        db_qty = dbp["quantity"] if dbp else 0
        if abs(remote_qty - db_qty) > 0:
            mismatches.append({
                "symbol": symbol,
                "remote_qty": remote_qty,
                "db_qty": db_qty,
                "diff": remote_qty - db_qty,
            })

    return {
        "success": True,
        "remote_count": len(remote_positions),
        "db_count": len(db_positions),
        "mismatches": mismatches,
        "mismatch_count": len(mismatches),
    }
    if mismatches:
        msg = (
            f"\U0001f534 <b>Position Mismatch</b>\n"
            f"User: {user_id[:8]}...\n"
            f"Broker: {broker.upper()}\n"
            f"Mismatches: {len(mismatches)}\n"
        )
        for m in mismatches[:5]:
            msg += f"{m['symbol']}: remote={m['remote_qty']} db={m['db_qty']} diff={m['diff']:+d}\n"
        if len(mismatches) > 5:
            msg += f"... and {len(mismatches) - 5} more"
        await send_telegram_alert(msg)

async def sync_all_positions():
    supabase = get_supabase()
    active_users = await async_safe_execute(
        supabase.table("broker_credentials")
        .select("user_id, broker")
        .eq("is_active", True)
    ) or []
    results = []
    for cred in active_users:
        try:
            r = await reconcile_user_positions(cred["user_id"], cred["broker"])
            results.append({"user_id": cred["user_id"], "broker": cred["broker"], **r})
        except Exception as e:
            logger.warning("Position sync failed user=%s broker=%s: %s", cred["user_id"], cred["broker"], e)
    return results
