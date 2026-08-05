import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from application.services.analytics_service import AnalyticsService
from core.deps import get_current_user, get_optional_user, require_admin
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
            user_id="",
            timestamp=body.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/v1/analytics/track-batch")
async def track_batch(
    request: Request,
    user: UserProfile | None = Depends(get_optional_user),
):
    """Client tracker batch ingest (session events: page views, clicks,
    scroll depth, client errors). Anonymous sessions allowed; user_id is
    resolved server-side when the caller is authenticated (cookie or bearer)."""
    body = await request.json()
    events = body.get("events", [])
    user_id = user.id if user else ""
    for e in events:
        if user_id:
            e["user_id"] = user_id
        props = e.get("properties")
        if isinstance(props, dict):
            props["is_auth"] = bool(user_id)
    return await _analytics_service.track_batch(events)


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


# ─── Beta Operations Mode: funnel / retention / usage / journey / crashes ───


@router.get("/api/v1/admin/analytics/funnel")
async def admin_funnel(
    steps: str = "signup,broker.connected,strategy.created,backtest.run,order.placed",
    days: int = 30,
    admin: UserProfile = Depends(require_admin),
):
    step_list = [s.strip() for s in steps.split(",") if s.strip()]
    return await _analytics_service.get_funnel(step_list, days=min(days, 90))


@router.get("/api/v1/admin/analytics/retention")
async def admin_retention(
    weeks: int = 8,
    admin: UserProfile = Depends(require_admin),
):
    return await _analytics_service.get_retention(weeks=min(weeks, 26))


@router.get("/api/v1/admin/analytics/features")
async def admin_features(
    days: int = 30,
    admin: UserProfile = Depends(require_admin),
):
    return await _analytics_service.get_feature_usage(days=min(days, 90))


@router.get("/api/v1/admin/analytics/sessions")
async def admin_sessions(
    limit: int = 25,
    days: int = 7,
    admin: UserProfile = Depends(require_admin),
):
    return await _analytics_service.get_sessions(limit=min(limit, 100), days=min(days, 30))


@router.get("/api/v1/admin/analytics/sessions/{session_id}/events")
async def admin_session_events(
    session_id: str,
    admin: UserProfile = Depends(require_admin),
):
    return await _analytics_service.get_session_events(session_id)


@router.get("/api/v1/admin/analytics/crashes")
async def admin_crashes(
    days: int = 30,
    admin: UserProfile = Depends(require_admin),
):
    return await _analytics_service.get_crashes(days=min(days, 90))
