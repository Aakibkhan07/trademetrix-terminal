import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from application.services.analytics_service import AnalyticsService
from core.deps import require_admin
from core.models import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])

_analytics_service = AnalyticsService()


@router.post("/api/v1/analytics/track")
async def track_event(request: Request):
    body = await request.json()
    try:
        return _analytics_service.track_event(
            event_name=body.get("event", ""),
            properties=body.get("properties", {}),
            session_id=body.get("session_id", ""),
            user_id=body.get("user_id", ""),
            timestamp=body.get("timestamp", datetime.utcnow().isoformat()),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/v1/analytics/events")
async def list_events(
    event: str = "",
    limit: int = 100,
    user: UserProfile = Depends(require_admin),
):
    return _analytics_service.list_events(event_filter=event or None, limit=limit)


@router.get("/api/v1/admin/analytics/overview")
async def admin_analytics_overview(admin: UserProfile = Depends(require_admin)):
    return await _analytics_service.get_admin_overview()
