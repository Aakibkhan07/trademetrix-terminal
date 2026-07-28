import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from application.services.analytics_service import AnalyticsService
from core.deps import get_current_user, require_admin
from core.models import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])

_analytics_service = AnalyticsService()


@router.post("/api/v1/analytics/track")
async def track_event(request: Request):
    body = await request.json()
    try:
        return await _analytics_service.track_event(
            event_name=body.get("event", ""),
            properties=body.get("properties", {}),
            session_id=body.get("session_id", ""),
            user_id=body.get("user_id", ""),
            timestamp=body.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/v1/analytics/events")
async def list_events(
    event: str = "",
    limit: int = 100,
    user: UserProfile = Depends(require_admin),
):
    return await _analytics_service.list_events(event_filter=event or None, limit=limit)


@router.get("/api/v1/admin/analytics/overview")
async def admin_analytics_overview(admin: UserProfile = Depends(require_admin)):
    return await _analytics_service.get_admin_overview()


@router.get("/api/v1/analytics/pnl")
async def get_pnl(
    current_user: UserProfile = Depends(get_current_user),
    period: str = "1d",
    group_by: str | None = None,
    broker: str | None = None,
):
    from portfolio.manager import portfolio_manager
    from risk.helpers import compute_daily_pnl_fifo, get_active_broker
    try:
        resolved = broker or await get_active_broker(current_user.id)
        if period == "1d":
            daily = await compute_daily_pnl_fifo(current_user.id, resolved)
            return {"pnl": {"daily": daily}, "period": period, "broker": resolved}
        if resolved:
            pnl = await portfolio_manager.get_pnl(current_user.id, resolved)
            return {"pnl": pnl.model_dump(), "period": period, "broker": resolved}
        return {"pnl": None, "period": period, "broker": None}
    except Exception as e:
        logger.error("Failed to fetch PnL for user=%s: %s", current_user.id, e)
        raise HTTPException(status_code=502, detail=f"Failed to fetch PnL: {e}")


@router.get("/api/v1/analytics/mtm")
async def get_mtm(current_user: UserProfile = Depends(get_current_user)):
    from risk.helpers import get_current_exposure
    try:
        exposure = await get_current_exposure(current_user.id)
        return {"mtm": exposure}
    except Exception as e:
        logger.error("Failed to fetch MTM for user=%s: %s", current_user.id, e)
        raise HTTPException(status_code=502, detail=f"Failed to fetch MTM: {e}")
