from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.deps import get_current_user
from core.db import get_supabase
from core.models import UserProfile
from engine.executor import ExecutionEngine
from engine.scheduler import scheduler

router = APIRouter(prefix="/engine", tags=["engine"])


class StartRunRequest(BaseModel):
    strategy_id: str
    broker: str
    mode: str = "PAPER"
    symbols: list[str] = []


class ExecuteSignalRequest(BaseModel):
    symbol: str
    side: str
    order_type: str = "MARKET"
    product: str = "INTRADAY"
    quantity: int
    price: float = 0.0
    trigger_price: float | None = None
    strategy_id: str | None = None


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
    result = supabase.table("strategy_runs").insert(data).execute()
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
    from core.models import NormalizedOrder, OrderSide, OrderType, ProductType, Exchange

    supabase = get_supabase()
    creds = supabase.table("broker_credentials").select("broker").eq("user_id", current_user.id).eq("is_active", True).maybe_single().execute()
    if not creds.data:
        raise HTTPException(status_code=400, detail="No active broker configured")

    engine = ExecutionEngine(current_user.id, creds.data["broker"])
    await engine.start()

    order = NormalizedOrder(
        symbol=req.symbol,
        exchange=Exchange.NSE,
        side=OrderSide(req.side),
        order_type=OrderType(req.order_type),
        product=ProductType(req.product),
        quantity=req.quantity,
        price=req.price,
        trigger_price=req.trigger_price,
        strategy_id=req.strategy_id,
    )

    result = await engine.execute_signal(order)
    await engine.stop()
    return {"result": result.model_dump()}


@router.get("/runs")
async def get_runs(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    result = supabase.table("strategy_runs").select("*").eq("user_id", current_user.id).order("created_at", desc=True).execute()
    return {"runs": result.data or []}
