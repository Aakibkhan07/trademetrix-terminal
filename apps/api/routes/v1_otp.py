import hashlib
import logging
import random
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, field_validator

from core.audit import record_audit
from core.cache import cache
from core.config import settings

logger = logging.getLogger(__name__)
from core.db import async_supabase, get_supabase
from core.http_client import get_http_client
from core.models import AuditLogEntry, UserProfile
from core.notifications import deliver_otp
from core.security import create_access_token

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

OTP_TTL = 300


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
    return str(random.SystemRandom().randint(100000, 999999))


async def _store_otp(email: str, code: str, phone: str = ""):
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    await cache.set(
        f"otp:{email}:login",
        {"code_hash": code_hash, "phone": phone, "verified": False, "created_at": datetime.now(UTC).isoformat()},
        ttl=OTP_TTL,
    )


async def _get_stored_otp(email: str) -> dict | None:
    return await cache.get(f"otp:{email}:login")


async def _delete_otp(email: str):
    await cache.delete(f"otp:{email}:login")


def _check_user_exists(supabase, email: str) -> dict | None:
    result = supabase.table("profiles").select("*").eq("email", email).maybe_single().execute()
    return result.data if result and result.data else None


@router.post("/send-otp")
async def send_otp(req: SendOTPRequest):
    supabase = get_supabase()
    user = _check_user_exists(supabase, req.email)

    code = _generate_otp()
    await _store_otp(req.email, code, req.phone)
    delivered = await deliver_otp(code, req.email, req.phone)

    result = {"message": "OTP sent to your registered contact", "exists": True} if user else \
             {"message": "OTP sent. Complete registration to continue.", "exists": False}
    if not delivered:
        logger.warning("OTP delivery failed for %s", req.email)
    return result


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
    except Exception as e:
        logger.warning("OTP profile creation failed: %s", e)

    code = _generate_otp()
    await _store_otp(req.email, code, req.phone)
    delivered = await deliver_otp(code, req.email, req.phone)

    if not delivered:
        logger.warning("Registration OTP delivery failed for %s", req.email)
    return {"message": "Account created. OTP sent to your registered contact.", "user_id": user_id}


@router.post("/verify-otp")
async def verify_otp(req: VerifyOTPRequest, response: Response):
    stored = await _get_stored_otp(req.email)
    if not stored:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No OTP found. Request a new one.")

    code_hash = hashlib.sha256(req.otp.encode()).hexdigest()
    if stored.get("code_hash") != code_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OTP. Please try again.")

    if stored.get("verified"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OTP already used. Request a new one.")

    stored["verified"] = True
    await _store_otp(req.email, req.otp, stored.get("phone", ""))
    await _delete_otp(req.email)

    supabase = get_supabase()
    is_new = False

    async def _lookup_auth_user(email: str) -> dict | None:
        try:
            client = await get_http_client()
            resp = await client.get(
                f"{settings.supabase_url}/auth/v1/admin/users",
                headers={
                    "apikey": settings.supabase_service_key,
                    "Authorization": f"Bearer {settings.supabase_service_key}",
                },
            )
            if resp.status_code == 200:
                users_data = resp.json()
                auth_users = users_data.get("users", []) if isinstance(users_data, dict) else users_data if isinstance(users_data, list) else []
                for u in auth_users:
                    if isinstance(u, dict) and u.get("email", "").lower() == email.lower():
                        return u
            return None
        except Exception:
            return None

    auth_user = await _lookup_auth_user(req.email)
    uid = auth_user["id"] if auth_user else None

    profile_data = None
    if uid:
        profile_data = (await async_supabase(lambda: supabase.table("profiles").select("*").eq("id", uid).maybe_single().execute())).data

    if not profile_data and uid:
        try:
            client = await get_http_client()
            await client.post(
                f"{settings.supabase_url}/rest/v1/profiles",
                headers={
                    "apikey": settings.supabase_service_key,
                    "Authorization": f"Bearer {settings.supabase_service_key}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates",
                },
                json={"id": uid, "email": req.email},
            )
            profile_data = {"id": uid, "email": req.email}
        except Exception as e:
            logger.warning("OTP profile creation failed: %s", e)

    if profile_data:
        user = UserProfile(**{k: v for k, v in profile_data.items() if v is not None})
    else:
        is_new = True
        user = UserProfile(id=uid or "", email=req.email)

    access_token = create_access_token(subject=user.id)
    _set_session_cookie(response, access_token)

    record_audit(AuditLogEntry(
        user_id=user.id,
        action="otp_verify",
        resource="auth",
        details={"email": req.email, "is_new": is_new},
    ))

    return VerifyOTPResponse(access_token=access_token, user=user, is_new=is_new)
