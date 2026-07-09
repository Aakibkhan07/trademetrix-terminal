import logging
import time

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.capabilities import Capabilities, resolve_capabilities
from core.db import async_supabase, get_supabase
from core.models import TIER_ORDER, UserProfile, role_satisfies, role_has_permission
from core.security import decode_access_token

logger = logging.getLogger(__name__)
_bearer = HTTPBearer(auto_error=False)

_user_cache: dict[str, tuple[float, dict]] = {}
USER_CACHE_TTL = 120
_USER_CACHE_MAX = 100


async def get_user_by_id(user_id: str) -> UserProfile | None:
    try:
        supabase = get_supabase()
        result = await async_supabase(
            lambda: supabase.table("profiles").select("*").eq("id", user_id).maybe_single().execute()
        )
        if not result or not result.data:
            return None
        profile_data = {k: v for k, v in dict(result.data).items() if v is not None}
        return UserProfile(**profile_data)
    except Exception as e:
        logger.warning("get_user_by_id failed for %s: %s", user_id, e)
        return None


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

    cached = _user_cache.get(user_id)
    if cached and time.time() - cached[0] < USER_CACHE_TTL:
        return UserProfile(**cached[1])

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
        if len(_user_cache) >= _USER_CACHE_MAX:
            stale = min(_user_cache.keys(), key=lambda k: _user_cache[k][0])
            del _user_cache[stale]
        _user_cache[user_id] = (time.time(), profile_data)
        return UserProfile(**profile_data)
    except HTTPException:
        raise
    except Exception as e:
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


async def get_capabilities(
    user: UserProfile = Depends(get_current_user),
) -> Capabilities:
    return await resolve_capabilities(user)


def require_feature(feature: str):
    """Require a specific capability feature.

    Example: require_feature("builder"), require_feature("trailing_sl")
    """
    async def checker(
        user: UserProfile = Depends(get_current_user),
        caps: Capabilities = Depends(get_capabilities),
    ) -> UserProfile:
        if user.role == "super_admin":
            return user
        allowed = getattr(caps, f"{feature}_allowed", None)
        if allowed is not True:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your plan ({caps.tier}) does not include '{feature}'. Please upgrade to access this feature.",
            )
        return user
    return checker


def require_tier(min_tier: str):
    """Legacy tier gate — delegates to capabilities resolver for subscription check."""
    async def checker(user: UserProfile = Depends(get_current_user)) -> UserProfile:
        if user.role == "super_admin":
            return user
        if TIER_ORDER.get(user.subscription_tier, -1) < TIER_ORDER.get(min_tier, 99):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your plan ({user.subscription_tier}) does not support this feature. Minimum required tier: {min_tier}.",
            )
        return user
    return checker
