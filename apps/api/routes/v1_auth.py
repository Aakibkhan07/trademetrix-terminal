import asyncio
import logging
from datetime import UTC, datetime
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from core.audit import record_audit
from core.cache import cache
from core.notifications import send_welcome_email
from core.config import settings
from core.db import async_supabase, get_supabase
from core.deps import _user_cache, get_capabilities, get_current_user
from core.http_client import get_http_client
from core.models import AuditLogEntry, UserProfile
from core.security import create_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "tm_session"
COOKIE_MAX_AGE = 7 * 24 * 3600  # 7 days
COOKIE_KWARGS = dict(
    httponly=True,
    secure=True,
    samesite="none",
    path="/",
    domain=settings.cookie_domain or None,
    max_age=COOKIE_MAX_AGE,
)

# ── Login throttling (P2) ──
LOGIN_FAIL_KEY = "loginfail:{email}:{ip}"
LOGIN_FAIL_MAX = 5
LOGIN_FAIL_WINDOW = 300  # seconds
LOGIN_DELAY_STEP = 0.5  # seconds, progressive
LOGIN_DELAY_MAX = 5.0  # seconds cap


def _client_ip(request: Request) -> str:
    """Best-effort client IP: trust the first X-Forwarded-For hop like the IP whitelist does."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        first = fwd.split(",")[0].strip()
        if first and first.lower() != "unknown":
            return first
    return request.client.host if request.client else "unknown"


async def _login_fail_key(email: str, ip: str) -> str:
    return LOGIN_FAIL_KEY.format(email=email.lower(), ip=ip)


async def _record_login_failure(email: str, ip: str) -> int:
    key = await _login_fail_key(email, ip)
    count = int(await cache.get(key, 0) or 0) + 1
    await cache.set(key, count, ttl=LOGIN_FAIL_WINDOW)
    return count


async def _clear_login_failures(email: str, ip: str) -> None:
    key = await _login_fail_key(email, ip)
    await cache.set(key, 0, ttl=LOGIN_FAIL_WINDOW)


async def _throttle_login(request: Request, email: str, failed: bool) -> None:
    """Progressive delay + temporary lockout on repeated signin failures.

    Degrades only the failure path — a successful credential check is never
    delayed or blocked.
    """
    ip = _client_ip(request)
    if not failed:
        await _clear_login_failures(email, ip)
        return
    count = await _record_login_failure(email, ip)
    if count > LOGIN_FAIL_MAX:
        record_audit(AuditLogEntry(
            user_id="", action="login_locked", resource="auth",
            details={"email": email, "ip": ip, "attempts": count},
        ))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again in a few minutes.",
        )
    if count > 1:
        record_audit(AuditLogEntry(
            user_id="", action="auth_failed", resource="auth",
            details={"email": email, "ip": ip, "attempts": count},
        ))
        await asyncio.sleep(min(LOGIN_DELAY_STEP * (count - 1), LOGIN_DELAY_MAX))


class SignUpRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""


class SignInRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class UpdateProfileRequest(BaseModel):
    onboarding_completed: bool


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AuthResponse(BaseModel):
    user: UserProfile
    access_token: str


def _set_session_cookie(response: Response, token: str):
    response.set_cookie(key=COOKIE_NAME, value=token, **COOKIE_KWARGS)


def _clear_session_cookie(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/", domain=settings.cookie_domain or None)


def _validate_password(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters long"
    if not any(c.isupper() for c in password):
        return "Password must contain at least one uppercase letter"
    if not any(c.islower() for c in password):
        return "Password must contain at least one lowercase letter"
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one digit"
    if not any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?`~" for c in password):
        return "Password must contain at least one special character"
    return None


@router.post("/signup", status_code=201)
async def signup(req: SignUpRequest, response: Response, background_tasks: BackgroundTasks):

    pw_error = _validate_password(req.password)
    if pw_error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=pw_error)

    try:
        client = await get_http_client()
        resp = await client.post(
            f"{settings.supabase_url}/auth/v1/admin/users",
            headers={
                "apikey": settings.supabase_service_key,
                "Authorization": f"Bearer {settings.supabase_service_key}",
                "Content-Type": "application/json",
            },
            json={"email": req.email, "password": req.password, "email_confirm": True},
        )
        if resp.status_code != 200:
            body = resp.json()
            error_code = body.get("error_code", "")
            if resp.status_code == 409 or error_code == "email_exists":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
            if resp.status_code == 422:
                msg = body.get("msg", "Validation error")
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user")
        user_data = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create user: {str(e)}")

    user_id = user_data["id"]

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
            json={"id": user_id, "full_name": req.full_name, "email": req.email, "created_at": datetime.now(UTC).isoformat()},
        )
    except Exception as e:
        logger.warning("Failed to create auth profile for user %s: %s", user_id, e)

    access_token = create_access_token(subject=user_id)
    _set_session_cookie(response, access_token)

    user = UserProfile(
        id=user_id,
        email=req.email,
        full_name=req.full_name,
    )

    record_audit(AuditLogEntry(
        user_id=user_id,
        action="signup",
        resource="auth",
        ip_address="",
    ))

    background_tasks.add_task(send_welcome_email, req.email, req.full_name or req.email)

    return AuthResponse(user=user, access_token=access_token)


@router.post("/signin")
async def signin(req: SignInRequest, response: Response, request: Request):

    try:
        client = await get_http_client()
        resp = await client.post(
            f"{settings.supabase_url}/auth/v1/token?grant_type=password",
            headers={
                "apikey": settings.supabase_anon_key,
                "Content-Type": "application/json",
            },
            json={"email": req.email, "password": req.password},
        )
        if resp.status_code != 200:
            await _throttle_login(request, req.email, failed=True)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        token_data = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        await _throttle_login(request, req.email, failed=True)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid credentials: {str(e)}")

    await _throttle_login(request, req.email, failed=False)

    user_id = token_data["user"]["id"]
    access_token = create_access_token(subject=user_id)

    _set_session_cookie(response, access_token)

    try:
        client = await get_http_client()
        resp = await client.get(
            f"{settings.supabase_url}/rest/v1/profiles?id=eq.{user_id}&select=*",
            headers={
                "apikey": settings.supabase_service_key,
                "Authorization": f"Bearer {settings.supabase_service_key}",
            },
        )
        if resp.status_code == 200 and resp.json():
            user = UserProfile(**resp.json()[0])
        else:
            user = UserProfile(id=user_id, email=req.email)
    except Exception:
        user = UserProfile(id=user_id, email=req.email)

    record_audit(AuditLogEntry(
        user_id=user_id,
        action="signin",
        resource="auth",
        ip_address="",
    ))

    return AuthResponse(user=user, access_token=access_token)


@router.post("/signout")
async def signout(response: Response, current_user: UserProfile = Depends(get_current_user)):
    _clear_session_cookie(response)

    record_audit(AuditLogEntry(
        user_id=current_user.id,
        action="signout",
        resource="auth",
        ip_address="",
    ))

    return {"message": "Signed out"}


@router.post("/change-password")
async def change_password(req: ChangePasswordRequest, current_user: UserProfile = Depends(get_current_user)):
    try:
        client = await get_http_client()
        signin_resp = await client.post(
            f"{settings.supabase_url}/auth/v1/token?grant_type=password",
            headers={
                "apikey": settings.supabase_anon_key,
                "Content-Type": "application/json",
            },
            json={"email": current_user.email, "password": req.current_password},
        )
        if signin_resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

        admin_resp = await client.put(
            f"{settings.supabase_url}/auth/v1/admin/users/{current_user.id}",
            headers={
                "apikey": settings.supabase_service_key,
                "Authorization": f"Bearer {settings.supabase_service_key}",
                "Content-Type": "application/json",
            },
            json={"password": req.new_password, "email_confirm": True},
        )
        if admin_resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update password")

        record_audit(AuditLogEntry(
            user_id=current_user.id,
            action="change_password",
            resource="auth",
            ip_address="",
        ))

        return {"message": "Password changed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to change password: {str(e)}")


@router.get("/csrf")
async def get_csrf_token(request: Request):
    """Return CSRF token for clients that don't have one yet (CSRF bootstrap).
    Middleware sets the cookie + X-CSRF-Token header on every response."""
    token = secrets.token_hex(32)
    request.state.csrf_token = token
    return {"csrf_token": token}


@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest):
    try:
        client = await get_http_client()
        resp = await client.post(
            f"{settings.supabase_url}/auth/v1/recover",
            headers={
                "apikey": settings.supabase_anon_key,
                "Content-Type": "application/json",
            },
            json={"email": req.email},
        )
        if resp.status_code != 200:
            logger.warning("Supabase recover failed: %s", resp.text)
    except Exception as e:
        logger.warning("Failed to send password reset: %s", e)

    record_audit(AuditLogEntry(
        user_id="",
        action="forgot_password",
        resource="auth",
        details={"email": req.email},
    ))
    return {"message": "If that email is registered, a password reset link has been sent"}


@router.get("/me")
async def get_me(current_user: UserProfile = Depends(get_current_user)):
    return current_user


@router.get("/me/capabilities")
async def me_capabilities(caps=Depends(get_capabilities)):
    return caps


@router.patch("/profile")
async def update_profile(req: UpdateProfileRequest, current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    data = req.model_dump()
    await async_supabase(lambda: supabase.table("profiles").update(data).eq("id", current_user.id).execute())
    _user_cache.pop(current_user.id, None)
    current_user.onboarding_completed = req.onboarding_completed
    return current_user


