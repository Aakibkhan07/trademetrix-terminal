import logging

from fastapi import APIRouter, Depends, HTTPException, status

from core.config import settings
from core.db import async_supabase, get_supabase
from core.capabilities import Capabilities
from core.deps import get_capabilities, get_current_user, require_feature
from core.models import (
    CreateUserStrategyRequest, DeployStrategyRequest,
    NormalizedOrder, UpdateUserStrategyRequest, UserProfile,
    UserStrategy, UserStrategyLeg,
)
from core.safe_query import async_safe_execute, async_safe_single
from engine.gate import execute_order
from engine.strategy_compiler import (
    MAX_LOTS, ValidationError, compile_user_strategy, validate_user_strategy,
)

router = APIRouter(prefix="/user-strategies", tags=["user-strategies"])
logger = logging.getLogger(__name__)


def _row_to_strategy(row: dict) -> UserStrategy:
    legs_data = row.pop("legs", []) or []
    strategy = UserStrategy(**{k: v for k, v in row.items() if v is not None})
    strategy.legs = [UserStrategyLeg(**leg) for leg in sorted(legs_data, key=lambda x: x.get("leg_order", 0))]
    return strategy


@router.get("/")
async def list_user_strategies(
    current_user: UserProfile = Depends(get_current_user),
    status_filter: str | None = None,
):
    supabase = get_supabase()
    query = supabase.table("user_strategies").select("*, legs:user_strategy_legs(*)").eq("user_id", current_user.id)
    if status_filter:
        query = query.eq("status", status_filter)
    data = await async_safe_execute(query.order("created_at", desc=True))
    return {"strategies": [UserStrategy(**{k: v for k, v in row.items() if v is not None}) for row in (data or [])]}


@router.post("/", status_code=201)
async def create_user_strategy(
    req: CreateUserStrategyRequest,
    current_user: UserProfile = Depends(require_feature("builder")),
    caps: Capabilities = Depends(get_capabilities),
):
    supabase = get_supabase()
    if current_user.role != "super_admin":
        existing = await async_safe_execute(
            supabase.table("user_strategies").select("id").eq("user_id", current_user.id).neq("status", "draft")
        )
        if existing and len(existing) >= caps.max_active_strategies:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your plan allows a maximum of {caps.max_active_strategies} active strategies. Upgrade your plan or delete existing strategies.",
            )

    strategy = UserStrategy(
        user_id=current_user.id,
        name=req.name,
        strategy_type=req.strategy_type,
        index_symbol=req.index_symbol,
        underlying_from=req.underlying_from,
        entry_time=req.entry_time,
        exit_time=req.exit_time,
        days_of_week=req.days_of_week,
        overall_sl_type=req.overall_sl_type,
        overall_sl_value=req.overall_sl_value,
        overall_target_type=req.overall_target_type,
        overall_target_value=req.overall_target_value,
        legs=req.legs,
    )

    try:
        validate_user_strategy(strategy)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)

    strategy_data = strategy.model_dump(exclude={"id", "legs", "created_at", "updated_at"})
    strategy_data["user_id"] = current_user.id
    strategy_data["days_of_week"] = f"{{{','.join(str(d) for d in (req.days_of_week or [1,2,3,4,5]))}}}"

    try:
        result = await async_supabase(lambda: supabase.table("user_strategies").insert(strategy_data).execute())
    except Exception as e:
        logger.warning("Failed to create strategy: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create strategy")

    if not result or not result.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create strategy")

    strategy_id = result.data[0]["id"]
    legs_to_insert = []
    for leg in req.legs:
        leg_data = leg.model_dump(exclude={"id", "strategy_id"}, exclude_none=True)
        leg_data["strategy_id"] = strategy_id
        legs_to_insert.append(leg_data)

    if legs_to_insert:
        try:
            await async_supabase(lambda: supabase.table("user_strategy_legs").insert(legs_to_insert).execute())
        except Exception as e:
            logger.warning("Failed to insert legs, cleaning up strategy: %s", e)
            await async_supabase(lambda: supabase.table("user_strategies").delete().eq("id", strategy_id).execute())
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create strategy legs")

    return {"id": strategy_id, "message": "Strategy created"}


@router.get("/{strategy_id}")
async def get_user_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    row = await async_safe_single(
        supabase.table("user_strategies").select("*, legs:user_strategy_legs(*)").eq("id", strategy_id).eq("user_id", current_user.id)
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return _row_to_strategy(row)


@router.get("/{strategy_id}/activity")
async def get_strategy_activity(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    rows = await async_safe_execute(
        supabase.table("audit_log")
        .select("*")
        .eq("user_id", current_user.id)
        .order("created_at", desc=True)
        .limit(50)
    ) or []
    filtered = [
        r for r in rows
        if r.get("resource") == f"strategy/{strategy_id}"
        or (r.get("resource") == "order" and r.get("strategy_id") == strategy_id)
    ]
    return {"activity": filtered}


@router.patch("/{strategy_id}")
async def update_user_strategy(
    strategy_id: str,
    req: UpdateUserStrategyRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    row = await async_safe_single(
        supabase.table("user_strategies").select("id").eq("id", strategy_id).eq("user_id", current_user.id)
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    updates = {}
    for field in ("name", "status", "strategy_type", "index_symbol", "underlying_from", "entry_time", "exit_time",
                  "overall_sl_type", "overall_sl_value", "overall_target_type", "overall_target_value"):
        val = getattr(req, field, None)
        if val is not None:
            updates[field] = val

    if req.days_of_week is not None:
        updates["days_of_week"] = f"{{{','.join(str(d) for d in req.days_of_week)}}}"

    if updates:
        try:
            await async_supabase(lambda: supabase.table("user_strategies").update(updates).eq("id", strategy_id).execute())
        except Exception as e:
            logger.warning("Failed to update strategy: %s", e)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update strategy")

    if req.legs is not None:
        try:
            await async_supabase(lambda: supabase.table("user_strategy_legs").delete().eq("strategy_id", strategy_id).execute())
            legs_to_insert = []
            for leg in req.legs:
                leg_data = leg.model_dump(exclude={"id", "strategy_id"}, exclude_none=True)
                leg_data["strategy_id"] = strategy_id
                legs_to_insert.append(leg_data)
            if legs_to_insert:
                await async_supabase(lambda: supabase.table("user_strategy_legs").insert(legs_to_insert).execute())
        except Exception as e:
            logger.warning("Failed to update legs: %s", e)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update strategy legs")

    return {"message": "Strategy updated"}


@router.delete("/{strategy_id}", status_code=204)
async def delete_user_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    await async_supabase(lambda: supabase.table("user_strategies").delete().eq("id", strategy_id).eq("user_id", current_user.id).execute())


@router.post("/{strategy_id}/deploy")
async def deploy_user_strategy(
    strategy_id: str,
    req: DeployStrategyRequest,
    current_user: UserProfile = Depends(require_feature("builder")),
    caps: Capabilities = Depends(get_capabilities),
):
    if req.mode.upper() == "LIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="LIVE deploy for user strategies is not enabled yet",
        )

    if req.mode.upper() != "PAPER":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mode must be 'PAPER' or 'LIVE'",
        )

    supabase = get_supabase()

    if current_user.role != "super_admin":
        existing = await async_safe_execute(
            supabase.table("user_strategies").select("id").eq("user_id", current_user.id).neq("status", "draft")
        )
        if existing and len(existing) >= caps.max_active_strategies:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your plan allows a maximum of {caps.max_active_strategies} active strategies. Upgrade your plan or delete existing strategies.",
            )

    row = await async_safe_single(
        supabase.table("user_strategies").select("*, legs:user_strategy_legs(*)").eq("id", strategy_id).eq("user_id", current_user.id)
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    strategy = _row_to_strategy(row)

    try:
        validate_user_strategy(strategy)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)

    plan = compile_user_strategy(strategy)

    results = []
    for i, order in enumerate(plan.orders):
        try:
            result = await execute_order(
                user_id=current_user.id,
                order=order,
                source="user_strategy",
            )
            results.append({
                "leg_order": plan.legs[i].leg_order if i < len(plan.legs) else i + 1,
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "success": result.success,
                "status": result.status,
                "message": result.message,
                "broker_order_id": result.broker_order_id,
            })
        except Exception as e:
            logger.exception("Deploy leg %d failed: %s", i, e)
            results.append({
                "leg_order": plan.legs[i].leg_order if i < len(plan.legs) else i + 1,
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "success": False,
                "status": "error",
                "message": str(e),
            })

    if all(r["success"] for r in results):
        await async_supabase(lambda: supabase.table("user_strategies").update({"status": "active"}).eq("id", strategy_id).execute())

    return {"strategy_id": strategy_id, "results": results}
