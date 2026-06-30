from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.audit import record_audit
from core.db import get_supabase
from core.deps import get_current_user
from core.models import AuditLogEntry, TIER_LIMITS, UserProfile
from core.safe_query import safe_execute
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


@router.get("/assigned")
async def get_assigned_strategies(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    data = safe_execute(
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
        "max_active_strategies": TIER_LIMITS.get(current_user.subscription_tier, 99),
    }


@router.get("/")
async def get_strategies(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    result = supabase.table("strategies").select("*").eq("user_id", current_user.id).execute()
    return {"strategies": result.data or []}


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
    result = supabase.table("strategies").insert(data).execute()

    record_audit(AuditLogEntry(
        user_id=current_user.id,
        action="create_strategy",
        resource="strategies",
        resource_id=result.data[0]["id"],
    ))

    return result.data[0]


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

    supabase.table("strategies").update(updates).eq("id", strategy_id).eq("user_id", current_user.id).execute()
    return {"message": "Strategy updated"}


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    supabase = get_supabase()
    supabase.table("strategies").delete().eq("id", strategy_id).eq("user_id", current_user.id).execute()
