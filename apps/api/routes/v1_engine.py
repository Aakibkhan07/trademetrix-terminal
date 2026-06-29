from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.db import get_supabase
from core.deps import get_current_user
from core.models import UserProfile
from core.safe_query import safe_execute, safe_single
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
    payload = {
        "user_id": current_user.id,
        "strategy_id": req.strategy_id,
        "broker": req.broker,
        "mode": req.mode,
        "symbols": req.symbols,
        "status": "running",
        "started_at": datetime.utcnow().isoformat(),
    }
    try:
        result = supabase.table("strategy_runs").insert(payload).execute()
        return {"run_id": result.data[0]["id"], "status": "running"}
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("Failed to start engine run: %s", e)
        return {"run_id": "", "status": "error", "detail": str(e)}


@router.post("/stop/{run_id}")
async def stop_engine(
    run_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    try:
        supabase.table("strategy_runs").update(
            {"status": "stopped", "stopped_at": datetime.utcnow().isoformat()}
        ).eq("id", run_id).eq("user_id", current_user.id).execute()
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("Failed to update strategy run: %s", e)
    return {"message": "Engine stopped"}


@router.post("/trade")
async def execute_trade(
    req: ExecuteSignalRequest,
    paper: bool = Query(True),
    current_user: UserProfile = Depends(get_current_user),
):
    from core.models import Exchange, InstrumentType, NormalizedOrder, OptionType, OrderSide, OrderType, ProductType

    supabase = get_supabase()
    creds = safe_single(
        supabase.table("broker_credentials").select("broker").eq("user_id", current_user.id).eq("is_active", True)
    )
    if not creds:
        raise HTTPException(status_code=400, detail="No active broker configured")

    engine = ExecutionEngine(current_user.id, creds["broker"], is_paper=paper)
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
    data = safe_execute(
        supabase.table("orders").select("*").eq("user_id", current_user.id).order("created_at", desc=True).limit(100)
    )
    return {"orders": data or []}


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    creds = safe_single(
        supabase.table("broker_credentials").select("broker").eq("user_id", current_user.id).eq("is_active", True)
    )
    if not creds:
        raise HTTPException(status_code=400, detail="No active broker configured")

    engine = ExecutionEngine(current_user.id, creds["broker"])
    await engine.start()
    result = await engine.cancel_order(order_id)
    await engine.stop()
    return {"result": result.model_dump()}


@router.get("/positions")
async def get_positions(
    paper: bool = Query(True),
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    creds = safe_single(
        supabase.table("broker_credentials").select("broker").eq("user_id", current_user.id).eq("is_active", True)
    )
    if creds:
        engine = ExecutionEngine(current_user.id, creds["broker"], is_paper=paper)
        await engine.start()
        positions = await engine.get_positions()
        await engine.stop()
        return {"positions": [p.model_dump() for p in positions]}
    return {"positions": []}


@router.get("/funds")
async def get_funds(
    paper: bool = Query(True),
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    creds = safe_single(
        supabase.table("broker_credentials").select("broker").eq("user_id", current_user.id).eq("is_active", True)
    )
    if creds:
        engine = ExecutionEngine(current_user.id, creds["broker"], is_paper=paper)
        await engine.start()
        funds = await engine.get_funds()
        await engine.stop()
        return {"funds": funds.model_dump()}
    return {"funds": {"total_margin": 0, "used_margin": 0, "available_margin": 0}}


@router.get("/runs")
async def get_runs(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    data = safe_execute(
        supabase.table("strategy_runs").select("*").eq("user_id", current_user.id).order("created_at", desc=True)
    )
    return {"runs": data or []}
