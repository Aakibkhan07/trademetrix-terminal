import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.audit import record_audit
from core.db import async_supabase, get_supabase
from core.deps import get_current_user, require_admin
from core.models import AuditLogEntry, Exchange, InstrumentType, NormalizedOrder, OptionType, OrderSide, OrderType as OrderTypeEnum, ProductType, StrategyAssignment, TIER_LIMITS, TIER_ORDER, UserProfile, tier_satisfies
from core.security import decrypt_broker_credentials
from core.safe_query import safe_execute, safe_single
from engine.gate import execute_order, get_mirror_recipients, scaled_qty
from strategies import get_strategy_catalog, get_strategy_tier, list_strategies

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class AssignRequest(BaseModel):
    user_id: str
    strategy_key: str


class AssignResponse(BaseModel):
    id: str
    user_id: str
    strategy_key: str
    required_tier: str
    message: str


@router.get("/users")
async def admin_list_users(admin: UserProfile = Depends(require_admin)):
    supabase = get_supabase()
    profiles = safe_execute(
        supabase.table("profiles").select("id, email, full_name, is_admin, subscription_tier, created_at")
    ) or []

    all_assignments = safe_execute(
        supabase.table("strategy_assignments").select("user_id").eq("active", True)
    ) or []

    count_map: dict[str, int] = {}
    for row in all_assignments:
        uid = row["user_id"]
        count_map[uid] = count_map.get(uid, 0) + 1

    result = []
    for p in profiles:
        tier = p.get("subscription_tier", "free")
        result.append({
            "id": p["id"],
            "email": p.get("email", ""),
            "full_name": p.get("full_name", ""),
            "is_admin": p.get("is_admin", False),
            "subscription_tier": tier,
            "active_assignments": count_map.get(p["id"], 0),
            "max_active_strategies": TIER_LIMITS.get(tier, 99),
        })

    return {"users": result}


@router.get("/assignments")
async def admin_list_assignments(
    user_id: str = Query(""),
    admin: UserProfile = Depends(require_admin),
):
    supabase = get_supabase()
    query = supabase.table("strategy_assignments").select("*").order("created_at", desc=True)
    if user_id:
        query = query.eq("user_id", user_id)

    data = safe_execute(query) or []
    return {"assignments": data}


@router.post("/assignments", status_code=201)
async def admin_assign_strategy(
    req: AssignRequest,
    admin: UserProfile = Depends(require_admin),
):
    if req.strategy_key not in list_strategies():
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy_key '{req.strategy_key}'. Valid keys: {', '.join(list_strategies())}",
        )

    supabase = get_supabase()
    target_user = safe_single(
        supabase.table("profiles").select("id, subscription_tier").eq("id", req.user_id)
    )
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    required_tier = get_strategy_tier(req.strategy_key)
    if not required_tier:
        raise HTTPException(status_code=500, detail="Strategy tier not found in catalog")

    user_tier = target_user.get("subscription_tier", "free")
    if not tier_satisfies(user_tier, required_tier):
        raise HTTPException(
            status_code=400,
            detail=f"User tier '{user_tier}' is below required tier '{required_tier}' for strategy '{req.strategy_key}'. "
            f"User needs at least '{required_tier}' subscription.",
        )

    existing = safe_single(
        supabase.table("strategy_assignments")
        .select("*")
        .eq("user_id", req.user_id)
        .eq("strategy_key", req.strategy_key)
    )
    if existing and existing.get("active"):
        return AssignResponse(
            id=existing["id"],
            user_id=req.user_id,
            strategy_key=req.strategy_key,
            required_tier=required_tier,
            message="Already assigned and active (no-op)",
        )

    limit = TIER_LIMITS.get(user_tier, 0)
    if limit > 0:
        current_active = safe_execute(
            supabase.table("strategy_assignments")
            .select("id")
            .eq("user_id", req.user_id)
            .eq("active", True)
        ) or []
        if len(current_active) >= limit:
            raise HTTPException(
                status_code=400,
                detail=f"{user_tier} tier allows {limit} active strategies; unassign one first",
            )

    if existing:
        await async_supabase(lambda: supabase.table("strategy_assignments").update({"active": True, "assigned_by": admin.id}).eq(
            "id", existing["id"]
        ).execute())
        record_audit(AuditLogEntry(
            user_id=admin.id,
            action="reassign_strategy",
            resource="strategy_assignments",
            resource_id=existing["id"],
            details={"target_user_id": req.user_id, "strategy_key": req.strategy_key, "required_tier": required_tier},
        ))
        return AssignResponse(
            id=existing["id"],
            user_id=req.user_id,
            strategy_key=req.strategy_key,
            required_tier=required_tier,
            message="Reassigned (reactivated)",
        )

    insert_data = {
        "user_id": req.user_id,
        "strategy_key": req.strategy_key,
        "required_tier": required_tier,
        "assigned_by": admin.id,
    }
    result = await async_supabase(lambda: supabase.table("strategy_assignments").insert(insert_data).execute())
    new_id = result.data[0]["id"]

    record_audit(AuditLogEntry(
        user_id=admin.id,
        action="assign_strategy",
        resource="strategy_assignments",
        resource_id=new_id,
        details={"target_user_id": req.user_id, "strategy_key": req.strategy_key, "required_tier": required_tier},
    ))

    return AssignResponse(
        id=new_id,
        user_id=req.user_id,
        strategy_key=req.strategy_key,
        required_tier=required_tier,
        message="Strategy assigned",
    )


@router.delete("/assignments/{assignment_id}")
async def admin_unassign_strategy(
    assignment_id: str,
    admin: UserProfile = Depends(require_admin),
):
    supabase = get_supabase()
    existing = safe_single(
        supabase.table("strategy_assignments").select("*").eq("id", assignment_id)
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Assignment not found")

    await async_supabase(lambda: supabase.table("strategy_assignments").update({"active": False}).eq("id", assignment_id).execute())

    record_audit(AuditLogEntry(
        user_id=admin.id,
        action="unassign_strategy",
        resource="strategy_assignments",
        resource_id=assignment_id,
        details={"target_user_id": existing["user_id"], "strategy_key": existing["strategy_key"]},
    ))

    return {"message": "Strategy unassigned (deactivated)"}


class UpdateTierRequest(BaseModel):
    subscription_tier: str


ALLOWED_TIERS = {"free", "starter", "pro", "enterprise"}


@router.patch("/users/{user_id}")
async def admin_update_user_tier(
    user_id: str,
    req: UpdateTierRequest,
    admin: UserProfile = Depends(require_admin),
):
    tier = req.subscription_tier
    if tier not in ALLOWED_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier '{tier}'. Allowed: {', '.join(sorted(ALLOWED_TIERS))}",
        )

    supabase = get_supabase()
    target = safe_single(
        supabase.table("profiles").select("*").eq("id", user_id)
    )
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    old_tier = target.get("subscription_tier", "free")
    if old_tier == tier:
        return {
            "id": target["id"],
            "email": target.get("email", ""),
            "full_name": target.get("full_name", ""),
            "subscription_tier": tier,
            "message": "No change (already at this tier)",
        }

    await async_supabase(lambda: supabase.table("profiles").update({"subscription_tier": tier}).eq("id", user_id).execute())

    old_rank = TIER_ORDER.get(old_tier, 0)
    new_rank = TIER_ORDER.get(tier, 0)
    deactivated_count = 0
    if new_rank < old_rank:
        stale = safe_execute(
            supabase.table("strategy_assignments")
            .select("id, strategy_key, required_tier")
            .eq("user_id", user_id)
            .eq("active", True)
        ) or []
        deactivate_ids = []
        for a in stale:
            req_rank = TIER_ORDER.get(a.get("required_tier", "free"), 99)
            if req_rank > new_rank:
                deactivate_ids.append(a["id"])
        if deactivate_ids:
            await async_supabase(lambda: supabase.table("strategy_assignments").update({"active": False}).in_("id", deactivate_ids).execute())
            deactivated_count = len(deactivate_ids)

        new_limit = TIER_LIMITS.get(tier, 99)
        remaining = safe_execute(
            supabase.table("strategy_assignments")
            .select("id, created_at")
            .eq("user_id", user_id)
            .eq("active", True)
            .order("created_at", desc=True)
        ) or []
        if len(remaining) > new_limit:
            excess_ids = [a["id"] for a in remaining[new_limit:]]
            await async_supabase(lambda: supabase.table("strategy_assignments").update({"active": False}).in_("id", excess_ids).execute())
            deactivated_count += len(excess_ids)
            logger.info(
                "Deactivated %d excess strategies on tier downgrade user=%s %s->%s (limit %d)",
                len(excess_ids), user_id, old_tier, tier, new_limit,
            )

    record_audit(AuditLogEntry(
        user_id=admin.id,
        action="update_user_tier",
        resource="profiles",
        resource_id=user_id,
        details={
            "old_tier": old_tier,
            "new_tier": tier,
            "deactivated_assignments": deactivated_count,
        },
    ))

    return {
        "id": target["id"],
        "email": target.get("email", ""),
        "full_name": target.get("full_name", ""),
        "subscription_tier": tier,
        "is_admin": target.get("is_admin", False),
        "created_at": target.get("created_at", ""),
        "message": f"Tier updated from '{old_tier}' to '{tier}'",
        "deactivated_assignments": deactivated_count,
    }


class BroadcastRequest(BaseModel):
    strategy_key: str
    symbol: str
    action: str
    quantity: int
    price: float = 0.0
    exchange: str = "NSE"
    order_type: str = "MARKET"
    product: str = "INTRADAY"
    reason: str = ""
    paper: bool = True


@router.get("/broadcast/recipients")
async def admin_broadcast_recipients(
    strategy_key: str = Query(""),
    admin: UserProfile = Depends(require_admin),
):
    if not strategy_key:
        return {"recipients": []}
    recipients = await get_mirror_recipients(strategy_key)
    return {"recipients": recipients}


@router.post("/broadcast")
async def admin_broadcast(
    req: BroadcastRequest,
    admin: UserProfile = Depends(require_admin),
):
    if req.strategy_key not in list_strategies():
        raise HTTPException(status_code=400, detail=f"Unknown strategy_key '{req.strategy_key}'")

    recipients = await get_mirror_recipients(req.strategy_key)
    if not recipients:
        return {"results": [], "count": 0, "paper": req.paper, "message": "No recipients found for this strategy"}

    action = req.action.upper()
    side = OrderSide.BUY if action in ("BUY", "LONG") else OrderSide.SELL
    source = "broadcast_paper" if req.paper else "broadcast_live"

    results = []
    for r in recipients:
        uid = r["user_id"]
        try:
            scaled = scaled_qty(uid, req.quantity, req.price)
            broadcast_reason = f"{req.reason} [strategy:{req.strategy_key}]" if req.reason else f"[strategy:{req.strategy_key}]"
            order = NormalizedOrder(
                symbol=req.symbol,
                exchange=Exchange(req.exchange),
                side=side,
                order_type=OrderTypeEnum(req.order_type),
                product=ProductType(req.product),
                quantity=scaled,
                price=req.price if req.price else 0.0,
                reason=broadcast_reason,
            )
            result = await execute_order(uid, order, source=source)
            results.append({
                "user_id": uid,
                "email": r.get("email", ""),
                "full_name": r.get("full_name", ""),
                "success": result.success,
                "broker_order_id": result.broker_order_id,
                "message": result.message,
                "status": result.status,
            })
        except Exception as e:
            logger.error("Broadcast execution error for user=%s: %s", uid, e)
            results.append({
                "user_id": uid,
                "email": r.get("email", ""),
                "full_name": r.get("full_name", ""),
                "success": False,
                "message": str(e),
                "status": "error",
            })

    return {"results": results, "count": len(results), "paper": req.paper}


@router.get("/brokers")
async def admin_list_brokers(admin: UserProfile = Depends(require_admin)):
    supabase = get_supabase()
    creds = safe_execute(
        supabase.table("broker_credentials")
        .select("id, user_id, broker, is_active, encrypted_access_token, created_at, updated_at")
        .order("created_at", desc=True)
    ) or []

    user_ids = list(set(c["user_id"] for c in creds))
    if not user_ids:
        return {"brokers": []}

    profiles = safe_execute(
        supabase.table("profiles")
        .select("id, email, full_name, is_admin")
        .in_("id", user_ids)
    ) or []
    profile_map = {p["id"]: p for p in profiles}

    result = []
    for c in creds:
        p = profile_map.get(c["user_id"], {})
        has_token = bool(c.get("encrypted_access_token"))
        result.append({
            "id": c["id"],
            "user_id": c["user_id"],
            "email": p.get("email", ""),
            "full_name": p.get("full_name", ""),
            "broker": c["broker"],
            "is_active": c.get("is_active", False),
            "has_access_token": has_token,
            "created_at": c.get("created_at", ""),
            "updated_at": c.get("updated_at", ""),
        })

    return {"brokers": result}


@router.get("/orders")
async def admin_list_orders(
    user_id: str = Query(""),
    is_paper: str = Query(""),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    admin: UserProfile = Depends(require_admin),
):
    supabase = get_supabase()
    query = supabase.table("orders").select("*").order("created_at", desc=True)
    if user_id:
        query = query.eq("user_id", user_id)
    if is_paper in ("true", "false"):
        query = query.eq("is_paper", is_paper == "true")

    data = safe_execute(query.limit(limit).offset(offset)) or []

    user_ids = list(set(o["user_id"] for o in data if o.get("user_id")))
    profile_map = {}
    if user_ids:
        profiles = safe_execute(
            supabase.table("profiles").select("id, email, full_name").in_("id", user_ids)
        ) or []
        profile_map = {p["id"]: p for p in profiles}

    orders = []
    for o in data:
        p = profile_map.get(o.get("user_id", ""), {})
        orders.append({
            "id": o.get("id", ""),
            "user_id": o.get("user_id", ""),
            "email": p.get("email", ""),
            "full_name": p.get("full_name", ""),
            "broker": o.get("broker", ""),
            "broker_order_id": o.get("broker_order_id", ""),
            "symbol": o.get("symbol", ""),
            "exchange": o.get("exchange", ""),
            "side": o.get("side", ""),
            "order_type": o.get("order_type", ""),
            "product": o.get("product", ""),
            "quantity": o.get("quantity", 0),
            "price": o.get("price", 0.0),
            "status": o.get("status", ""),
            "is_paper": o.get("is_paper", True),
            "message": o.get("message", ""),
            "filled_quantity": o.get("filled_quantity", 0),
            "filled_at": o.get("filled_at", ""),
            "created_at": o.get("created_at", ""),
        })

    return {"orders": orders, "count": len(orders)}


@router.get("/audit-log")
async def admin_audit_log(
    user_id: str = Query(""),
    action: str = Query(""),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    admin: UserProfile = Depends(require_admin),
):
    supabase = get_supabase()
    query = supabase.table("audit_log").select("*").order("created_at", desc=True)
    if user_id:
        query = query.eq("user_id", user_id)
    if action:
        query = query.eq("action", action)

    data = safe_execute(query.limit(limit).offset(offset)) or []
    return {"entries": data, "count": len(data)}


@router.get("/stats")
async def admin_stats(admin: UserProfile = Depends(require_admin)):
    supabase = get_supabase()
    profiles = safe_execute(
        supabase.table("profiles").select("id, is_admin, subscription_tier, created_at")
    ) or []

    total_users = len(profiles)
    total_admins = sum(1 for p in profiles if p.get("is_admin"))
    tier_counts: dict[str, int] = {}
    for p in profiles:
        t = p.get("subscription_tier", "free")
        tier_counts[t] = tier_counts.get(t, 0) + 1

    assignments = safe_execute(
        supabase.table("strategy_assignments").select("id").eq("active", True)
    ) or []
    active_assignments = len(assignments)

    catalog_count = len(get_strategy_catalog())

    return {
        "total_users": total_users,
        "total_admins": total_admins,
        "active_assignments": active_assignments,
        "total_strategies": catalog_count,
        "tier_distribution": tier_counts,
    }


@router.get("/risk")
async def admin_risk_overview(admin: UserProfile = Depends(require_admin)):
    supabase = get_supabase()
    settings = safe_execute(
        supabase.table("risk_settings").select("*")
    ) or []

    user_ids = list(set(s["user_id"] for s in settings))
    profile_map = {}
    if user_ids:
        profiles = safe_execute(
            supabase.table("profiles").select("id, email, full_name").in_("id", user_ids)
        ) or []
        profile_map = {p["id"]: p for p in profiles}

    result = []
    for s in settings:
        p = profile_map.get(s["user_id"], {})
        result.append({
            "user_id": s["user_id"],
            "email": p.get("email", ""),
            "full_name": p.get("full_name", ""),
            "max_capital": s.get("max_capital", 0.0),
            "max_position_size": s.get("max_position_size", 0.0),
            "max_open_positions": s.get("max_open_positions", 10),
            "max_daily_loss": s.get("max_daily_loss", 0.0),
            "max_drawdown_pct": s.get("max_drawdown_pct", 0.0),
            "kill_switch_enabled": s.get("kill_switch_enabled", False),
            "is_live": s.get("is_live", False),
            "strategy_id": s.get("strategy_id", ""),
        })

    return {"settings": result, "count": len(result)}


@router.get("/active-brokers")
async def admin_active_brokers_count(admin: UserProfile = Depends(require_admin)):
    supabase = get_supabase()
    total = safe_execute(
        supabase.table("broker_credentials").select("id").eq("is_active", True)
    ) or []
    oauthed = safe_execute(
        supabase.table("broker_credentials").select("id").neq("encrypted_access_token", "")
    ) or []
    return {
        "active_broker_count": len(total),
        "oauthed_count": len(oauthed),
    }
