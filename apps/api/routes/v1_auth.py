from fastapi import APIRouter, HTTPException, status, Response, Depends
from pydantic import BaseModel, EmailStr
from core.db import get_supabase
from core.security import hash_password, verify_password, create_access_token
from core.deps import get_current_user
from core.audit import record_audit
from core.models import UserProfile, AuditLogEntry
from core.config import settings
from core.http_client import get_http_client

router = APIRouter(prefix="/auth", tags=["auth"])


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


@router.post("/signup", status_code=201)
async def signup(req: SignUpRequest, response: Response):
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
    except Exception:
        pass

    access_token = create_access_token(subject=user_id)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400,
    )

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
    supabase = get_supabase()

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

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400,
    )

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
    response.delete_cookie(key="access_token", httponly=True, secure=True, samesite="lax")

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
