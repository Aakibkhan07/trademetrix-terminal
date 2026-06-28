from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from brokers import list_brokers, get_broker
from core.deps import get_current_user
from core.db import get_supabase
from core.security import encrypt_broker_credentials
from core.models import UserProfile
from core.audit import record_audit
from core.models import AuditLogEntry

router = APIRouter(prefix="/brokers", tags=["brokers"])


class BrokerCredentialInput(BaseModel):
    broker: str
    api_key: str
    secret_key: str
    access_token: str = ""
    additional_params: dict = {}


class BrokerCredentialResponse(BaseModel):
    id: str
    broker: str
    is_active: bool


@router.get("/list")
async def list_available_brokers():
    return {"brokers": list_brokers()}


@router.get("/credentials")
async def get_credentials(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    result = (
        supabase.table("broker_credentials")
        .select("id, broker, is_active, created_at")
        .eq("user_id", current_user.id)
        .execute()
    )
    return {"credentials": result.data or []}


@router.post("/credentials", status_code=201)
async def save_credentials(
    req: BrokerCredentialInput,
    current_user: UserProfile = Depends(get_current_user),
):
    if req.broker not in list_brokers():
        raise HTTPException(status_code=400, detail=f"Unsupported broker: {req.broker}")

    supabase = get_supabase()
    existing = (
        supabase.table("broker_credentials")
        .select("id")
        .eq("user_id", current_user.id)
        .eq("broker", req.broker)
        .maybe_single()
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=409, detail="Broker already registered")

    data = {
        "user_id": current_user.id,
        "broker": req.broker,
        "encrypted_api_key": encrypt_broker_credentials(req.api_key),
        "encrypted_secret_key": encrypt_broker_credentials(req.secret_key),
        "encrypted_access_token": encrypt_broker_credentials(req.access_token) if req.access_token else "",
        "additional_params": req.additional_params,
    }
    result = supabase.table("broker_credentials").insert(data).execute()
    inserted = result.data[0]

    record_audit(AuditLogEntry(
        user_id=current_user.id,
        action="add_broker",
        resource="broker_credentials",
        resource_id=inserted["id"],
        details={"broker": req.broker},
    ))

    return BrokerCredentialResponse(id=inserted["id"], broker=req.broker, is_active=inserted["is_active"])


@router.delete("/credentials/{broker_name}", status_code=204)
async def delete_credentials(
    broker_name: str,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    result = (
        supabase.table("broker_credentials")
        .delete()
        .eq("user_id", current_user.id)
        .eq("broker", broker_name)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Credentials not found")

    record_audit(AuditLogEntry(
        user_id=current_user.id,
        action="remove_broker",
        resource="broker_credentials",
        resource_id="",
        details={"broker": broker_name},
    ))
