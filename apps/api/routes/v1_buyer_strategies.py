"""Routes for options-buying strategy lifecycle."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.deps import get_current_user
from core.models import UserProfile
from engine.buyer_strategy_runner import BUYER_KEYS, buyer_strategy_runner
from engine.backtest import fetch_historical_data
from strategies import get_strategy
from strategies.buyer_backtest import BuyerBacktestEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/buyer-strategies", tags=["buyer_strategies"])


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
    if req.strategy_key not in BUYER_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown buyer strategy: {req.strategy_key}")
    try:
        get_strategy(req.strategy_key)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Strategy class not found: {req.strategy_key}")

    if req.index not in ("NIFTY", "SENSEX"):
        raise HTTPException(status_code=400, detail="index must be NIFTY or SENSEX")

    config = {
        "strategy_id": req.strategy_id,
        "user_id": current_user.id,
        "index": req.index,
        "strategy_key": req.strategy_key,
        **req.config,
    }
    success = await buyer_strategy_runner.activate(req.strategy_id, config, req.index)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to activate strategy")
    return {"message": "Strategy activated", "strategy_id": req.strategy_id}


@router.post("/deactivate/{strategy_id}")
async def deactivate_buyer_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    success = await buyer_strategy_runner.deactivate(strategy_id)
    if not success:
        raise HTTPException(status_code=404, detail="Strategy not found or already inactive")
    return {"message": "Strategy deactivated"}


@router.get("/status")
async def buyer_strategy_status():
    statuses = await buyer_strategy_runner.get_statuses()
    return {"strategies": statuses}


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
    if req.strategy_key not in BUYER_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown buyer strategy: {req.strategy_key}")
    try:
        get_strategy(req.strategy_key)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Strategy class not found: {req.strategy_key}")

    config = {
        "strategy_id": f"bt_{req.strategy_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "user_id": current_user.id,
        "index": req.symbol,
        "capital": req.initial_capital,
        **req.config,
    }

    try:
        candles = await fetch_historical_data(
            symbol=req.symbol,
            exchange=req.exchange,
            interval=req.interval,
            days=req.days,
            user_id=current_user.id,
        )
    except Exception as e:
        logger.warning("Fyers data fetch failed (%s), using simulated data", e)
        candles = _generate_simulated_candles(req.symbol, req.days, req.interval)

    if not candles:
        candles = _generate_simulated_candles(req.symbol, req.days, req.interval)

    engine = BuyerBacktestEngine(req.strategy_key, config, req.initial_capital)
    results = await engine.run(candles)
    return {
        "symbol": req.symbol,
        "strategy": req.strategy_key,
        "interval": req.interval,
        "days": req.days,
        **results,
    }


def _generate_simulated_candles(symbol: str, days: int, interval: str) -> list[dict]:
    import random
    import math
    from datetime import datetime, timedelta, timezone

    mins = _parse_interval_minutes(interval)
    count = days * 375 // mins
    base = 22000.0 if "SENSEX" in symbol else 19500.0
    candles = []
    now = datetime.now(timezone.utc)
    price = base

    for i in range(count):
        ts = now - timedelta(minutes=(count - i) * mins)
        if ts.weekday() >= 5:
            continue
        if ts.hour < 9 or ts.hour >= 15 or (ts.hour == 15 and ts.minute > 15):
            continue
        change = price * random.gauss(0, 0.003)
        o = price
        h = o + abs(change) * random.uniform(1.0, 1.5) + random.random() * 20
        l = o - abs(change) * random.uniform(1.0, 1.5) - random.random() * 20
        c = o + change
        price = c
        candles.append({
            "symbol": symbol,
            "exchange": "NSE",
            "interval": interval,
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": int(random.uniform(50000, 500000)),
            "timestamp": ts.isoformat(),
        })
    return candles


def _parse_interval_minutes(interval: str) -> int:
    interval = interval.lower().strip()
    try:
        if interval.endswith("min"):
            return int(interval.replace("min", ""))
        if interval.endswith("h"):
            return int(interval.replace("h", "")) * 60
        if interval.endswith("d"):
            return int(interval.replace("d", "")) * 1440
        if interval.endswith("m"):
            return int(interval.replace("m", ""))
        return int(interval)
    except (ValueError, AttributeError):
        return 5

