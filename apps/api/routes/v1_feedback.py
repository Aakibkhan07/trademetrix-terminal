import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from application.services.analytics_service import AnalyticsService
from core.deps import get_current_user, require_admin
from core.models import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])

_feedback_service = AnalyticsService()

CATEGORIES = ("bug", "feature", "nps", "report")
STATUSES = ("new", "triaged", "resolved", "wontfix")


@router.post("/api/v1/feedback")
async def submit_feedback(
    request: Request,
    user: UserProfile = Depends(get_current_user),
):
    body = await request.json()
    category = body.get("category", "bug")
    title = body.get("title", "")
    description = body.get("description", "")
    metadata = body.get("metadata", {}) or {}
    try:
        result = await _feedback_service.submit_feedback(
            user, category, title, description, metadata
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    logger.info(
        "Feedback submitted: id=%s user=%s category=%s", result.get("id"), user.id, category
    )
    return result


@router.get("/api/v1/feedback")
async def list_my_feedback(
    user: UserProfile = Depends(get_current_user),
):
    return await _feedback_service.list_user_feedback(user.id)


@router.get("/api/v1/admin/feedback")
async def admin_list_feedback(
    category: str = "",
    status: str = "",
    admin: UserProfile = Depends(require_admin),
):
    return await _feedback_service.list_feedback(category=category, status=status)


@router.patch("/api/v1/admin/feedback/{feedback_id}")
async def admin_update_feedback(
    feedback_id: int,
    request: Request,
    admin: UserProfile = Depends(require_admin),
):
    body = await request.json()
    result = await _feedback_service.update_feedback(
        feedback_id,
        status=body.get("status") if body.get("status") in STATUSES else None,
        notes=body.get("notes"),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return result
