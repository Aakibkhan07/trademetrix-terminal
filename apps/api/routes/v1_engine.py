from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from pydantic import BaseModel

from core.db import get_supabase
from core.deps import get_current_user
from core.models import UserProfile
from engine.executor import ExecutionEngine

router = APIRouter(prefix="/engine", tags=["engine"])


class StartRunRequest(BaseModel):
    strategy_id: str
    broker: str
    mode: str = "PAPER"
    symbols: list[str] = []


class ExecuteSignalRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    side: str
    order_type: str = "MARKET"
    product: str = "INTRADAY"
    quantity: int
    price: float = 0.0
    trigger_price: float | None = None
    strategy_id: str | None = None
    instrument_type: str = "EQ"
    strike_price: float | None = None
    expiry_date: str | None = None
    option_type: str | None = None


@router.post("/start")
async def start_engine(
    req: StartRunRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    data = {
        "user_id": current_user.id,
        "strategy_id": req.strategy_id,
        "broker": req.broker,
        "mode": req.mode,
        "symbols": req.symbols,
        "status": "running",
        "started_at": datetime.utcnow().isoformat(),
    }
    try:
        result = supabase.table("strategy_runs").insert(data).execute()
    except APIError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": result.data[0]["id"], "status": "running"}


@router.post("/stop/{run_id}")
async def stop_engine(
    run_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    supabase.table("strategy_runs").update(
        {"status": "stopped", "stopped_at": datetime.utcnow().isoformat()}
    ).eq("id", run_id).eq("user_id", current_user.id).execute()
    return {"message": "Engine stopped"}


@router.post("/trade")
async def execute_trade(
    req: ExecuteSignalRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    from core.models import (
        Exchange,
        InstrumentType,
        NormalizedOrder,
        OptionType,
        OrderSide,
        OrderType,
        ProductType,
    )

    supabase = get_supabase()
    creds = supabase.table("broker_credentials").select("broker").eq("user_id", current_user.id).eq("is_active", True).maybe_single().execute()
    if not creds.data:
        raise HTTPException(status_code=400, detail="No active broker configured")

    engine = ExecutionEngine(current_user.id, creds.data["broker"])
    await engine.start()

    order = NormalizedOrder(
        symbol=req.symbol,
        exchange=Exchange(req.exchange),
        side=OrderSide(req.side),
        order_type=OrderType(req.order_type),
        product=ProductType(req.product),
        quantity=req.quantity,
        price=req.price,
        trigger_price=req.trigger_price,
        strategy_id=req.strategy_id,
        instrument_type=InstrumentType(req.instrument_type),
        strike_price=req.strike_price,
        expiry_date=req.expiry_date,
        option_type=OptionType(req.option_type) if req.option_type else None,
    )

    result = await engine.execute_signal(order)
    await engine.stop()
    return {"result": result.model_dump()}


@router.get("/orders")
async def get_orders(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    result = supabase.table("orders").select("*").eq("user_id", current_user.id).order("created_at", desc=True).limit(100).execute()
    return {"orders": result.data or []}


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    creds = supabase.table("broker_credentials").select("broker").eq("user_id", current_user.id).eq("is_active", True).maybe_single().execute()
    if not creds.data:
        raise HTTPException(status_code=400, detail="No active broker configured")

    engine = ExecutionEngine(current_user.id, creds.data["broker"])
    await engine.start()
    result = await engine.cancel_order(order_id)
    await engine.stop()
    return {"result": result.model_dump()}


@router.get("/positions")
async def get_positions(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    creds = supabase.table("broker_credentials").select("broker").eq("user_id", current_user.id).eq("is_active", True).maybe_single().execute()
    if creds.data:
        engine = ExecutionEngine(current_user.id, creds.data["broker"])
        await engine.start()
        positions = await engine.get_positions()
        await engine.stop()
        return {"positions": [p.model_dump() for p in positions]}
    return {"positions": []}


@router.get("/funds")
async def get_funds(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    creds = supabase.table("broker_credentials").select("broker").eq("user_id", current_user.id).eq("is_active", True).maybe_single().execute()
    if creds.data:
        engine = ExecutionEngine(current_user.id, creds.data["broker"])
        await engine.start()
        funds = await engine.get_funds()
        await engine.stop()
        return {"funds": funds.model_dump()}
    return {"funds": {"total_margin": 0, "used_margin": 0, "available_margin": 0}}


@router.get("/runs")
async def get_runs(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    result = supabase.table("strategy_runs").select("*").eq("user_id", current_user.id).order("created_at", desc=True).execute()
    return {"runs": result.data or []}
