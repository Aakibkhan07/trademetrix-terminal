import logging
from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from application.services.multileg_service import MultiLegService
from core.deps import get_current_user
from core.models import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategies/multi-leg", tags=["multi-leg"])
service = MultiLegService()


class LegAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class LegDefinition(BaseModel):
    action: LegAction
    symbol: str
    quantity: int
    exchange: str = "NFO"
    order_type: str = "MARKET"
    product: str = "INTRADAY"
    price: float = 0.0
    trigger_price: float | None = None
    instrument_type: str = "OPT"
    strike_price: float | None = None
    expiry_date: str | None = None
    option_type: str | None = None


class CreateStrategyRequest(BaseModel):
    name: str
    description: str = ""
    underlying: str = "NIFTY"
    expiry: str = "weekly"
    legs: list[LegDefinition] = Field(min_length=1)


class PlaceMultiLegRequest(BaseModel):
    strategy_id: str
    broker: str = "fyers"


@router.get("/strategies")
async def list_strategies(current_user: UserProfile = Depends(get_current_user)):
    strategies = await service.list_strategies(current_user.id)
    return {"strategies": strategies}


@router.get("/strategies/{strategy_id}")
async def get_strategy(strategy_id: str, current_user: UserProfile = Depends(get_current_user)):
    data = await service.get_strategy(strategy_id, current_user.id)
    if not data:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"strategy": data}


@router.post("/strategies")
async def create_strategy(req: CreateStrategyRequest, current_user: UserProfile = Depends(get_current_user)):
    result = await service.create_strategy(current_user.id, req)
    return result


@router.delete("/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str, current_user: UserProfile = Depends(get_current_user)):
    deleted = await service.delete_strategy(strategy_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"message": "Strategy deleted"}


@router.post("/strategies/{strategy_id}/place")
async def place_strategy(strategy_id: str, req: PlaceMultiLegRequest, current_user: UserProfile = Depends(get_current_user)):
    try:
        result = await service.place_strategy(strategy_id, current_user.id)
    except ValueError as e:
        if "defined" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=404, detail=str(e))
    return result
