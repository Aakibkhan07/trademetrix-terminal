from fastapi import APIRouter

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
    return {"status": "ready"}


@router.get("/health/live")
async def liveness():
    return {"status": "alive"}
