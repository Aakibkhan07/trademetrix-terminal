import asyncio
from datetime import UTC, datetime
from core.config import settings
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from brokers import list_brokers
from brokers.registry import get_broker_metadata
from core.audit import record_audit
from core.db import async_supabase, get_supabase
from core.deps import get_current_user
from core.models import AuditLogEntry, UserProfile
from core.safe_query import safe_execute, safe_single
from core.security import decrypt_broker_credentials, encrypt_broker_credentials

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
    data = safe_execute(
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
    target = safe_single(
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
    existing = safe_single(
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


FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI") or settings.fyers_redirect_uri or "https://api.ai.trademetrix.tech/api/v1/brokers/fyers/callback"


def _fyers_auth_url(client_id: str, state: str) -> str:
    return (
        f"https://api-t1.fyers.in/api/v3/generate-authcode"
        f"?client_id={client_id}"
        f"&redirect_uri={FYERS_REDIRECT_URI}"
        f"&response_type=code"
        f"&state={state}"
    )


@router.post("/fyers/re-auth")
async def fyers_re_auth(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    cred = safe_single(
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
    cred = safe_single(
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
    cred = safe_single(
        supabase.table("broker_credentials")
        .select("*")
        .eq("user_id", current_user.id)
        .eq("broker", "fyers")
    )
    if not cred:
        raise HTTPException(status_code=400, detail="No Fyers credentials found. Save them first.")

    client_id = decrypt_broker_credentials(cred["encrypted_api_key"])
    secret_key = decrypt_broker_credentials(cred["encrypted_secret_key"])

    from fyers_apiv3 import fyersModel

    def _exchange():
        s = fyersModel.SessionModel(
            client_id=client_id,
            secret_key=secret_key,
            redirect_uri=FYERS_REDIRECT_URI,
            grant_type="authorization_code",
        )
        s.set_token(req.auth_code)
        return s.generate_token()

    data = await asyncio.get_running_loop().run_in_executor(None, _exchange)
    if data.get("s") != "ok":
        raise HTTPException(status_code=400, detail=f"Fyers auth failed: {data.get('message', '')}")

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

    FRONTEND_URL = f"{settings.frontend_url or 'https://ai.trademetrix.tech'}/brokers"

    supabase = get_supabase()
    cred = safe_single(
        supabase.table("broker_credentials")
        .select("*")
        .eq("user_id", state)
        .eq("broker", "fyers")
    )
    if not cred:
        return RedirectResponse(url=f"{FRONTEND_URL}?auth_error=No+Fyers+credentials+found")

    client_id = decrypt_broker_credentials(cred["encrypted_api_key"])
    secret_key = decrypt_broker_credentials(cred["encrypted_secret_key"])

    from fyers_apiv3 import fyersModel

    def _exchange():
        s = fyersModel.SessionModel(
            client_id=client_id,
            secret_key=secret_key,
            redirect_uri=FYERS_REDIRECT_URI,
            grant_type="authorization_code",
        )
        s.set_token(auth_code)
        return s.generate_token()

    data = await asyncio.get_running_loop().run_in_executor(None, _exchange)
    if data.get("s") != "ok":
        return RedirectResponse(url=f"{FRONTEND_URL}?auth_error=Fyers+auth+failed")

    raw_token = data["access_token"]
    encrypted = encrypt_broker_credentials(raw_token)
    await async_supabase(lambda: supabase.table("broker_credentials").update(
        {"encrypted_access_token": encrypted, "is_active": True, "updated_at": datetime.now(UTC).isoformat()}
    ).eq("id", cred["id"]).execute())

    return RedirectResponse(url=f"{FRONTEND_URL}?auth_success=1")
