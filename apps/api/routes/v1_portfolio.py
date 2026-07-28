import logging

from fastapi import APIRouter, Depends, HTTPException, status

from core.deps import get_current_user
from core.models import UserProfile
from portfolio.manager import portfolio_manager
from risk.helpers import get_active_broker

router = APIRouter(tags=["portfolio"])
logger = logging.getLogger(__name__)


def _find_broker(user_id: str, preferred: str | None) -> str | None:
    if preferred:
        return preferred
    import asyncio
    try:
        return asyncio.run(get_active_broker(user_id))
    except Exception:
        return None


@router.get("/api/v1/positions")
async def get_positions(
    current_user: UserProfile = Depends(get_current_user),
    broker: str | None = None,
):
    resolved = broker or await get_active_broker(current_user.id)
    if not resolved:
        return {"positions": [], "broker": None}
    try:
        await portfolio_manager.refresh(current_user.id, resolved)
        positions = await portfolio_manager.get_positions(current_user.id, resolved)
        return {"positions": [p.model_dump() for p in positions], "broker": resolved}
    except Exception as e:
        logger.error("Failed to fetch positions for user=%s broker=%s: %s", current_user.id, resolved, e)
        raise HTTPException(status_code=502, detail=f"Failed to fetch positions: {e}")


@router.get("/api/v1/holdings")
async def get_holdings(
    current_user: UserProfile = Depends(get_current_user),
    broker: str | None = None,
):
    resolved = broker or await get_active_broker(current_user.id)
    if not resolved:
        return {"holdings": [], "broker": None}
    try:
        holdings = await portfolio_manager.get_holdings(current_user.id, resolved)
        return {"holdings": [h.model_dump() for h in holdings], "broker": resolved}
    except Exception as e:
        logger.error("Failed to fetch holdings for user=%s broker=%s: %s", current_user.id, resolved, e)
        raise HTTPException(status_code=502, detail=f"Failed to fetch holdings: {e}")


@router.get("/api/v1/funds")
async def get_funds(
    current_user: UserProfile = Depends(get_current_user),
    broker: str | None = None,
):
    resolved = broker or await get_active_broker(current_user.id)
    if not resolved:
        return {"funds": None, "broker": None}
    try:
        funds = await portfolio_manager.get_margin(current_user.id, resolved)
        return {"funds": funds.model_dump(), "broker": resolved}
    except Exception as e:
        logger.error("Failed to fetch funds for user=%s broker=%s: %s", current_user.id, resolved, e)
        raise HTTPException(status_code=502, detail=f"Failed to fetch funds: {e}")


@router.get("/api/v1/portfolio/summary")
async def get_portfolio_summary(
    current_user: UserProfile = Depends(get_current_user),
):
    try:
        summary = await portfolio_manager.get_summary(current_user.id)
        return {"summary": summary.model_dump()}
    except Exception as e:
        logger.error("Failed to fetch portfolio summary for user=%s: %s", current_user.id, e)
        raise HTTPException(status_code=502, detail=f"Failed to fetch portfolio summary: {e}")
