import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from brokers.fyers_adapter import FyersAdapter
from core.audit import record_audit
from core.config import settings
from core.capabilities import CAP_MAP, FREE, Capabilities, resolve_capabilities_by_id
from core.db import async_supabase, get_supabase
from core.deps import get_current_user, require_admin, require_super_admin
from core.models import ADMIN_ROLES, role_satisfies
from core.models import AuditLogEntry, Exchange, InstrumentType, NormalizedOrder, OptionType, OrderSide, OrderType as OrderTypeEnum, ProductType, StrategyAssignment, TIER_ORDER, UserProfile, tier_satisfies
from core.security import decrypt_broker_credentials
from core.safe_query import async_safe_single, async_safe_execute, safe_single, safe_execute
from engine.gate import execute_order, get_mirror_recipients, scaled_qty
from strategies import get_strategy_catalog, get_strategy_tier, list_strategies

FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI") or settings.fyers_redirect_uri or "https://api.ai.trademetrix.tech/api/v1/brokers/fyers/callback"

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
    profiles = await async_safe_execute(
        supabase.table("profiles").select("id, email, full_name, is_admin, role, subscription_tier, created_at")
    ) or []

    all_assignments = await async_safe_execute(
        supabase.table("strategy_assignments").select("user_id").eq("active", True)
    ) or []

    count_map: dict[str, int] = {}
    for row in all_assignments:
        uid = row["user_id"]
        count_map[uid] = count_map.get(uid, 0) + 1

    tier_cache: dict[str, int] = {}
    result = []
    for p in profiles:
        uid = p["id"]
        if uid not in tier_cache:
            caps = await resolve_capabilities_by_id(uid)
            tier_cache[uid] = caps.max_active_strategies
        result.append({
            "id": uid,
            "email": p.get("email", ""),
            "full_name": p.get("full_name", ""),
            "is_admin": p.get("is_admin", False),
            "role": p.get("role", ""),
            "subscription_tier": p.get("subscription_tier", "free"),
            "active_assignments": count_map.get(uid, 0),
            "max_active_strategies": tier_cache[uid],
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

    data = await async_safe_execute(query) or []
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
    target_user = await async_safe_single(
        supabase.table("profiles").select("id, subscription_tier").eq("id", req.user_id)
    )
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    required_tier = get_strategy_tier(req.strategy_key)
    if not required_tier:
        raise HTTPException(status_code=500, detail="Strategy tier not found in catalog")

    target_caps = await resolve_capabilities_by_id(req.user_id)
    if not tier_satisfies(target_caps.tier, required_tier) and target_caps.tier != "super_admin":
        raise HTTPException(
            status_code=400,
            detail=f"User tier '{target_caps.tier}' is below required tier '{required_tier}' for strategy '{req.strategy_key}'. "
            f"User needs at least '{required_tier}' subscription.",
        )

    existing = await async_safe_single(
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

    limit = target_caps.max_active_strategies
    if limit > 0:
        current_active = await async_safe_execute(
            supabase.table("strategy_assignments")
            .select("id")
            .eq("user_id", req.user_id)
            .eq("active", True)
        ) or []
        if len(current_active) >= limit:
            raise HTTPException(
                status_code=400,
                detail=f"{target_caps.tier} tier allows {limit} active strategies; unassign one first",
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
    existing = await async_safe_single(
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
# Maps legacy tier names to new subscription tiers for capability resolution
LEGACY_TIER_TO_SUB: dict[str, str] = {
    "free": "",
    "starter": "monthly",
    "pro": "halfyearly",
    "enterprise": "yearly",
}


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
    target = await async_safe_single(
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
        stale = await async_safe_execute(
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

        mapped_sub = LEGACY_TIER_TO_SUB.get(tier, "")
        new_caps = CAP_MAP.get(mapped_sub, FREE) if mapped_sub else FREE
        new_limit = new_caps.max_active_strategies
        remaining = await async_safe_execute(
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
    creds = await async_safe_execute(
        supabase.table("broker_credentials")
        .select("id, user_id, broker, is_active, encrypted_access_token, created_at, updated_at")
        .order("created_at", desc=True)
    ) or []

    user_ids = list(set(c["user_id"] for c in creds))
    if not user_ids:
        return {"brokers": []}

    profiles = await async_safe_execute(
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

    data = await async_safe_execute(query.limit(limit).offset(offset)) or []

    user_ids = list(set(o["user_id"] for o in data if o.get("user_id")))
    profile_map = {}
    if user_ids:
        profiles = await async_safe_execute(
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

    data = await async_safe_execute(query.limit(limit).offset(offset)) or []
    return {"entries": data, "count": len(data)}


@router.get("/stats")
async def admin_stats(admin: UserProfile = Depends(require_admin)):
    supabase = get_supabase()
    profiles = await async_safe_execute(
        supabase.table("profiles").select("id, is_admin, subscription_tier, created_at")
    ) or []

    total_users = len(profiles)
    total_admins = sum(1 for p in profiles if p.get("is_admin"))
    tier_counts: dict[str, int] = {}
    for p in profiles:
        uid = p["id"]
        try:
            caps = await resolve_capabilities_by_id(uid) if "id" in p else FREE
            t = caps.tier
        except Exception:
            t = p.get("subscription_tier", "free")
        tier_counts[t] = tier_counts.get(t, 0) + 1

    assignments = await async_safe_execute(
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
    settings = await async_safe_execute(
        supabase.table("risk_settings").select("*")
    ) or []

    user_ids = list(set(s["user_id"] for s in settings))
    profile_map = {}
    if user_ids:
        profiles = await async_safe_execute(
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
    total = await async_safe_execute(
        supabase.table("broker_credentials").select("id").eq("is_active", True)
    ) or []
    oauthed = await async_safe_execute(
        supabase.table("broker_credentials").select("id").neq("encrypted_access_token", "")
    ) or []
    return {
        "active_broker_count": len(total),
        "oauthed_count": len(oauthed),
    }


@router.post("/brokers/fyers/validate")
async def admin_validate_fyers_tokens(admin: UserProfile = Depends(require_admin)):
    supabase = get_supabase()
    creds = await async_safe_execute(
        supabase.table("broker_credentials")
        .select("id, user_id, encrypted_access_token, encrypted_api_key")
        .eq("broker", "fyers")
    ) or []

    user_ids = list(set(c["user_id"] for c in creds))
    profile_map = {}
    if user_ids:
        profiles = await async_safe_execute(
            supabase.table("profiles").select("id, email, full_name").in_("id", user_ids)
        ) or []
        profile_map = {p["id"]: p for p in profiles}

    results = []
    for c in creds:
        p = profile_map.get(c["user_id"], {})
        token_raw = c.get("encrypted_access_token", "") or ""
        if not token_raw:
            results.append({"id": c["id"], "user_id": c["user_id"], "email": p.get("email", ""), "full_name": p.get("full_name", ""), "has_token": False, "valid": False, "error": "no_token"})
            continue
        try:
            raw_token = decrypt_broker_credentials(token_raw)
            raw_client_id = decrypt_broker_credentials(c["encrypted_api_key"]) if c.get("encrypted_api_key") else ""
            adapter = FyersAdapter()
            await adapter.authenticate({"client_id": raw_client_id, "access_token": raw_token})
            funds = await adapter.get_funds()
            valid = funds.total_margin is not None
            results.append({"id": c["id"], "user_id": c["user_id"], "email": p.get("email", ""), "full_name": p.get("full_name", ""), "has_token": True, "valid": valid, "error": ""})
        except Exception as e:
            results.append({"id": c["id"], "user_id": c["user_id"], "email": p.get("email", ""), "full_name": p.get("full_name", ""), "has_token": True, "valid": False, "error": str(e)[:200]})

    return {"results": results}


@router.post("/brokers/fyers/re-auth/{credential_id}")
async def admin_fyers_re_auth(credential_id: str, admin: UserProfile = Depends(require_admin)):
    supabase = get_supabase()
    cred = await async_safe_single(
        supabase.table("broker_credentials").select("id, user_id, encrypted_api_key").eq("id", credential_id).eq("broker", "fyers")
    )
    if not cred:
        raise HTTPException(status_code=404, detail="Fyers credential not found")
    client_id = decrypt_broker_credentials(cred["encrypted_api_key"])
    await async_supabase(lambda: supabase.table("broker_credentials").update(
        {"is_active": False, "encrypted_access_token": ""}
    ).eq("id", credential_id).execute())
    record_audit(AuditLogEntry(
        user_id=admin.id,
        action="fyers_re_auth",
        resource="broker_credentials",
        resource_id=credential_id,
        details={"target_user_id": cred["user_id"]},
    ))
    auth_url = (
        f"https://api-t1.fyers.in/api/v3/generate-authcode"
        f"?client_id={client_id}"
        f"&redirect_uri={FYERS_REDIRECT_URI}"
        f"&response_type=code"
        f"&state={cred['user_id']}"
    )
    return {"auth_url": auth_url, "user_id": cred["user_id"]}


class SetAdminRoleRequest(BaseModel):
    email: str
    role: str


class UpdateAdminRoleRequest(BaseModel):
    role: str


@router.get("/admins")
async def admin_list_admins(admin: UserProfile = Depends(require_admin)):
    supabase = get_supabase()
    profiles = await async_safe_execute(
        supabase.table("profiles").select("id, email, full_name, is_admin, role, created_at")
        .or_("is_admin.eq.true,role.gte." + "a")
    ) or []
    result = []
    for p in profiles:
        p.pop("created_at", None)
        result.append(p)
    return {"admins": result}


@router.post("/admins", status_code=201)
async def admin_create_admin(
    req: SetAdminRoleRequest,
    admin: UserProfile = Depends(require_super_admin),
):
    if req.role not in ADMIN_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(ADMIN_ROLES)}")

    supabase = get_supabase()
    profile = await async_safe_single(
        supabase.table("profiles").select("id, email, is_admin, role").eq("email", req.email)
    )
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")

    supabase.table("profiles").update({
        "is_admin": True,
        "role": req.role,
    }).eq("id", profile["id"]).execute()

    record_audit(AuditLogEntry(
        user_id=admin.id,
        action="admin_create",
        resource="admin",
        details={"target_email": req.email, "role": req.role},
    ))

    return {"message": f"User promoted to {req.role}"}


@router.patch("/admins/{user_id}")
async def admin_update_role(
    user_id: str,
    req: UpdateAdminRoleRequest,
    admin: UserProfile = Depends(require_super_admin),
):
    if req.role not in ADMIN_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(ADMIN_ROLES)}")

    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot change your own role")

    supabase = get_supabase()
    profile = await async_safe_single(
        supabase.table("profiles").select("id, is_admin, role").eq("id", user_id)
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Admin user not found")
    if profile["role"] == "super_admin":
        raise HTTPException(status_code=400, detail="Cannot modify a super admin")

    supabase.table("profiles").update({
        "is_admin": req.role in ADMIN_ROLES,
        "role": req.role,
    }).eq("id", user_id).execute()

    record_audit(AuditLogEntry(
        user_id=admin.id,
        action="admin_update_role",
        resource="admin",
        details={"target_user": user_id, "new_role": req.role},
    ))

    return {"message": f"Role updated to {req.role}"}


@router.delete("/admins/{user_id}")
async def admin_remove_admin(
    user_id: str,
    admin: UserProfile = Depends(require_super_admin),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot remove yourself")

    supabase = get_supabase()
    profile = await async_safe_single(
        supabase.table("profiles").select("id, role").eq("id", user_id)
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Admin user not found")
    if profile["role"] == "super_admin":
        raise HTTPException(status_code=400, detail="Cannot remove a super admin")

    supabase.table("profiles").update({
        "is_admin": False,
        "role": "",
    }).eq("id", user_id).execute()

    record_audit(AuditLogEntry(
        user_id=admin.id,
        action="admin_remove",
        resource="admin",
        details={"target_user": user_id},
    ))

    return {"message": "Admin access removed"}
