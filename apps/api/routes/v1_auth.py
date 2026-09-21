import asyncio
import logging
from datetime import UTC, datetime
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr

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
    email: EmailStr
    password: str
    full_name: str = ""


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class UpdateProfileRequest(BaseModel):
    onboarding_completed: bool


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AuthResponse(BaseModel):
    user: UserProfile
    access_token: str


class OAuthExchangeRequest(BaseModel):
    """Supabase GoTrue session tokens from an OAuth redirect (fragment params)."""

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
    except Exception:
        logger.exception("signup GoTrue create failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user")

    user_id = user_data.get("id")
    if not user_id:
        logger.error("signup GoTrue response missing id: %s", user_data)
        raise HTTPException(status_code=502, detail="User provider returned invalid response")

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


@router.post("/google")
async def google_auth(req: OAuthExchangeRequest, response: Response):
    """Exchange a Supabase GoTrue session created via Google OAuth for an API session.

    Flow: user clicks "Continue with Google" → Supabase GoTrue
    `/auth/v1/authorize?provider=google` → Google consent → GoTrue redirects back to
    /auth/callback with tokens in the URL fragment → this endpoint verifies the
    GoTrue access_token against GoTrue, requires a `google` identity, finds-or-creates
    the profile, and mints the app's own session (cookie + JWT) like /signin.
    """
    try:
        client = await get_http_client()
        resp = await client.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={
                "apikey": settings.supabase_anon_key,
                "Authorization": f"Bearer {req.access_token}",
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired OAuth session")
        user_data = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to verify OAuth session: {e}")

    identities = user_data.get("identities") or []
    providers = {i.get("provider") for i in identities}
    if "google" not in providers:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not linked to a Google identity")

    user_id = user_data["id"]
    email = user_data.get("email") or ""
    meta = user_data.get("user_metadata") or {}
    full_name = (meta.get("full_name") or meta.get("name") or "").strip()

    # find-or-create profile (Google users skip the normal signup route)
    profile_row = None
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
            profile_row = resp.json()[0]
        elif resp.status_code == 200:
            await client.post(
                f"{settings.supabase_url}/rest/v1/profiles",
                headers={
                    "apikey": settings.supabase_service_key,
                    "Authorization": f"Bearer {settings.supabase_service_key}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates",
                },
                json={"id": user_id, "full_name": full_name, "email": email, "created_at": datetime.now(UTC).isoformat()},
            )
    except Exception as e:
        logger.warning("OAuth profile lookup/create failed for %s: %s", user_id, e)

    if profile_row:
        user = UserProfile(**profile_row)
    else:
        user = UserProfile(id=user_id, email=email, full_name=full_name)

    api_token = create_access_token(subject=user_id)
    _set_session_cookie(response, api_token)

    record_audit(AuditLogEntry(
        user_id=user_id,
        action="signin",
        resource="auth",
        resource_id="google",
        ip_address="",
    ))

    return AuthResponse(user=user, access_token=api_token)


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
    token = getattr(request.state, 'csrf_token', None) or secrets.token_hex(32)
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


# ── OTP Authentication (v1.9.0) ─────────────────────────────────────────────
# Flow A — existing users: send OTP → verify → get access_token
# Flow B — new users: send OTP (user created at send time with password) →
#           verify → get access_token + is_new=true → redirect to onboarding
#
# OTP is a 6-digit code stored in Redis with 5-minute TTL.
# send-otp is rate-limited to 3 requests per email per 10 minutes.
# verify-otp is rate-limited to 5 attempts per OTP per 10 minutes.
# Both endpoints require CSRF (same middleware as signup/signin).

import secrets as _secrets
import hashlib as _hashlib

_OTP_CODE_BYTES = 3  # 10**6 = 1,000,000 codes — 6 digits
_OTP_TTL_SECONDS = 300  # 5 minutes
_OTP_SEND_PREFIX = "otp:sent:"
_OTP_VERIFY_PREFIX = "otp:verify:"
_OTP_MAX_SEND_PER_EMAIL = 3
_OTP_SEND_WINDOW = 600  # 10 minutes
_OTP_MAX_VERIFY_ATTEMPTS = 5
_OTP_VERIFY_LOCKOUT = 300  # 5 minutes after max failed attempts


def _otp_redis_key_sent(email: str) -> str:
    return f"{_OTP_SEND_PREFIX}{email.lower()}"


def _otp_redis_key_code(email: str) -> str:
    return f"{_OTP_VERIFY_PREFIX}code:{email.lower()}"


def _otp_redis_key_attempts(email: str) -> str:
    return f"{_OTP_VERIFY_PREFIX}attempts:{email.lower()}"


def _otp_redis_key_lockout(email: str) -> str:
    return f"{_OTP_VERIFY_PREFIX}lockout:{email.lower()}"


def _generate_otp() -> str:
    return f"{_secrets.randbelow(1_000_000):06d}"


async def _send_otp_email(to_email: str, otp_code: str, *, is_new_user: bool = False) -> bool:
    """Send OTP via email using the same email gateway as welcome/reset emails."""
    from core.notifications import send_email_resend
    from html import escape as _escape

    safe = _escape(to_email.split("@")[0])
    subject = "Your TradeMetrix Login Code"
    text_body = (
        f"Hi {safe},\n\n"
        f"Your one-time login code for TradeMetrix is: {otp_code}\n\n"
        f"This code expires in 5 minutes. Do not share it with anyone.\n\n"
        f"If you did not request this code, you can safely ignore this email.\n\n"
        f"Best,\nThe TradeMetrix Team"
    )
    html_body = (
        f"<h2>Your TradeMetrix Login Code</h2>"
        f"<p>Hi {safe},</p>"
        f"<p>Your one-time login code is:</p>"
        f"<p style=\"font-size:28px;font-weight:700;letter-spacing:4px;color:#8b5cf6;\">{otp_code}</p>"
        f"<p>This code expires in 5 minutes. Do not share it with anyone.</p>"
        f"<p>If you did not request this code, you can safely ignore this email.</p>"
        f"<br><p>Best,<br>The TradeMetrix Team</p>"
    )
    try:
        ok = await send_email_resend(to_email, subject, text_body, html_body)
        if not ok:
            logger.warning("OTP email failed to deliver to %s", to_email)
        return ok
    except Exception as e:
        logger.warning("OTP email error for %s: %s", to_email, e)
        return False


async def _rate_limit_otp_send(email: str) -> tuple[bool, str | None]:
    """Check send rate limit. Returns (allowed, error_message)."""
    count = await cache.get(_otp_redis_key_sent(email))
    if count is not None and int(count) >= _OTP_MAX_SEND_PER_EMAIL:
        ttl = await cache.ttl(_otp_redis_key_sent(email))
        wait = max(ttl, 0) if ttl > 0 else _OTP_SEND_WINDOW
        return False, f"Too many OTP requests. Try again in {wait} seconds."
    return True, None


async def _record_otp_send(email: str) -> None:
    await cache.increment(_otp_redis_key_sent(email), ttl=_OTP_SEND_WINDOW)


async def _check_otp_verify_lockout(email: str) -> tuple[bool, str | None]:
    """Check if email is locked out from verifying. Returns (allowed, error_message)."""
    remaining = await cache.get(_otp_redis_key_lockout(email))
    if remaining is not None and int(remaining) > 0:
        return False, f"Too many failed attempts. Try again in {remaining} seconds."
    return True, None


async def _record_otp_verify_attempt(email: str, valid: bool) -> None:
    """Record a verify attempt. Locks out on max failures."""
    if valid:
        await cache.delete(_otp_redis_key_attempts(email))
        await cache.delete(_otp_redis_key_lockout(email))
        return
    count = await cache.increment(_otp_redis_key_attempts(email), ttl=_OTP_VERIFY_LOCKOUT)
    if count >= _OTP_MAX_VERIFY_ATTEMPTS:
        await cache.set(_otp_redis_key_lockout(email), _OTP_VERIFY_LOCKOUT, ttl=_OTP_VERIFY_LOCKOUT)


async def _store_otp_code(email: str, code: str) -> None:
    await cache.set(_otp_redis_key_code(email), code, ttl=_OTP_TTL_SECONDS)


async def _get_stored_otp(email: str) -> str | None:
    return await cache.get(_otp_redis_key_code(email))


async def _clear_otp(email: str) -> None:
    await cache.delete(_otp_redis_key_code(email))


class SendOTPRequest(BaseModel):
    email: EmailStr


@router.post("/send-otp")
async def send_otp(req: SendOTPRequest):
    """Send a 6-digit OTP to the given email.

    For existing users: used for OTP-based login.
    For new users: call register-with-otp instead (creates account + sends OTP).
    Rate limited: 3 sends per email per 10 minutes.
    """
    allowed, err = await _rate_limit_otp_send(req.email)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=err)

    # Check if user exists in Supabase (info only — we send OTP either way)
    user_exists = False
    try:
        supabase = get_supabase()
        rows = await async_supabase(
            lambda: supabase.table("profiles").select("id").eq("email", req.email).execute()
        )
        if hasattr(rows, "data"):
            user_exists = len(rows.data) > 0
    except Exception:
        pass

    # Generate and store OTP
    otp_code = _generate_otp()
    await _store_otp_code(req.email, otp_code)
    await _record_otp_send(req.email)

    # Send email
    delivered = await _send_otp_email(req.email, otp_code, is_new_user=False)

    return {
        "message": "OTP sent successfully" if delivered else "OTP generated (email delivery pending)",
        "dev_otp": otp_code if not delivered else None,
        "exists": user_exists,
        "expires_in": _OTP_TTL_SECONDS,
        "delivered": delivered,
    }


class RegisterWithOTPRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""
    phone: str = ""


def _validate_otp_signup_password(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters long"
    if not any(c.isupper() for c in password):
        return "Password must contain at least one uppercase letter"
    if not any(c.islower() for c in password):
        return "Password must contain at least one lowercase letter"
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one digit"
    return None


@router.post("/register-with-otp")
async def register_with_otp(req: RegisterWithOTPRequest):
    """Create a new user account and send an OTP for verification.

    The user sets their password now; they prove ownership of the email
    by entering the OTP sentinel to the verify-otp endpoint.
    Rate limited: 3 sends per email per 10 minutes (shared with send-otp).
    """
    pw_error = _validate_otp_signup_password(req.password)
    if pw_error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=pw_error)

    allowed, err = await _rate_limit_otp_send(req.email)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=err)

    # Create user in Supabase GoTrue
    try:
        client = await get_http_client()
        resp = await client.post(
            f"{settings.supabase_url}/auth/v1/admin/users",
            headers={
                "apikey": settings.supabase_service_key,
                "Authorization": f"Bearer {settings.supabase_service_key}",
                "Content-Type": "application/json",
            },
            json={
                "email": req.email,
                "password": req.password,
                "email_confirm": True,
                "user_metadata": {"full_name": req.full_name or req.email, "phone": req.phone or ""},
            },
        )
        if resp.status_code == 409 or resp.json().get("error_code") == "email_exists":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        if resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user")
        user_data = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("register-with-otp GoTrue create failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user")

    user_id = user_data.get("id")
    if not user_id:
        raise HTTPException(status_code=502, detail="User provider returned invalid response")

    # Create profile row
    try:
        supabase = get_supabase()
        await async_supabase(
            lambda: supabase.table("profiles").upsert(
                {
                    "id": user_id,
                    "full_name": req.full_name or req.email,
                    "email": req.email,
                    "phone": req.phone or "",
                    "created_at": datetime.now(UTC).isoformat(),
                },
                on_conflict="id",
            ).execute()
        )
    except Exception as e:
        logger.warning("Failed to create profile for OTP user %s: %s", user_id, e)

    # Generate and store OTP
    otp_code = _generate_otp()
    await _store_otp_code(req.email, otp_code)
    await _record_otp_send(req.email)

    # Send OTP email
    delivered = await _send_otp_email(req.email, otp_code, is_new_user=True)

    # Store is_new flag in Redis so verify-otp can detect it
    try:
        await cache.set(f"otp:is_new:{req.email}", "1", _OTP_TTL_SECONDS)
    except Exception:
        pass

    record_audit(AuditLogEntry(
        user_id=user_id,
        action="signup_otp_sent",
        resource="auth",
        details={"email": req.email, "email_delivered": delivered},
    ))

    # Mark as new user in Redis so verify-otp can detect it reliably
    # (database queries for is_new are unreliable due to PostgrestResponse quirks)
    try:
        await cache.set(f"otp:is_new:{req.email}", "1", _OTP_TTL_SECONDS)
    except Exception:
        pass

    return {
        "message": "Account created. Check your email for the login code." if delivered else "Account created (email pending)",
        "dev_otp": otp_code if not delivered else None,
        "user_id": user_id,
        "expires_in": _OTP_TTL_SECONDS,
        "delivered": delivered,
    }

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str


@router.post("/verify-otp")
async def verify_otp(req: VerifyOTPRequest, request: Request):
    """Verify a 6-digit OTP and return an access token.

    For existing users: returns { access_token, user, is_new: false }.
    For new users (registered via register-with-otp): returns
    { access_token, user, is_new: true } — frontend should redirect to onboarding.
    Rate limited: 5 verify attempts per OTP, then 5-minute lockout.
    """
    allowed, err = await _check_otp_verify_lockout(req.email)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=err)

    if not req.otp or len(req.otp) != 6 or not req.otp.isdigit():
        await _record_otp_verify_attempt(req.email, valid=False)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP format")

    stored = await _get_stored_otp(req.email)
    if stored is None:
        await _record_otp_verify_attempt(req.email, valid=False)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Code expired or not found. Request a new one.")

    if stored != req.otp:
        await _record_otp_verify_attempt(req.email, valid=False)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect code")

    # OTP is valid — clear it so it can't be reused
    await _clear_otp(req.email)

    # Read is_new flag from Redis (set during register-with-otp).
    # This is more reliable than querying the profiles table.
    is_new = False
    try:
        is_new_val = await cache.get(f"otp:is_new:{req.email}")
        if is_new_val == "1":
            is_new = True
            await cache.delete(f"otp:is_new:{req.email}")
    except Exception:
        pass

    # Fallback: if Redis flag missing, check profiles table
    if not is_new:
        try:
            supabase = get_supabase()
            rows = await async_supabase(
                lambda: supabase.table("profiles").select("onboarding_completed").eq("email", req.email).execute()
            )
            if hasattr(rows, "data") and rows.data:
                row = rows.data[0]
                if isinstance(row, dict) and not row.get("onboarding_completed"):
                    is_new = True
        except Exception:
            pass

    # Look up user ID
    user_id = ""
    full_name = ""
    subscription_tier = "free"
    try:
        supabase = get_supabase()
        resp = await async_supabase(
            lambda: supabase.table("profiles").select("id, full_name, subscription_tier").eq("email", req.email).execute()
        )
        rows = resp.data if hasattr(resp, "data") else []
        if rows:
            user_id = rows[0].get("id", "")
            full_name = rows[0].get("full_name", "") or ""
            subscription_tier = rows[0].get("subscription_tier") or "free"
    except Exception:
        pass

    if not user_id:
        # Fallback: get from GoTrue
        try:
            client = await get_http_client()
            resp = await client.get(
                f"{settings.supabase_url}/auth/v1/user",
                headers={
                    "apikey": settings.supabase_anon_key,
                    "Authorization": f"Bearer {settings.supabase_service_key}",
                },
            )
            if resp.status_code == 200:
                user_data = resp.json()
                user_id = user_data.get("id", "")
                meta = user_data.get("user_metadata") or {}
                full_name = (meta.get("full_name") or "").strip()
        except Exception:
            pass

    access_token = create_access_token(subject=user_id)

    record_audit(AuditLogEntry(
        user_id=user_id or req.email,
        action="otp_verify" + ("_new" if is_new else "_existing"),
        resource="auth",
        details={"email": req.email, "is_new": is_new},
    ))

    user = UserProfile(
        id=user_id or "",
        email=req.email,
        full_name=full_name,
        subscription_tier=subscription_tier,
    )

    return {
        "access_token": access_token,
        "user": user,
        "is_new": is_new,
    }



