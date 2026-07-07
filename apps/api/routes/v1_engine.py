import asyncio
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import async_supabase, get_supabase
from core.deps import get_current_user
from core.models import OrderResult, UserProfile
from core.safe_query import async_safe_execute, async_safe_single, safe_execute, safe_single
from engine.executor import ExecutionEngine
from engine.gate import execute_order
from engine.token_refresh import get_token_status

router = APIRouter(prefix="/engine", tags=["engine"])

_engine_cache: dict[str, tuple[ExecutionEngine, float]] = {}
_engine_lock = asyncio.Lock()
_ENGINE_TTL = 120

async def _get_engine(user_id: str, broker: str) -> ExecutionEngine:
    key = f"{user_id}:{broker}"
    entry = _engine_cache.get(key)
    if entry:
        engine, ts = entry
        if time.monotonic() - ts < _ENGINE_TTL:
            return engine
        await engine.stop()
    engine = ExecutionEngine(user_id, broker)
    await engine.start()
    _engine_cache[key] = (engine, time.monotonic())
    return engine

async def _release_engine(user_id: str, broker: str):
    entry = _engine_cache.pop(f"{user_id}:{broker}", None)
    if entry:
        await entry[0].stop()


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
        "started_at": datetime.now(UTC).isoformat(),
    }
    try:
        result = await async_supabase(lambda: supabase.table("strategy_runs").insert(payload).execute())
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
        await async_supabase(lambda: supabase.table("strategy_runs").update(
            {"status": "stopped", "stopped_at": datetime.now(UTC).isoformat()}
        ).eq("id", run_id).eq("user_id", current_user.id).execute())
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("Failed to update strategy run: %s", e)
    return {"message": "Engine stopped"}


@router.post("/trade")
async def execute_trade(
    req: ExecuteSignalRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    from core.models import Exchange, InstrumentType, NormalizedOrder, OptionType, OrderSide, OrderType, ProductType

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
        source="manual",
    )

    result = await execute_order(current_user.id, order, source="manual")
    return {"result": result.model_dump()}


@router.get("/orders")
async def get_orders(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    data = await async_safe_execute(
        supabase.table("orders").select("*").eq("user_id", current_user.id).order("created_at", desc=True).limit(100)
    )
    return {"orders": data or []}


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    from execution import execution_manager
    from execution.models import ExecutionRequest

    supabase = get_supabase()
    creds = await async_safe_single(
        supabase.table("broker_credentials").select("broker").eq("user_id", current_user.id).eq("is_active", True)
    )
    if not creds:
        raise HTTPException(status_code=400, detail="No active broker configured")

    req = ExecutionRequest(
        user_id=current_user.id,
        broker=creds["broker"],
        symbol="",
        side="",
        quantity=0,
        source="cancel",
    )
    result = await execution_manager.cancel_order(req, order_id)
    return {"result": result.model_dump()}


class OrderNoteRequest(BaseModel):
    note: str
    tags: list[str] = []


@router.post("/orders/{order_id}/note", status_code=201)
async def add_order_note(
    order_id: str,
    req: OrderNoteRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    order = await async_safe_single(
        supabase.table("orders").select("id").eq("id", order_id).eq("user_id", current_user.id)
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    result = await async_supabase(lambda: supabase.table("journal_entries").insert({
        "user_id": current_user.id,
        "entry_type": "trade_note",
        "content": req.note,
        "tags": req.tags,
        "trade_ids": [order_id],
    }).execute())
    return {"note": result.data[0]}


@router.get("/orders/notes")
async def get_order_notes(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    data = await async_safe_execute(
        supabase.table("journal_entries")
        .select("*")
        .eq("user_id", current_user.id)
        .eq("entry_type", "trade_note")
        .order("created_at", desc=True)
        .limit(100)
    ) or []
    return {"notes": data}


@router.get("/positions")
async def get_positions(
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    creds = await async_safe_single(
        supabase.table("broker_credentials").select("broker").eq("user_id", current_user.id).eq("is_active", True)
    )
    if creds:
        try:
            engine = await _get_engine(current_user.id, creds["broker"])
            positions = await engine.get_positions()
            return {"positions": [p.model_dump() for p in positions]}
        except ValueError as e:
            logger = __import__("logging").getLogger(__name__)
            logger.warning("Failed to get positions: %s", e)
    return {"positions": []}


@router.get("/funds")
async def get_funds(
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    creds = await async_safe_single(
        supabase.table("broker_credentials").select("broker").eq("user_id", current_user.id).eq("is_active", True)
    )
    if creds:
        try:
            engine = await _get_engine(current_user.id, creds["broker"])
            funds = await engine.get_funds()
            return {"funds": funds.model_dump()}
        except ValueError as e:
            logger = __import__("logging").getLogger(__name__)
            logger.warning("Failed to get funds: %s", e)
    return {"funds": {"total_margin": 0, "used_margin": 0, "available_margin": 0}}


@router.get("/runs")
async def get_runs(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    data = await async_safe_execute(
        supabase.table("strategy_runs").select("*").eq("user_id", current_user.id).order("created_at", desc=True)
    )
    return {"runs": data or []}


@router.get("/token-status")
async def token_status(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    creds = await async_safe_single(
        supabase.table("broker_credentials").select("broker").eq("user_id", current_user.id).eq("is_active", True)
    )
    if not creds:
        return {"status": "unknown", "broker": ""}
    status = await get_token_status(current_user.id, creds["broker"])
    return status
