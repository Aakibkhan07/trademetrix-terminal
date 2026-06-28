import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.deps import get_current_user
from core.models import UserProfile
from engine.backtest import BacktestEngine, fetch_historical_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    strategy_type: str
    symbol: str = "NIFTY"
    exchange: str = "NSE"
    interval: str = "15m"
    days: int = 60
    initial_capital: float = 100000
    config: dict = {}


@router.post("/run")
async def run_backtest(
    req: BacktestRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    try:
        candles = await fetch_historical_data(
            symbol=req.symbol,
            exchange=req.exchange,
            interval=req.interval,
            days=req.days,
        )

        engine = BacktestEngine(
            strategy_type=req.strategy_type,
            config=req.config,
            initial_capital=req.initial_capital,
        )

        result = await engine.run(candles)
        return {
            "symbol": req.symbol,
            "strategy": req.strategy_type,
            "interval": req.interval,
            "days": req.days,
            "initial_capital": req.initial_capital,
            "candles_analyzed": len(candles),
            "results": result.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Backtest failed")
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")


@router.get("/strategies")
async def list_backtest_strategies():
    from strategies import list_strategies
    return {"strategies": list_strategies()}
