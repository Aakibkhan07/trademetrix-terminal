from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.audit import record_audit
from core.db import get_supabase
from core.capabilities import Capabilities
from core.deps import get_capabilities, get_current_user
from core.models import AuditLogEntry, UserProfile
from core.safe_query import async_safe_single, async_safe_execute, safe_single, safe_execute
from strategies import list_strategies

router = APIRouter(prefix="/strategies", tags=["strategies"])


class CreateStrategyRequest(BaseModel):
    name: str
    type: str = "builtin"
    config: dict = {}


class UpdateStrategyRequest(BaseModel):
    name: str | None = None
    config: dict | None = None
    is_active: bool | None = None


@router.get("/list-builtin")
async def list_builtin():
    from strategies import get_strategy_catalog
    return {"strategies": [s.model_dump() for s in get_strategy_catalog()]}


@router.get("/marketplace")
async def get_marketplace():
    from strategies import get_strategy_catalog, get_strategy_category
    supabase = get_supabase()
    catalog = get_strategy_catalog()

    assignments = await async_safe_execute(
        supabase.table("strategy_assignments").select("strategy_key").eq("active", True)
    ) or []
    user_counts: dict[str, int] = {}
    for row in assignments:
        key = row["strategy_key"]
        user_counts[key] = user_counts.get(key, 0) + 1

    srows = await async_safe_execute(supabase.table("strategies").select("id, type")) or []
    all_ids = [s["id"] for s in srows]
    type_by_id: dict[str, str] = {s["id"]: s.get("type", "") for s in srows}

    strategy_types = set(list_strategies())
    all_orders_data = await async_safe_execute(
        supabase.table("orders").select("status, filled_quantity, average_price, strategy_id").in_("strategy_id", all_ids)
    ) or [] if all_ids else []

    perf_by_key: dict[str, dict] = {}
    for type_key in strategy_types:
        type_ids = {sid for sid, t in type_by_id.items() if t == type_key}
        if not type_ids:
            continue
        type_orders = [o for o in all_orders_data if o.get("strategy_id") in type_ids]
        total_trades = len(type_orders)
        filled = [o for o in type_orders if o.get("status") == "FILLED" and o.get("filled_quantity", 0) > 0]
        wins = sum(1 for o in filled if o.get("average_price", 0) > 0)
        win_rate = round(wins / len(filled) * 100, 1) if filled else 0.0
        perf_by_key[type_key] = {
            "total_trades": total_trades,
            "total_pnl": 0.0,
            "win_rate": win_rate,
            "avg_return": 0.0,
        }

    result = []
    for s in catalog:
        if s.key == "graph_strategy":
            continue
        m = perf_by_key.get(s.key, {})
        result.append({
            **s.model_dump(),
            "category": get_strategy_category(s.key),
            "user_count": user_counts.get(s.key, 0),
            "total_trades": m.get("total_trades", 0),
            "total_pnl": m.get("total_pnl", 0.0),
            "win_rate": m.get("win_rate", 0.0),
            "avg_return": m.get("avg_return", 0.0),
        })
    return {"strategies": result}


@router.get("/{key}/detail")
async def get_strategy_detail(key: str):
    from strategies import get_strategy_catalog, get_strategy_category, get_strategy_tier
    catalog = get_strategy_catalog()
    info = next((s for s in catalog if s.key == key), None)
    if not info:
        raise HTTPException(status_code=404, detail="Strategy not found")

    supabase = get_supabase()

    assignment_rows = await async_safe_execute(
        supabase.table("strategy_assignments").select("id").eq("strategy_key", key).eq("active", True)
    ) or []
    user_count = len(assignment_rows)

    srows = await async_safe_execute(
        supabase.table("strategies").select("id").eq("type", key)
    ) or []
    ids = [s["id"] for s in srows]

    metrics = {"total_trades": 0, "total_pnl": 0.0, "win_rate": 0.0, "avg_return": 0.0}
    recent_trades = []

    if ids:
        orders_data = await async_safe_execute(
            supabase.table("orders")
            .select("*")
            .in_("strategy_id", ids)
            .order("created_at", desc=True)
            .limit(50)
        ) or []
        total_trades = len(orders_data)
        filled = [o for o in orders_data if o.get("status") == "FILLED" and o.get("filled_quantity", 0) > 0]
        wins = 0
        for o in filled:
            if o.get("average_price", 0) > 0:
                wins += 1
        win_rate = round(wins / len(filled) * 100, 1) if filled else 0.0
        metrics = {
            "total_trades": total_trades,
            "total_pnl": 0.0,
            "win_rate": win_rate,
            "avg_return": 0.0,
        }
        recent_trades = [
            {
                "id": o["id"],
                "symbol": o.get("symbol", ""),
                "side": o.get("side", ""),
                "quantity": o.get("quantity", 0),
                "price": o.get("price", 0),
                "status": o.get("status", ""),
                "filled_quantity": o.get("filled_quantity", 0),
                "average_price": o.get("average_price", 0),
                "is_paper": o.get("is_paper", True),
                "created_at": o.get("created_at", ""),
            }
            for o in orders_data[:20]
        ]

    return {
        **info.model_dump(),
        "category": get_strategy_category(key),
        "user_count": user_count,
        **metrics,
        "recent_trades": recent_trades,
    }


@router.get("/assigned")
async def get_assigned_strategies(
    current_user: UserProfile = Depends(get_current_user),
    caps: Capabilities = Depends(get_capabilities),
):
    supabase = get_supabase()
    data = await async_safe_execute(
        supabase.table("strategy_assignments")
        .select("strategy_key, mirror_enabled, required_tier")
        .eq("user_id", current_user.id)
        .eq("active", True)
    )
    from strategies import get_strategy_catalog
    catalog = {s.key: s for s in get_strategy_catalog()}
    result = []
    for row in data or []:
        key = row["strategy_key"]
        info = catalog.get(key)
        result.append({
            "strategy_key": key,
            "name": info.name if info else key,
            "description": info.description if info else "",
            "mirror_enabled": row.get("mirror_enabled", True),
            "required_tier": row.get("required_tier", "free"),
        })
    return {
        "strategies": result,
        "active_count": len(result),
        "max_active_strategies": caps.max_active_strategies,
    }


@router.get("/")
async def get_strategies(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    result = await async_safe_execute(
        supabase.table("strategies").select("*").eq("user_id", current_user.id)
    )
    return {"strategies": result or []}


@router.post("/", status_code=201)
async def create_strategy(
    req: CreateStrategyRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    if req.type == "builtin" and req.config.get("type") not in list_strategies():
        raise HTTPException(status_code=400, detail="Unknown builtin strategy type")

    supabase = get_supabase()
    data = {
        "user_id": current_user.id,
        "name": req.name,
        "type": req.type,
        "config": req.config,
    }
    result = await async_safe_execute(supabase.table("strategies").insert(data))

    if result:
        record_audit(AuditLogEntry(
            user_id=current_user.id,
            action="create_strategy",
            resource="strategies",
            resource_id=result[0]["id"],
        ))

    return result[0] if result else {"error": "Failed to create strategy"}


@router.put("/{strategy_id}")
async def update_strategy(
    strategy_id: str,
    req: UpdateStrategyRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    updates = {k: v for k, v in req.model_dump(exclude_none=True).items()}
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    await async_safe_execute(
        supabase.table("strategies").update(updates).eq("id", strategy_id).eq("user_id", current_user.id)
    )
    return {"message": "Strategy updated"}


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    await async_safe_execute(supabase.table("strategies").delete().eq("id", strategy_id).eq("user_id", current_user.id))
