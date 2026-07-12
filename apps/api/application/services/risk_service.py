import logging
from typing import Any

from fastapi import HTTPException

from core.capabilities import Capabilities
from core.db import get_supabase
from core.models import RiskSettings
from core.safe_query import async_safe_execute
from risk.riskguard import RiskGuard

logger = logging.getLogger(__name__)


class RiskService:
    async def get_settings(self, user_id: str) -> dict:
        supabase = get_supabase()
        data = await async_safe_execute(supabase.table("risk_settings").select("*").eq("user_id", user_id))
        return {"settings": data or []}

    async def update_settings(self, user_id: str, req: Any, caps: Capabilities) -> dict:
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
        rg = RiskGuard(user_id)
        settings = RiskSettings(
            user_id=user_id,
            strategy_id=req.strategy_id,
            max_capital=req.max_capital,
            max_position_size=req.max_position_size,
            max_open_positions=req.max_open_positions,
            max_daily_loss=req.max_daily_loss,
            max_drawdown_pct=req.max_drawdown_pct,
        )
        await rg.update_settings(settings)
        return {"message": "Risk settings updated"}

    async def enable_kill_switch(self, user_id: str) -> dict:
        rg = RiskGuard(user_id)
        await rg.enable_kill_switch()
        return {"message": "Kill switch enabled"}

    async def disable_kill_switch(self, user_id: str) -> dict:
        rg = RiskGuard(user_id)
        await rg.disable_kill_switch()
        return {"message": "Kill switch disabled"}

    async def kill_switch_status(self, user_id: str) -> dict:
        rg = RiskGuard(user_id)
        status = await rg.get_kill_switch_status()
        return {"kill_switch_enabled": status}

    async def enable_live(self, user_id: str, confirm: bool) -> dict:
        rg = RiskGuard(user_id)
        success = await rg.enable_live(multi_step_confirm=confirm)
        if not success:
            raise HTTPException(status_code=400, detail="Multi-step confirmation required")
        return {"message": "LIVE trading enabled"}

    async def disable_live(self, user_id: str) -> dict:
        rg = RiskGuard(user_id)
        await rg.disable_live()
        return {"message": "LIVE trading disabled"}

    async def live_status(self, user_id: str) -> dict:
        rg = RiskGuard(user_id)
        status = await rg.get_live_status()
        return {"is_live": status}
