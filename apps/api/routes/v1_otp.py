import hashlib
import random
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Response, status

from core.audit import record_audit
from core.config import settings
from core.db import get_supabase
from core.http_client import get_http_client
from core.models import AuditLogEntry, UserProfile
from core.notifications import deliver_otp
from core.security import create_access_token
from pydantic import BaseModel, field_validator

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "tm_session"
COOKIE_MAX_AGE = 7 * 24 * 3600
COOKIE_KWARGS = dict(
    httponly=True,
    secure=True,
    samesite="none",
    path="/",
    domain=settings.cookie_domain or None,
    max_age=COOKIE_MAX_AGE,
)


class SendOTPRequest(BaseModel):
    email: str
    phone: str = ""


class RegisterWithOTPRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""
    phone: str = ""

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


class VerifyOTPRequest(BaseModel):
    email: str
    otp: str


class VerifyOTPResponse(BaseModel):
    access_token: str
    user: UserProfile
    is_new: bool = False


def _set_session_cookie(response: Response, token: str):
    response.set_cookie(key=COOKIE_NAME, value=token, **COOKIE_KWARGS)


def _generate_otp() -> str:
    return str(random.randint(100000, 999999))


def _store_otp(supabase, email: str, code: str, phone: str = ""):
    expires_at = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    supabase.table("otp_codes").insert({
        "email": email,
        "phone": phone,
        "code_hash": code_hash,
        "purpose": "login",
        "expires_at": expires_at,
    }).execute()
    supabase.table("otp_codes").delete().eq("email", email).eq("purpose", "login").lt("expires_at", datetime.now(UTC).isoformat()).execute()


def _check_user_exists(supabase, email: str) -> dict | None:
    result = supabase.table("profiles").select("*").eq("email", email).maybe_single().execute()
    return result.data if result and result.data else None


@router.post("/send-otp")
async def send_otp(req: SendOTPRequest):
    supabase = get_supabase()
    user = _check_user_exists(supabase, req.email)

    code = _generate_otp()
    _store_otp(supabase, req.email, code, req.phone)
    await deliver_otp(code, req.email, req.phone)

    if user:
        return {"message": "OTP sent to your registered contact", "exists": True}
    return {"message": "OTP sent. Complete registration to continue.", "exists": False}


@router.post("/register-with-otp", status_code=201)
async def register_with_otp(req: RegisterWithOTPRequest):
    supabase = get_supabase()

    try:
        client = await get_http_client()
        resp = await client.post(
            f"{settings.supabase_url}/auth/v1/admin/users",
            headers={
                "apikey": settings.supabase_service_key,
                "Authorization": f"Bearer {settings.supabase_service_key}",
                "Content-Type": "application/json",
            },
            json={"email": req.email, "password": req.password, "email_confirm": False},
        )
        if resp.status_code == 409:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        if resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create user: {resp.text}")
        user_data = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create user: {str(e)}")

    user_id = user_data["id"]

    profile_payload = {"id": user_id, "email": req.email, "full_name": req.full_name}
    if req.phone:
        profile_payload["phone"] = req.phone
    try:
        await client.post(
            f"{settings.supabase_url}/rest/v1/profiles",
            headers={
                "apikey": settings.supabase_service_key,
                "Authorization": f"Bearer {settings.supabase_service_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates",
            },
            json=profile_payload,
        )
    except Exception:
        pass

    code = _generate_otp()
    _store_otp(supabase, req.email, code, req.phone)
    await deliver_otp(code, req.email, req.phone)

    return {"message": "Account created. OTP sent to your registered contact.", "user_id": user_id}


@router.post("/verify-otp")
async def verify_otp(req: VerifyOTPRequest, response: Response):
    supabase = get_supabase()

    records = supabase.table("otp_codes").select("*").eq("email", req.email).eq("purpose", "login").eq("verified_at", None).order("created_at", desc=True).limit(5).execute()
    if not records or not records.data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No OTP found. Request a new one.")

    code_hash = hashlib.sha256(req.otp.encode()).hexdigest()
    valid = None
    for record in records.data:
        expires_at = record.get("expires_at", "")
        if record.get("code_hash") == code_hash:
            if expires_at and datetime.fromisoformat(expires_at.replace("Z", "+00:00")) < datetime.now(UTC):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OTP expired. Request a new one.")
            valid = record
            break

    if not valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OTP. Please try again.")

    supabase.table("otp_codes").update({"verified_at": datetime.now(UTC).isoformat()}).eq("id", valid["id"]).execute()

    user = _check_user_exists(supabase, req.email)
    is_new = False
    if not user:
        is_new = True
        user = UserProfile(id="", email=req.email)

    access_token = create_access_token(subject=user.id)
    _set_session_cookie(response, access_token)

    record_audit(AuditLogEntry(
        user_id=user.id,
        action="otp_verify",
        resource="auth",
        details={"email": req.email, "is_new": is_new},
    ))

    return VerifyOTPResponse(access_token=access_token, user=user, is_new=is_new)
