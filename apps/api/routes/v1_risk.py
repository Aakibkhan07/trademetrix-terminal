from fastapi import APIRouter, Depends
from pydantic import BaseModel

from application.services.risk_service import RiskService
from core.capabilities import Capabilities
from core.deps import get_capabilities, get_current_user
from core.models import UserProfile

router = APIRouter(prefix="/risk", tags=["risk"])

risk_service = RiskService()


class UpdateRiskRequest(BaseModel):
    strategy_id: str | None = None
    max_capital: float = 0.0
    max_position_size: float = 0.0
    max_open_positions: int = 10
    max_daily_loss: float = 0.0
    max_drawdown_pct: float = 0.0


class LiveEnableRequest(BaseModel):
    confirm: bool = False


@router.get("/settings")
async def get_risk_settings(current_user: UserProfile = Depends(get_current_user)):
    return await risk_service.get_settings(current_user.id)


@router.post("/settings")
async def update_risk_settings(
    req: UpdateRiskRequest,
    current_user: UserProfile = Depends(get_current_user),
    caps: Capabilities = Depends(get_capabilities),
):
    return await risk_service.update_settings(current_user.id, req, caps)


@router.post("/kill-switch/enable")
async def enable_kill_switch(current_user: UserProfile = Depends(get_current_user)):
    return await risk_service.enable_kill_switch(current_user.id)


@router.post("/kill-switch/disable")
async def disable_kill_switch(current_user: UserProfile = Depends(get_current_user)):
    return await risk_service.disable_kill_switch(current_user.id)


@router.get("/kill-switch")
async def kill_switch_status(current_user: UserProfile = Depends(get_current_user)):
    return await risk_service.kill_switch_status(current_user.id)


@router.post("/live/enable")
async def enable_live(
    req: LiveEnableRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    return await risk_service.enable_live(current_user.id, req.confirm)


@router.post("/live/disable")
async def disable_live(current_user: UserProfile = Depends(get_current_user)):
    return await risk_service.disable_live(current_user.id)


@router.get("/live/status")
async def live_status(current_user: UserProfile = Depends(get_current_user)):
    return await risk_service.live_status(current_user.id)
