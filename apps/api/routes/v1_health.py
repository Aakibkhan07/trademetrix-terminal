
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


def _db_ok() -> bool:
    try:
        from core.db import get_supabase
        sb = get_supabase()
        sb.table("orders").select("id").limit(1).execute()
        return True
    except Exception:
        return False


async def _cache_ok() -> bool:
    try:
        if cache._enabled and cache._redis:
            await cache._redis.ping()
            return True
        return False
    except Exception:
        return False


@router.get("/health/ready")
async def readiness():
    db = _db_ok()
    cache_ok = await _cache_ok()
    status = "ok" if db else "degraded"
    return {
        "status": status,
        "dependencies": {"database": db, "cache": cache_ok},
    }


@router.get("/health/live")
async def liveness():
    return {"status": "alive"}
