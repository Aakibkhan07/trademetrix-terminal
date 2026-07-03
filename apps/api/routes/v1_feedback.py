import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from core.deps import get_current_user, require_admin
from core.models import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])

_feedback: list[dict] = []


@router.post("/api/v1/feedback")
async def submit_feedback(request: Request, user: UserProfile = Depends(get_current_user)):
    body = await request.json()
    category = body.get("category", "bug")
    title = body.get("title", "")
    description = body.get("description", "")
    metadata = body.get("metadata", {})

    if not title and not description:
        raise HTTPException(status_code=400, detail="title or description is required")

    if category not in ("bug", "feature", "nps", "report"):
        category = "bug"

    entry = {
        "id": len(_feedback) + 1,
        "user_id": user.id,
        "user_email": user.email,
        "full_name": user.full_name or "",
        "category": category,
        "title": title,
        "description": description,
        "metadata": metadata,
        "status": "new",
        "created_at": datetime.utcnow().isoformat(),
    }
    _feedback.append(entry)

    logger.info("Feedback submitted: id=%d user=%s category=%s title=%s", entry["id"], user.id, category, title)
    return {"ok": True, "id": entry["id"]}


@router.get("/api/v1/admin/feedback")
async def admin_list_feedback(
    category: str = "",
    status: str = "",
    admin: UserProfile = Depends(require_admin),
):
    result = list(_feedback)
    if category:
        result = [f for f in result if f["category"] == category]
    if status:
        result = [f for f in result if f["status"] == status]
    return {"feedback": result, "count": len(result)}


@router.patch("/api/v1/admin/feedback/{feedback_id}")
async def admin_update_feedback(
    feedback_id: int,
    request: Request,
    admin: UserProfile = Depends(require_admin),
):
    body = await request.json()
    for f in _feedback:
        if f["id"] == feedback_id:
            if "status" in body:
                f["status"] = body["status"]
            if "notes" in body:
                f["notes"] = body["notes"]
            return {"ok": True, "feedback": f}
    raise HTTPException(status_code=404, detail="Feedback not found")
