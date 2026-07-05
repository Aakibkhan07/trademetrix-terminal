from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import get_supabase
from core.capabilities import Capabilities
from core.deps import get_capabilities, get_current_user
from core.models import RiskSettings, UserProfile
from core.safe_query import safe_execute
from risk.riskguard import RiskGuard

router = APIRouter(prefix="/risk", tags=["risk"])


class UpdateRiskRequest(BaseModel):
    strategy_id: str | None = None
    max_capital: float = 0.0
    max_position_size: float = 0.0
    max_open_positions: int = 10
    max_daily_loss: float = 0.0
    max_drawdown_pct: float = 0.0


@router.get("/settings")
async def get_risk_settings(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    data = safe_execute(supabase.table("risk_settings").select("*").eq("user_id", current_user.id))
    return {"settings": data or []}


@router.post("/settings")
async def update_risk_settings(
    req: UpdateRiskRequest,
    current_user: UserProfile = Depends(get_current_user),
    caps: Capabilities = Depends(get_capabilities),
):
    tier_floor = caps.daily_loss_floor
    if req.max_daily_loss == 0:
        raise HTTPException(
            status_code=400,
            detail=f"Daily loss cap cannot be disabled. Minimum is your tier default of ₹{tier_floor:.0f}.",
        )
    if req.max_daily_loss < tier_floor:
        raise HTTPException(
            status_code=400,
            detail=f"max_daily_loss {req.max_daily_loss:.0f} is below your tier floor of ₹{tier_floor:.0f}. You may raise it, but not lower it below your tier's default.",
        )

    rg = RiskGuard(current_user.id)
    settings = RiskSettings(
        user_id=current_user.id,
        strategy_id=req.strategy_id,
        max_capital=req.max_capital,
        max_position_size=req.max_position_size,
        max_open_positions=req.max_open_positions,
        max_daily_loss=req.max_daily_loss,
        max_drawdown_pct=req.max_drawdown_pct,
    )
    await rg.update_settings(settings)
    return {"message": "Risk settings updated"}


@router.post("/kill-switch/enable")
async def enable_kill_switch(current_user: UserProfile = Depends(get_current_user)):
    rg = RiskGuard(current_user.id)
    await rg.enable_kill_switch()
    return {"message": "Kill switch enabled"}


@router.post("/kill-switch/disable")
async def disable_kill_switch(current_user: UserProfile = Depends(get_current_user)):
    rg = RiskGuard(current_user.id)
    await rg.disable_kill_switch()
    return {"message": "Kill switch disabled"}


@router.get("/kill-switch")
async def kill_switch_status(current_user: UserProfile = Depends(get_current_user)):
    rg = RiskGuard(current_user.id)
    status = await rg.get_kill_switch_status()
    return {"kill_switch_enabled": status}


class LiveEnableRequest(BaseModel):
    confirm: bool = False


@router.post("/live/enable")
async def enable_live(
    req: LiveEnableRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    rg = RiskGuard(current_user.id)
    success = await rg.enable_live(multi_step_confirm=req.confirm)
    if not success:
        raise HTTPException(status_code=400, detail="Multi-step confirmation required")
    return {"message": "LIVE trading enabled"}


@router.post("/live/disable")
async def disable_live(current_user: UserProfile = Depends(get_current_user)):
    rg = RiskGuard(current_user.id)
    await rg.disable_live()
    return {"message": "LIVE trading disabled"}


@router.get("/live/status")
async def live_status(current_user: UserProfile = Depends(get_current_user)):
    rg = RiskGuard(current_user.id)
    status = await rg.get_live_status()
    return {"is_live": status}
