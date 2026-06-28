
from fastapi import APIRouter

from core.cache import cache
from core.config import settings
from core.metrics import get_metrics, get_uptime

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "uptime_seconds": round(get_uptime(), 2),
    }


@router.get("/metrics")
async def metrics():
    return get_metrics()


@router.get("/health/ready")
async def readiness():
    deps = {"database": False, "cache": False}
    messages = []

    try:
        from core.db import get_supabase
        sb = get_supabase()
        sb.table("users").select("id").limit(1).execute()
        deps["database"] = True
    except Exception as e:
        messages.append(f"database: {e}")

    try:
        if cache._client:
            await cache._client.ping()
            deps["cache"] = True
    except Exception as e:
        messages.append(f"cache: {e}")

    ready = all(deps.values())
    return {
        "status": "ready" if ready else "degraded",
        "dependencies": deps,
        "messages": messages,
    }


@router.get("/health/live")
async def liveness():
    return {"status": "alive"}
