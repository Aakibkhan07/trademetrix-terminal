import logging

from fastapi import APIRouter, Depends, Query

from core.deps import get_current_user
from core.models import UserProfile
from market.historical import historical_engine
from market.observability import market_metrics
from market.option_chain import option_chain_engine
from market.status import market_status_service
from market.symbol_master import symbol_master

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/historical")
async def get_historical(
    symbol: str = Query("NIFTY"),
    exchange: str = Query("NSE"),
    interval: str = Query("15m"),
    days: int = Query(7),
    current_user: UserProfile = Depends(get_current_user),
):
    candles = await historical_engine.get_historical(symbol, exchange, interval, days, user_id=current_user.id)
    supported = await historical_engine.get_supported_intervals()
    return {
        "symbol": symbol,
        "exchange": exchange,
        "interval": interval,
        "days": days,
        "candles": candles,
        "supported_intervals": supported,
    }


@router.get("/option-chain")
async def get_option_chain(
    symbol: str = Query("NIFTY"),
    expiry: str = Query(""),
    current_user: UserProfile = Depends(get_current_user),
):
    data = await option_chain_engine.get_option_chain(symbol, expiry)
    expiries = await option_chain_engine.get_expiries(symbol)
    pcr = option_chain_engine.calculate_pcr(data)
    max_pain = option_chain_engine.calculate_max_pain(data)
    return {
        "symbol": symbol.upper(),
        "expiry": expiry or (expiries[0] if expiries else ""),
        "expiries": expiries,
        "pcr": pcr,
        "max_pain": max_pain,
        "data": data,
    }


@router.get("/status")
async def get_market_status():
    status = market_status_service.get_market_status()
    return status


@router.get("/instruments")
async def search_instruments(
    query: str = Query("", min_length=1),
    instrument_type: str = Query(""),
    limit: int = Query(20, le=100),
):
    results = symbol_master.search_symbols(query, instrument_type or None, limit)
    return {"query": query, "results": results, "count": len(results)}


@router.get("/metrics")
async def get_market_metrics():
    metrics = market_metrics.get_metrics()
    return metrics
