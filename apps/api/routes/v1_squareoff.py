import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from application.services.squareoff_service import SquareoffService
from core.deps import get_current_user
from core.models import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/engine/squareoff", tags=["squareoff"])

service = SquareoffService()


class SquareoffConfigRequest(BaseModel):
    enabled: bool = True
    time: str = "15:15"
    days: list[int] = [0, 1, 2, 3, 4]


@router.get("/config")
async def get_squareoff_config(current_user: UserProfile = Depends(get_current_user)):
    config = await service.get_config(current_user.id)
    return {"config": config}


@router.post("/config")
async def set_squareoff_config(
    req: SquareoffConfigRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    return await service.set_config(
        user_id=current_user.id,
        enabled=req.enabled,
        time=req.time,
        days=req.days,
    )


@router.post("/run")
async def run_squareoff(current_user: UserProfile = Depends(get_current_user)):
    return await service.run_squareoff(current_user.id)
