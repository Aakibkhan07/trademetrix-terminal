from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.db import async_supabase, get_supabase
from core.models import UserProfile, role_satisfies, role_has_permission
from core.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UserProfile:
    token = None
    if credentials:
        token = credentials.credentials
    else:
        token = request.cookies.get("tm_session") or request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    try:
        supabase = get_supabase()
        result = await async_supabase(lambda: supabase.table("profiles").select("*").eq("id", user_id).maybe_single().execute())
        if not result or not result.data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User profile not found",
            )
        profile_data = {k: v for k, v in dict(result.data).items() if v is not None}
        if not profile_data.get("full_name") and profile_data.get("name"):
            profile_data["full_name"] = profile_data["name"]
        return UserProfile(**profile_data)
    except HTTPException:
        raise
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("Profile lookup failed for user=%s: %s", user_id, e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
        )


async def require_admin(user: UserProfile = Depends(get_current_user)) -> UserProfile:
    if not user.is_admin and not role_satisfies(user.role, "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def require_super_admin(user: UserProfile = Depends(get_current_user)) -> UserProfile:
    if not role_satisfies(user.role, "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    return user


def require_permission(permission: str):
    async def checker(user: UserProfile = Depends(get_current_user)) -> UserProfile:
        if not role_has_permission(user.role, permission) and not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}",
            )
        return user
    return checker
