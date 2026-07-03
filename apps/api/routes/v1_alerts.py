import asyncio
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.audit import record_audit
from core.db import async_supabase, get_supabase
from core.deps import get_current_user
from core.models import AuditLogEntry, UserProfile
from core.safe_query import safe_execute, safe_single

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


class CreateAlertRequest(BaseModel):
    symbol: str
    condition: str
    target_price: float
    note: str = ""


class AlertResponse(BaseModel):
    id: str
    symbol: str
    condition: str
    target_price: float
    is_active: bool
    triggered_at: str | None
    note: str
    created_at: str


@router.get("/")
async def list_alerts(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    data = safe_execute(
        supabase.table("user_alerts")
        .select("*")
        .eq("user_id", current_user.id)
        .order("created_at", desc=True)
    ) or []
    return {"alerts": data}


@router.post("/", status_code=201)
async def create_alert(
    req: CreateAlertRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    if req.condition not in ("above", "below"):
        raise HTTPException(status_code=400, detail="condition must be 'above' or 'below'")

    supabase = get_supabase()
    payload = {
        "user_id": current_user.id,
        "symbol": req.symbol.upper(),
        "condition": req.condition,
        "target_price": req.target_price,
        "note": req.note,
    }
    result = await async_supabase(lambda: supabase.table("user_alerts").insert(payload).execute())
    new = result.data[0]

    record_audit(AuditLogEntry(
        user_id=current_user.id,
        action="create_alert",
        resource="user_alerts",
        resource_id=new["id"],
        details={"symbol": req.symbol, "condition": req.condition, "target_price": req.target_price},
    ))

    return AlertResponse(
        id=new["id"], symbol=new["symbol"], condition=new["condition"],
        target_price=new["target_price"], is_active=new.get("is_active", True),
        triggered_at=new.get("triggered_at"), note=new.get("note", ""),
        created_at=new.get("created_at", ""),
    )


@router.delete("/{alert_id}", status_code=204)
async def delete_alert(
    alert_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    alert = safe_single(
        supabase.table("user_alerts").select("id").eq("id", alert_id).eq("user_id", current_user.id)
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    await async_supabase(lambda: supabase.table("user_alerts").delete().eq("id", alert_id).execute())


@router.post("/{alert_id}/toggle")
async def toggle_alert(
    alert_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    alert = safe_single(
        supabase.table("user_alerts").select("id, is_active").eq("id", alert_id).eq("user_id", current_user.id)
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    new_status = not alert.get("is_active", True)
    await async_supabase(lambda: supabase.table("user_alerts").update({"is_active": new_status}).eq("id", alert_id).execute())
    return {"is_active": new_status}


class NotificationPrefsRequest(BaseModel):
    channels: list[str]


@router.get("/notification-prefs")
async def get_notification_prefs(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    prefs = safe_single(
        supabase.table("notification_prefs").select("*").eq("user_id", current_user.id)
    )
    if not prefs:
        return {"channels": ["email"]}
    return {"channels": prefs.get("channels", ["email"])}


@router.put("/notification-prefs")
async def update_notification_prefs(
    req: NotificationPrefsRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    for c in req.channels:
        if c not in ("email", "sms", "whatsapp"):
            raise HTTPException(status_code=400, detail=f"Invalid channel: {c}")
    supabase = get_supabase()
    existing = safe_single(
        supabase.table("notification_prefs").select("id").eq("user_id", current_user.id)
    )
    if existing:
        await async_supabase(lambda: supabase.table("notification_prefs").update({
            "channels": req.channels, "updated_at": datetime.now(UTC).isoformat(),
        }).eq("id", existing["id"]).execute())
    else:
        await async_supabase(lambda: supabase.table("notification_prefs").insert({
            "user_id": current_user.id, "channels": req.channels,
        }).execute())
    return {"channels": req.channels}
