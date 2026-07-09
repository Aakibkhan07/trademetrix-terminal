import asyncio
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.db import get_supabase
from core.deps import get_current_user
from core.models import UserProfile
from core.safe_query import async_safe_execute, async_safe_single

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/engine/squareoff", tags=["squareoff"])

SQUAREOFF_TABLE = "squareoff_config"


class SquareoffConfigRequest(BaseModel):
    enabled: bool = True
    time: str = "15:15"
    days: list[int] = [0, 1, 2, 3, 4]


class SquareoffConfig(BaseModel):
    enabled: bool = False
    time: str = "15:15"
    days: list[int] = [0, 1, 2, 3, 4]
    user_id: str = ""


@router.get("/config")
async def get_squareoff_config(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    data = await async_safe_single(
        supabase.table(SQUAREOFF_TABLE).select("*").eq("user_id", current_user.id)
    )
    if not data:
        return {"config": {"enabled": False, "time": "15:15", "days": [0, 1, 2, 3, 4]}}
    return {
        "config": {
            "enabled": data.get("enabled", False),
            "time": data.get("squareoff_time", "15:15"),
            "days": data.get("days", [0, 1, 2, 3, 4]),
        }
    }


@router.post("/config")
async def set_squareoff_config(
    req: SquareoffConfigRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    existing = await async_safe_single(
        supabase.table(SQUAREOFF_TABLE).select("id").eq("user_id", current_user.id)
    )
    payload = {
        "user_id": current_user.id,
        "enabled": req.enabled,
        "squareoff_time": req.time,
        "days": req.days,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if existing:
        await async_safe_execute(
            supabase.table(SQUAREOFF_TABLE).update(payload).eq("user_id", current_user.id)
        )
    else:
        payload["created_at"] = datetime.now(UTC).isoformat()
        await async_safe_execute(
            supabase.table(SQUAREOFF_TABLE).insert(payload)
        )
    set_squareoff_cache(current_user.id, SquareoffConfig(
        enabled=req.enabled, time=req.time, days=req.days, user_id=current_user.id,
    ))
    return {"message": "Squareoff config updated"}


@router.post("/run")
async def run_squareoff(current_user: UserProfile = Depends(get_current_user)):
    from core.models import Exchange, NormalizedOrder, OrderSide, OrderType, ProductType
    from engine.gate import execute_order

    supabase = get_supabase()
    creds = await async_safe_single(
        supabase.table("broker_credentials").select("broker").eq("user_id", current_user.id).eq("is_active", True)
    )
    if not creds:
        return {"message": "No active broker", "squareoff_count": 0}

    from engine.executor import ExecutionEngine
    engine = ExecutionEngine(current_user.id, creds["broker"])
    await engine.start()
    try:
        positions = await engine.get_positions()
    finally:
        await engine.stop()

    intraday = [p for p in positions if p.product in ("INTRADAY", "MIS")]
    if not intraday:
        return {"message": "No intraday positions to square off", "squareoff_count": 0}

    results = []
    for pos in intraday:
        side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY
        order = NormalizedOrder(
            symbol=pos.symbol,
            exchange=pos.exchange or Exchange.NSE,
            side=side,
            order_type=OrderType.MARKET,
            product=ProductType.INTRADAY,
            quantity=abs(pos.quantity),
            price=0,
            instrument_type=pos.instrument_type,
            strike_price=pos.strike_price,
            expiry_date=pos.expiry_date,
            option_type=pos.option_type,
            source="squareoff",
        )
        result = await execute_order(current_user.id, order, source="squareoff")
        results.append(result)

    return {
        "message": f"Squareoff executed for {len(intraday)} positions",
        "squareoff_count": len(results),
        "results": [r.model_dump() for r in results],
    }


_squareoff_cache: dict[str, SquareoffConfig] = {}
_squareoff_task: asyncio.Task | None = None


def set_squareoff_cache(user_id: str, config: SquareoffConfig):
    _squareoff_cache[user_id] = config


async def _squareoff_loop():
    while True:
        try:
            supabase = get_supabase()
            now = datetime.now()
            current_time = f"{now.hour:02d}:{now.minute:02d}"
            current_dow = now.weekday()

            configs = await async_safe_execute(
                supabase.table(SQUAREOFF_TABLE).select("*").eq("enabled", True)
            )
            for row in (configs or []):
                sq_time = row.get("squareoff_time", "15:15")
                days = row.get("days", [0, 1, 2, 3, 4])
                if current_dow not in days:
                    continue
                if sq_time == current_time:
                    user_id = row["user_id"]
                    cfg = SquareoffConfig(
                        enabled=True, time=sq_time, days=days, user_id=user_id,
                    )
                    set_squareoff_cache(user_id, cfg)
                    try:
                        from core.deps import get_user_by_id
                        user = await get_user_by_id(user_id)
                        if user:
                            await run_squareoff_for_user(user)
                    except Exception as e:
                        logger.error("Auto squareoff failed for %s: %s", user_id, e)
        except Exception as e:
            logger.error("Squareoff loop error: %s", e)
        await asyncio.sleep(30)


async def run_squareoff_for_user(user: UserProfile):
    from core.models import Exchange, NormalizedOrder, OrderSide, OrderType, ProductType
    from engine.gate import execute_order

    supabase = get_supabase()
    creds = await async_safe_single(
        supabase.table("broker_credentials").select("broker").eq("user_id", user.id).eq("is_active", True)
    )
    if not creds:
        return

    from engine.executor import ExecutionEngine
    engine = ExecutionEngine(user.id, creds["broker"])
    await engine.start()
    try:
        positions = await engine.get_positions()
    finally:
        await engine.stop()

    intraday = [p for p in positions if p.product in ("INTRADAY", "MIS")]
    for pos in intraday:
        side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY
        order = NormalizedOrder(
            symbol=pos.symbol,
            exchange=pos.exchange or Exchange.NSE,
            side=side,
            order_type=OrderType.MARKET,
            product=ProductType.INTRADAY,
            quantity=abs(pos.quantity),
            price=0,
            instrument_type=pos.instrument_type,
            strike_price=pos.strike_price,
            expiry_date=pos.expiry_date,
            option_type=pos.option_type,
            source="squareoff",
        )
        await execute_order(user.id, order, source="squareoff")


async def start_squareoff_scheduler():
    global _squareoff_task
    if _squareoff_task is None:
        _squareoff_task = asyncio.create_task(_squareoff_loop())
        logger.info("Squareoff scheduler started")


async def stop_squareoff_scheduler():
    global _squareoff_task
    if _squareoff_task:
        _squareoff_task.cancel()
        _squareoff_task = None
        logger.info("Squareoff scheduler stopped")
