import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

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
    except RuntimeError:
        logger.exception("buyer strategy activate failed")
        raise HTTPException(status_code=500, detail="Buyer strategy activation failed")


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
    days: int = Field(default=30, ge=1, le=1825)
    initial_capital: float = Field(default=100000.0, gt=0)
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


@router.get("/hero-zero/{index}")
async def hero_zero_finder(index: str, current_user: UserProfile = Depends(get_current_user)):
    from datetime import datetime, timedelta, timezone
    from market.instrument_service import instrument_service
    from core.constants import STRIKE_INTERVALS
    idx = index.upper()
    is_expiry = False
    try:
        from strategies.hero_zero import EXPIRY_WEEKDAY
        wd = EXPIRY_WEEKDAY.get(idx, 3)
        is_expiry = datetime.now(timezone(timedelta(hours=5, minutes=30))).weekday() == wd
    except Exception:
        pass
    spot = 0
    try:
        spot = await instrument_service.spot_price(idx)
    except Exception:
        pass
    if not spot:
        spot = 24500 if idx == "NIFTY" else 81000 if idx == "SENSEX" else 51000
    expiry = await instrument_service.nearest_weekly_expiry(idx)
    strikes = await instrument_service.strikes(idx)
    if not strikes:
        step = STRIKE_INTERVALS.get(idx, 50)
        atm = round(spot / step) * step
        strikes = [atm + i * step for i in range(-6, 7)]
    heroes = []
    for dist in [0, 1, 2, 3, 4, 5]:
        for cepe in ["CE", "PE"]:
            step = STRIKE_INTERVALS.get(idx, 50)
            atm = round(spot / step) * step
            strike = atm + dist * step if cepe == "CE" else atm - dist * step
            try:
                prem = await instrument_service.option_ltp(idx, expiry, strike, cepe)
            except Exception:
                prem = 0
            if 5 <= prem < 100:
                heroes.append({"index": idx, "expiry": expiry, "strike": strike, "cepe": cepe, "premium": round(prem, 2), "spot": spot, "is_expiry": is_expiry, "lots": 10, "qty": 10 * (65 if idx == "NIFTY" else 20 if idx == "SENSEX" else 30), "target": round(prem * 3.5, 2), "sl": round(prem * 0.6, 2)})
    return {"index": idx, "is_expiry": is_expiry, "spot": spot, "expiry": expiry, "heroes": heroes, "count": len(heroes)}
