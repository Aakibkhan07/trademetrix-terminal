import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from application.services.buyer_strategy_service import BuyerStrategyService
from core.deps import get_current_user
from core.models import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/buyer-strategies", tags=["buyer_strategies"])

service = BuyerStrategyService()


class ActivateRequest(BaseModel):
    strategy_id: str
    strategy_key: str
    index: str = "NIFTY"
    config: dict = {}


class DeactivateRequest(BaseModel):
    strategy_id: str


@router.post("/activate")
async def activate_buyer_strategy(
    req: ActivateRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    try:
        return await service.activate(
            user_id=current_user.id,
            strategy_id=req.strategy_id,
            strategy_key=req.strategy_key,
            index=req.index,
            config=req.config,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deactivate/{strategy_id}")
async def deactivate_buyer_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    try:
        return await service.deactivate(strategy_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/status")
async def buyer_strategy_status():
    return await service.status()


class BacktestBuyerRequest(BaseModel):
    strategy_key: str
    symbol: str = "NIFTY"
    exchange: str = "NSE"
    interval: str = "5m"
    days: int = 30
    initial_capital: float = 100000.0
    config: dict = {}


@router.post("/backtest")
async def backtest_buyer_strategy(
    req: BacktestBuyerRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    try:
        return await service.backtest(
            user_id=current_user.id,
            strategy_key=req.strategy_key,
            symbol=req.symbol,
            exchange=req.exchange,
            interval=req.interval,
            days=req.days,
            initial_capital=req.initial_capital,
            config=req.config,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
