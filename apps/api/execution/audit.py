import hashlib
import json
import logging
from datetime import UTC, datetime

from core.db import async_supabase, get_supabase

logger = logging.getLogger(__name__)


def compute_payload_hash(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


async def log_execution_event(
    user_id: str,
    broker: str,
    action: str,
    execution_request_id: str = "",
    broker_order_id: str = "",
    symbol: str = "",
    side: str = "",
    quantity: int = 0,
    price: float = 0.0,
    latency_ms: float = 0.0,
    status: str = "",
    message: str = "",
    payload: dict | None = None,
    result: dict | None = None,
) -> None:
    try:
        supabase = get_supabase()
        entry = {
            "user_id": user_id,
            "broker": broker,
            "action": action,
            "resource": "order",
            "execution_request_id": execution_request_id,
            "broker_order_id": broker_order_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "latency_ms": latency_ms,
            "status": status,
            "message": message,
            "payload_hash": compute_payload_hash(payload or {}),
            "result": json.dumps(result) if result else "",
            "created_at": datetime.now(UTC).isoformat(),
        }
        await async_supabase(lambda: supabase.table("audit_log").insert(entry).execute())
    except Exception as e:
        logger.error("Failed to write execution audit log: %s", e)


async def log_validation_failure(
    user_id: str,
    broker: str,
    errors: list[dict],
    payload: dict | None = None,
) -> None:
    try:
        supabase = get_supabase()
        entry = {
            "user_id": user_id,
            "broker": broker,
            "action": "validation_failed",
            "resource": "order",
            "status": "rejected",
            "message": json.dumps(errors),
            "payload_hash": compute_payload_hash(payload or {}),
            "created_at": datetime.now(UTC).isoformat(),
        }
        await async_supabase(lambda: supabase.table("audit_log").insert(entry).execute())
    except Exception as e:
        logger.error("Failed to write validation audit: %s", e)
