import hashlib
import logging
from datetime import UTC, datetime
from core.config import settings
import os

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from brokers import list_brokers
from brokers.registry import get_broker_metadata
from core.audit import record_audit
from core.db import async_supabase, get_supabase
from core.deps import get_current_user
from core.models import AuditLogEntry, UserProfile
from core.safe_query import async_safe_single, async_safe_execute, safe_execute, safe_single
from core.security import decrypt_broker_credentials, encrypt_broker_credentials
from core.http_client import get_http_client

router = APIRouter(prefix="/brokers", tags=["brokers"])


class BrokerCredentialInput(BaseModel):
    broker: str
    api_key: str = ""
    secret_key: str = ""
    client_id: str = ""
    client_code: str = ""
    access_token: str = ""
    additional_params: dict = {}


class BrokerCredentialResponse(BaseModel):
    id: str
    broker: str
    is_active: bool


class ActivateBrokerRequest(BaseModel):
    broker: str


@router.get("/list")
async def list_available_brokers():
    return {"brokers": list_brokers()}


@router.get("/metadata")
async def list_broker_metadata():
    return {"brokers": get_broker_metadata()}


@router.get("/metadata/{broker}")
async def broker_metadata(broker: str):
    try:
        return get_broker_metadata(broker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/credentials")
async def get_credentials(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    data = await async_safe_execute(
        supabase.table("broker_credentials")
        .select("id, broker, is_active, created_at")
        .eq("user_id", current_user.id)
    )
    return {"credentials": data or []}


@router.post("/activate")
async def activate_broker(
    req: ActivateBrokerRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    target = await async_safe_single(
        supabase.table("broker_credentials")
        .select("id")
        .eq("user_id", current_user.id)
        .eq("broker", req.broker)
    )
    if not target:
        raise HTTPException(status_code=404, detail=f"No credentials found for broker '{req.broker}'")

    await async_supabase(lambda: supabase.table("broker_credentials").update({"is_active": False}).eq("user_id", current_user.id).neq("broker", req.broker).execute())
    await async_supabase(lambda: supabase.table("broker_credentials").update({"is_active": True}).eq("id", target["id"]).execute())

    record_audit(AuditLogEntry(
        user_id=current_user.id,
        action="activate_broker",
        resource="broker_credentials",
        resource_id=target["id"],
        details={"broker": req.broker},
    ))

    return {"message": f"Broker '{req.broker}' activated", "broker": req.broker}


@router.post("/credentials", status_code=201)
async def save_credentials(
    req: BrokerCredentialInput,
    current_user: UserProfile = Depends(get_current_user),
):
    if req.broker not in list_brokers():
        raise HTTPException(status_code=400, detail=f"Unsupported broker: {req.broker}")

    api_key = req.api_key or req.client_id or req.client_code or ""
    secret_key = req.secret_key or ""
    access_token = req.access_token or ""

    supabase = get_supabase()
    existing = await async_safe_single(
        supabase.table("broker_credentials")
        .select("id")
        .eq("user_id", current_user.id)
        .eq("broker", req.broker)
    )
    payload: dict = {
        "encrypted_api_key": encrypt_broker_credentials(api_key),
        "encrypted_secret_key": encrypt_broker_credentials(secret_key),
        "additional_params": req.additional_params,
    }
    if access_token:
        payload["encrypted_access_token"] = encrypt_broker_credentials(access_token)

    try:
        if existing:
            result = await async_supabase(lambda: supabase.table("broker_credentials").update(payload).eq("id", existing["id"]).execute())
            inserted = result.data[0] if result.data else existing
            action = "update_broker"
        else:
            payload["user_id"] = current_user.id
            payload["broker"] = req.broker
            if access_token:
                payload["encrypted_access_token"] = encrypt_broker_credentials(access_token)
            else:
                payload["encrypted_access_token"] = ""
            result = await async_supabase(lambda: supabase.table("broker_credentials").insert(payload).execute())
            inserted = result.data[0]
            action = "add_broker"
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save credentials: {e}")

    record_audit(AuditLogEntry(
        user_id=current_user.id,
        action=action,
        resource="broker_credentials",
        resource_id=inserted.get("id", ""),
        details={"broker": req.broker},
    ))

    return BrokerCredentialResponse(id=inserted.get("id", ""), broker=req.broker, is_active=inserted.get("is_active", False))


@router.delete("/credentials/{broker_name}", status_code=204)
async def delete_credentials(
    broker_name: str,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    try:
        result = await async_supabase(lambda: supabase.table("broker_credentials").delete().eq("user_id", current_user.id).eq("broker", broker_name).execute())
        if not result.data:
            raise HTTPException(status_code=404, detail="Credentials not found")
    except HTTPException:
        raise
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("Failed to delete broker credentials: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete credentials")

    record_audit(AuditLogEntry(
        user_id=current_user.id,
        action="remove_broker",
        resource="broker_credentials",
        resource_id="",
        details={"broker": broker_name},
    ))


from urllib.parse import urlencode

FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI") or settings.fyers_redirect_uri or "https://api.ai.trademetrix.tech/api/v1/brokers/fyers/callback"


def _fyers_auth_url(client_id: str, state: str) -> str:
    params = urlencode({
        "client_id": client_id,
        "redirect_uri": FYERS_REDIRECT_URI,
        "response_type": "code",
        "state": state,
    })
    return f"https://api-t1.fyers.in/api/v3/generate-authcode?{params}"


@router.post("/fyers/re-auth")
async def fyers_re_auth(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    cred = await async_safe_single(
        supabase.table("broker_credentials")
        .select("id, broker")
        .eq("user_id", current_user.id)
        .eq("broker", "fyers")
    )
    if not cred:
        raise HTTPException(status_code=400, detail="No Fyers credentials found. Save them first.")

    row = await async_supabase(lambda: supabase.table("broker_credentials").select("encrypted_api_key").eq("id", cred["id"]).single().execute())
    client_id = decrypt_broker_credentials(row.data["encrypted_api_key"])

    await async_supabase(lambda: supabase.table("broker_credentials").update(
        {"is_active": False, "encrypted_access_token": ""}
    ).eq("id", cred["id"]).execute())

    return {"auth_url": _fyers_auth_url(client_id, current_user.id)}


@router.get("/fyers/auth-url")
async def fyers_auth_url(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    cred = await async_safe_single(
        supabase.table("broker_credentials")
        .select("id, broker")
        .eq("user_id", current_user.id)
        .eq("broker", "fyers")
    )
    if not cred:
        raise HTTPException(status_code=400, detail="Save Fyers credentials first (APP ID as api_key, secret as secret_key)")

    row = await async_supabase(lambda: supabase.table("broker_credentials").select("encrypted_api_key").eq("id", cred["id"]).single().execute())
    client_id = decrypt_broker_credentials(row.data["encrypted_api_key"])
    return {"auth_url": _fyers_auth_url(client_id, current_user.id)}


class FyersAuthCodeInput(BaseModel):
    auth_code: str


@router.post("/fyers/exchange-code")
async def fyers_exchange_code(
    req: FyersAuthCodeInput,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    cred = await async_safe_single(
        supabase.table("broker_credentials")
        .select("*")
        .eq("user_id", current_user.id)
        .eq("broker", "fyers")
    )
    if not cred:
        raise HTTPException(status_code=400, detail="No Fyers credentials found. Save them first.")

    client_id = decrypt_broker_credentials(cred["encrypted_api_key"])
    secret_key = decrypt_broker_credentials(cred["encrypted_secret_key"])

    client = await get_http_client()
    app_id_hash = hashlib.sha256(f"{client_id}:{secret_key}".encode()).hexdigest()
    resp = await client.post(
        "https://api-t1.fyers.in/api/v3/validate-authcode",
        json={
            "grant_type": "authorization_code",
            "appIdHash": app_id_hash,
            "code": req.auth_code,
        },
    )
    data = resp.json()
    if data.get("s") != "ok":
        msg = data.get("message", data.get("errmsg", "unknown"))
        logger.error("Fyers token exchange failed: status=%d body=%s", resp.status_code, data)
        raise HTTPException(status_code=400, detail=f"Fyers auth failed: {msg}")

    raw_token = data["access_token"]
    encrypted = encrypt_broker_credentials(raw_token)
    await async_supabase(lambda: supabase.table("broker_credentials").update(
        {"encrypted_access_token": encrypted, "is_active": True, "updated_at": datetime.now(UTC).isoformat()}
    ).eq("id", cred["id"]).execute())

    return {"message": "Fyers authenticated successfully!"}


@router.get("/fyers/callback")
async def fyers_callback(
    auth_code: str = Query(alias="auth_code"),
    state: str | None = Query(None),
):
    from fastapi.responses import RedirectResponse

    logger.info("Fyers callback HIT: auth_code=%s state=%s", auth_code[:20] if auth_code else "none", state)

    FRONTEND_URL = f"{settings.frontend_url or 'https://ai.trademetrix.tech'}/brokers"

    supabase = get_supabase()
    cred = await async_safe_single(
        supabase.table("broker_credentials")
        .select("*")
        .eq("user_id", state)
        .eq("broker", "fyers")
    )
    if not cred:
        return RedirectResponse(url=f"{FRONTEND_URL}?auth_error=No+Fyers+credentials+found")

    client_id = decrypt_broker_credentials(cred["encrypted_api_key"])
    secret_key = decrypt_broker_credentials(cred["encrypted_secret_key"])

    logger.info("Fyers callback: auth_code=%s... state=%s", auth_code[:20] if auth_code else "none", state)

    client = await get_http_client()
    app_id_hash = hashlib.sha256(f"{client_id}:{secret_key}".encode()).hexdigest()
    resp = await client.post(
        "https://api-t1.fyers.in/api/v3/validate-authcode",
        json={
            "grant_type": "authorization_code",
            "appIdHash": app_id_hash,
            "code": auth_code,
        },
    )
    data = resp.json()
    logger.info("Fyers callback response: status=%d body=%s", resp.status_code, data)
    if data.get("s") != "ok":
        msg = data.get("message", data.get("errmsg", "unknown"))
        return RedirectResponse(url=f"{FRONTEND_URL}?auth_error=Fyers+auth+failed:+{msg}")

    raw_token = data["access_token"]
    encrypted = encrypt_broker_credentials(raw_token)
    await async_supabase(lambda: supabase.table("broker_credentials").update(
        {"encrypted_access_token": encrypted, "is_active": True, "updated_at": datetime.now(UTC).isoformat()}
    ).eq("id", cred["id"]).execute())

    return RedirectResponse(url=f"{FRONTEND_URL}?auth_success=1")
