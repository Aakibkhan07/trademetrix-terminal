import logging
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import get_supabase
from core.deps import get_current_user
from core.models import (
    Exchange,
    InstrumentType,
    NormalizedOrder,
    OptionType,
    OrderSide,
    OrderType,
    ProductType,
    UserProfile,
)
from core.safe_query import async_safe_execute, async_safe_single

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategies/multi-leg", tags=["multi-leg"])


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


class StrategyDefinition(BaseModel):
    name: str
    description: str = ""
    underlying: str = "NIFTY"
    expiry: str = "weekly"
    legs: list[LegDefinition] = Field(min_length=1)


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
    supabase = get_supabase()
    data = await async_safe_execute(
        supabase.table("multi_leg_strategies")
        .select("*")
        .eq("user_id", current_user.id)
        .order("created_at", desc=True)
    )
    return {"strategies": data or []}


@router.get("/strategies/{strategy_id}")
async def get_strategy(strategy_id: str, current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    data = await async_safe_single(
        supabase.table("multi_leg_strategies")
        .select("*")
        .eq("id", strategy_id)
        .eq("user_id", current_user.id)
    )
    if not data:
        raise HTTPException(status_code=404, detail="Strategy not found")
    legs = await async_safe_execute(
        supabase.table("multi_leg_strategy_legs")
        .select("*")
        .eq("strategy_id", strategy_id)
        .order("leg_index")
    )
    data["legs"] = legs or []
    return {"strategy": data}


@router.post("/strategies")
async def create_strategy(req: CreateStrategyRequest, current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    strat_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    strat_payload = {
        "id": strat_id,
        "user_id": current_user.id,
        "name": req.name,
        "description": req.description,
        "underlying": req.underlying,
        "expiry": req.expiry,
        "leg_count": len(req.legs),
        "status": "draft",
        "created_at": now,
        "updated_at": now,
    }
    await async_safe_execute(supabase.table("multi_leg_strategies").insert(strat_payload))
    for i, leg in enumerate(req.legs):
        leg_payload = {
            "id": str(uuid.uuid4()),
            "strategy_id": strat_id,
            "leg_index": i,
            "action": leg.action.value,
            "symbol": leg.symbol,
            "quantity": leg.quantity,
            "exchange": leg.exchange,
            "order_type": leg.order_type,
            "product": leg.product,
            "price": leg.price,
            "trigger_price": leg.trigger_price,
            "instrument_type": leg.instrument_type,
            "strike_price": leg.strike_price,
            "expiry_date": leg.expiry_date,
            "option_type": leg.option_type,
            "created_at": now,
        }
        await async_safe_execute(supabase.table("multi_leg_strategy_legs").insert(leg_payload))
    return {"strategy_id": strat_id, "name": req.name, "leg_count": len(req.legs)}


@router.delete("/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str, current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    existing = await async_safe_single(
        supabase.table("multi_leg_strategies").select("id").eq("id", strategy_id).eq("user_id", current_user.id)
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Strategy not found")
    await async_safe_execute(supabase.table("multi_leg_strategy_legs").delete().eq("strategy_id", strategy_id))
    await async_safe_execute(supabase.table("multi_leg_strategies").delete().eq("id", strategy_id))
    return {"message": "Strategy deleted"}


@router.post("/strategies/{strategy_id}/place")
async def place_strategy(strategy_id: str, req: PlaceMultiLegRequest, current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    data = await async_safe_single(
        supabase.table("multi_leg_strategies").select("*").eq("id", strategy_id).eq("user_id", current_user.id)
    )
    if not data:
        raise HTTPException(status_code=404, detail="Strategy not found")
    legs = await async_safe_execute(
        supabase.table("multi_leg_strategy_legs").select("*").eq("strategy_id", strategy_id).order("leg_index")
    )
    if not legs:
        raise HTTPException(status_code=400, detail="No legs defined")

    from engine.gate import execute_order

    results = []
    order_ids = []
    for leg in legs:
        order = NormalizedOrder(
            symbol=leg["symbol"],
            exchange=Exchange(leg.get("exchange", "NFO")),
            side=OrderSide.BUY if leg["action"] == "BUY" else OrderSide.SELL,
            order_type=OrderType(leg.get("order_type", "MARKET")),
            product=ProductType(leg.get("product", "INTRADAY")),
            quantity=leg["quantity"],
            price=float(leg.get("price", 0)),
            trigger_price=float(leg["trigger_price"]) if leg.get("trigger_price") else None,
            instrument_type=InstrumentType(leg.get("instrument_type", "OPT")),
            strike_price=float(leg["strike_price"]) if leg.get("strike_price") else None,
            expiry_date=leg.get("expiry_date"),
            option_type=OptionType(leg["option_type"]) if leg.get("option_type") else None,
            strategy_id=strategy_id,
            source="multi_leg",
        )
        result = await execute_order(current_user.id, order, source="multi_leg")
        results.append(result)
        order_ids.append(result.broker_order_id)

    now = datetime.now(UTC).isoformat()
    await async_safe_execute(
        supabase.table("multi_leg_strategies")
        .update({"status": "active", "last_placed_at": now, "updated_at": now})
        .eq("id", strategy_id)
    )

    return {
        "message": f"Placed {len(results)} legs",
        "strategy_id": strategy_id,
        "order_ids": order_ids,
        "results": [r.model_dump() for r in results],
    }
