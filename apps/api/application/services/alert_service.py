import logging
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import HTTPException

from core.audit import record_audit
from core.db import async_supabase, get_supabase
from core.models import AuditLogEntry
from core.safe_query import async_safe_execute, async_safe_single

logger = logging.getLogger(__name__)


class AlertService:
    async def list_alerts(self, user_id: str) -> dict:
        supabase = get_supabase()
        data = await async_safe_execute(
            supabase.table("user_alerts").select("*").eq("user_id", user_id).order("created_at", desc=True)
        ) or []
        return {"alerts": data}

    async def create_alert(self, user_id: str, symbol: str, condition: str, target_price: float, note: str) -> dict:
        if condition not in ("above", "below"):
            raise HTTPException(status_code=400, detail="condition must be 'above' or 'below'")
        supabase = get_supabase()
        payload: dict[str, Any] = {
            "user_id": user_id,
            "symbol": symbol.upper(),
            "condition": condition,
            "target_price": target_price,
            "note": note,
        }
        result = await async_supabase(lambda: supabase.table("user_alerts").insert(payload).execute())
        new = cast(dict[str, Any], result.data[0])
        record_audit(AuditLogEntry(
            user_id=user_id,
            action="create_alert",
            resource="user_alerts",
            resource_id=new["id"],
            details={"symbol": symbol, "condition": condition, "target_price": target_price},
        ))
        return {
            "id": new["id"],
            "symbol": new["symbol"],
            "condition": new["condition"],
            "target_price": new["target_price"],
            "is_active": new.get("is_active", True),
            "triggered_at": new.get("triggered_at"),
            "note": new.get("note", ""),
            "created_at": new.get("created_at", ""),
        }

    async def delete_alert(self, user_id: str, alert_id: str) -> None:
        supabase = get_supabase()
        alert = await async_safe_single(
            supabase.table("user_alerts").select("id").eq("id", alert_id).eq("user_id", user_id)
        )
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        await async_supabase(lambda: supabase.table("user_alerts").delete().eq("id", alert_id).execute())

    async def toggle_alert(self, user_id: str, alert_id: str) -> dict:
        supabase = get_supabase()
        alert = await async_safe_single(
            supabase.table("user_alerts").select("id, is_active").eq("id", alert_id).eq("user_id", user_id)
        )
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        new_status = not alert.get("is_active", True)
        await async_supabase(lambda: supabase.table("user_alerts").update({"is_active": new_status}).eq("id", alert_id).execute())
        return {"is_active": new_status}

    async def get_notification_prefs(self, user_id: str) -> dict:
        supabase = get_supabase()
        prefs = await async_safe_single(
            supabase.table("notification_prefs").select("*").eq("user_id", user_id)
        )
        if not prefs:
            return {"channels": ["email"]}
        return {"channels": prefs.get("channels", ["email"])}

    async def update_notification_prefs(self, user_id: str, channels: list[str]) -> dict:
        for c in channels:
            if c not in ("email", "sms", "whatsapp"):
                raise HTTPException(status_code=400, detail=f"Invalid channel: {c}")
        supabase = get_supabase()
        existing = await async_safe_single(
            supabase.table("notification_prefs").select("id").eq("user_id", user_id)
        )
        if existing:
            await async_supabase(lambda: supabase.table("notification_prefs").update({
                "channels": channels, "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", existing["id"]).execute())
        else:
            await async_supabase(lambda: supabase.table("notification_prefs").insert({
                "user_id": user_id, "channels": channels,
            }).execute())
        return {"channels": channels}
