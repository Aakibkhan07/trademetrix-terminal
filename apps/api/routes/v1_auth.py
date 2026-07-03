import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from core.audit import record_audit
from core.config import settings
from core.deps import get_current_user
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


class SignUpRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""


class SignInRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    user: UserProfile
    access_token: str


def _set_session_cookie(response: Response, token: str):
    response.set_cookie(key=COOKIE_NAME, value=token, **COOKIE_KWARGS)


def _clear_session_cookie(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/", domain=settings.cookie_domain or None)


@router.post("/signup", status_code=201)
async def signup(req: SignUpRequest, response: Response):

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
            json={"id": user_id, "full_name": req.full_name, "email": req.email},
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

    return AuthResponse(user=user, access_token=access_token)


@router.post("/signin")
async def signin(req: SignInRequest, response: Response):

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
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        token_data = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid credentials: {str(e)}")

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


@router.get("/me")
async def get_me(current_user: UserProfile = Depends(get_current_user)):
    return current_user
