import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from brokers import list_brokers
from core.audit import record_audit
from core.db import get_supabase
from core.deps import get_current_user
from core.models import AuditLogEntry, UserProfile
from core.safe_query import safe_execute, safe_single
from core.security import decrypt_broker_credentials, encrypt_broker_credentials

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
    data = safe_execute(
        supabase.table("broker_credentials")
        .select("id, broker, is_active, created_at")
        .eq("user_id", current_user.id)
    )
    return {"credentials": data or []}


@router.post("/credentials", status_code=201)
async def save_credentials(
    req: BrokerCredentialInput,
    current_user: UserProfile = Depends(get_current_user),
):
    if req.broker not in list_brokers():
        raise HTTPException(status_code=400, detail=f"Unsupported broker: {req.broker}")

    supabase = get_supabase()
    existing = safe_single(
        supabase.table("broker_credentials")
        .select("id")
        .eq("user_id", current_user.id)
        .eq("broker", req.broker)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Broker already registered")

    payload = {
        "user_id": current_user.id,
        "broker": req.broker,
        "encrypted_api_key": encrypt_broker_credentials(req.api_key),
        "encrypted_secret_key": encrypt_broker_credentials(req.secret_key),
        "encrypted_access_token": encrypt_broker_credentials(req.access_token) if req.access_token else "",
        "additional_params": req.additional_params,
    }
    try:
        result = supabase.table("broker_credentials").insert(payload).execute()
        inserted = result.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save credentials: {e}")

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
    try:
        result = supabase.table("broker_credentials").delete().eq("user_id", current_user.id).eq("broker", broker_name).execute()
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


FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI", "https://api.ai.trademetrix.tech/api/v1/brokers/fyers/callback")


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

    row = supabase.table("broker_credentials").select("encrypted_api_key").eq("id", cred["id"]).single().execute()
    client_id = decrypt_broker_credentials(row.data["encrypted_api_key"])
    auth_url = (
        f"https://api.fyers.in/api/v2/generate-authcode"
        f"?client_id={client_id}"
        f"&redirect_uri={FYERS_REDIRECT_URI}"
        f"&response_type=code"
        f"&state={current_user.id}"
    )
    return {"auth_url": auth_url}


class FyersAuthCodeInput(BaseModel):
    auth_code: str


@router.post("/fyers/exchange-code")
async def fyers_exchange_code(
    req: FyersAuthCodeInput,
    current_user: UserProfile = Depends(get_current_user),
):
    import httpx

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

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.fyers.in/api/v2/validate-authcode",
            json={"client_id": client_id, "secret_key": secret_key, "auth_code": req.auth_code},
        )
        data = resp.json()
        if data.get("s") != "ok":
            raise HTTPException(status_code=400, detail=f"Fyers auth failed: {data.get('message', '')}")

        raw_token = data["access_token"]
        encrypted = encrypt_broker_credentials(raw_token)
        supabase.table("broker_credentials").update(
            {"encrypted_access_token": encrypted, "is_active": True, "updated_at": __import__("datetime").datetime.utcnow().isoformat()}
        ).eq("id", cred["id"]).execute()

    return {"message": "Fyers authenticated successfully!"}


@router.get("/fyers/callback")
async def fyers_callback(
    auth_code: str = Query(alias="auth_code"),
    state: str | None = Query(None),
):
    from fastapi.responses import RedirectResponse

    FRONTEND_URL = "https://ai.trademetrix.tech/brokers"

    import httpx

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

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.fyers.in/api/v2/validate-authcode",
            json={"client_id": client_id, "secret_key": secret_key, "auth_code": auth_code},
        )
        data = resp.json()
        if data.get("s") != "ok":
            return RedirectResponse(url=f"{FRONTEND_URL}?auth_error=Fyers+auth+failed")

        raw_token = data["access_token"]
        encrypted = encrypt_broker_credentials(raw_token)
        supabase.table("broker_credentials").update(
            {"encrypted_access_token": encrypted, "is_active": True, "updated_at": __import__("datetime").datetime.utcnow().isoformat()}
        ).eq("id", cred["id"]).execute()

    return RedirectResponse(url=f"{FRONTEND_URL}?auth_success=1")
