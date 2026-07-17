import logging
import os
from datetime import datetime
from typing import Any, cast

from fastapi import HTTPException

from brokers.fyers_adapter import FyersAdapter
from core.audit import record_audit
from core.config import settings
from core.capabilities import CAP_MAP, FREE, resolve_capabilities_by_id
from core.db import async_supabase, get_supabase
from core.models import ADMIN_ROLES, AuditLogEntry, Exchange, NormalizedOrder, OrderSide, OrderType as OrderTypeEnum, ProductType, TIER_ORDER, tier_satisfies
from core.safe_query import async_safe_execute, async_safe_single
from core.security import decrypt_broker_credentials
from engine.gate import execute_order, get_mirror_recipients, scaled_qty
from strategies import get_strategy_catalog, get_strategy_category, get_strategy_tier, list_strategies

FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI") or settings.fyers_redirect_uri or "https://api.ai.trademetrix.tech/api/v1/brokers/fyers/callback"

ALLOWED_TIERS = {"free", "starter", "pro", "enterprise"}
LEGACY_TIER_TO_SUB = {
    "free": "",
    "starter": "monthly",
    "pro": "halfyearly",
    "enterprise": "yearly",
}

logger = logging.getLogger(__name__)


class AdminService:

    async def list_users(self) -> dict:
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

    async def list_users_with_brokers(self) -> dict:
        supabase = get_supabase()
        profiles = await async_safe_execute(
            supabase.table("profiles").select("id, email, full_name, subscription_tier")
        ) or []
        brokers_raw = await async_safe_execute(
            supabase.table("broker_credentials").select("user_id, broker, is_active")
        ) or []
        broker_map: dict[str, list[dict]] = {}
        for b in brokers_raw:
            uid = b["user_id"]
            if uid not in broker_map:
                broker_map[uid] = []
            broker_map[uid].append({"broker": b["broker"], "active": b.get("is_active", False)})
        result = []
        for p in profiles:
            uid = p["id"]
            result.append({
                "id": uid,
                "email": p.get("email", ""),
                "full_name": p.get("full_name", ""),
                "subscription_tier": p.get("subscription_tier", "free"),
                "brokers": broker_map.get(uid, []),
                "has_broker": len(broker_map.get(uid, [])) > 0,
            })
        return {"users": result}

    async def list_assignments(self, user_id: str = "") -> dict:
        supabase = get_supabase()
        query = supabase.table("strategy_assignments").select("*").order("created_at", desc=True)
        if user_id:
            query = query.eq("user_id", user_id)
        data = await async_safe_execute(query) or []
        return {"assignments": data}

    async def assign_strategy(self, target_user_id: str, strategy_key: str, admin_id: str) -> dict:
        if strategy_key not in list_strategies():
            raise HTTPException(
                status_code=400,
                detail=f"Unknown strategy_key '{strategy_key}'. Valid keys: {', '.join(list_strategies())}",
            )

        supabase = get_supabase()
        target_user = await async_safe_single(
            supabase.table("profiles").select("id, subscription_tier").eq("id", target_user_id)
        )
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

        required_tier = get_strategy_tier(strategy_key)
        if not required_tier:
            raise HTTPException(status_code=500, detail="Strategy tier not found in catalog")

        target_caps = await resolve_capabilities_by_id(target_user_id)
        limit = target_caps.max_active_strategies
        if limit > 0:
            current_active = await async_safe_execute(
                supabase.table("strategy_assignments")
                .select("id")
                .eq("user_id", target_user_id)
                .eq("active", True)
            ) or []
            if len(current_active) >= limit:
                raise HTTPException(
                    status_code=400,
                    detail=f"{target_caps.tier} tier allows {limit} active strategies; unassign one first",
                )

        existing = await async_safe_single(
            supabase.table("strategy_assignments")
            .select("*")
            .eq("user_id", target_user_id)
            .eq("strategy_key", strategy_key)
            .eq("active", False)
        )
        if existing:
            await async_supabase(lambda: supabase.table("strategy_assignments").update({"active": True, "assigned_by": admin_id}).eq(
                "id", existing["id"]
            ).execute())
            record_audit(AuditLogEntry(
                user_id=admin_id,
                action="reassign_strategy",
                resource="strategy_assignments",
                resource_id=existing["id"],
                details={"target_user_id": target_user_id, "strategy_key": strategy_key, "required_tier": required_tier},
            ))
            return {
                "id": existing["id"],
                "user_id": target_user_id,
                "strategy_key": strategy_key,
                "required_tier": required_tier,
                "message": "Reassigned (reactivated)",
            }

        insert_data = {
            "user_id": target_user_id,
            "strategy_key": strategy_key,
            "required_tier": required_tier,
            "assigned_by": admin_id,
        }
        result = await async_supabase(lambda: supabase.table("strategy_assignments").insert(insert_data).execute())
        new_id: str = str(cast(dict[str, Any], result.data[0])["id"])

        record_audit(AuditLogEntry(
            user_id=admin_id,
            action="assign_strategy",
            resource="strategy_assignments",
            resource_id=new_id,
            details={"target_user_id": target_user_id, "strategy_key": strategy_key, "required_tier": required_tier},
        ))

        return {
            "id": new_id,
            "user_id": target_user_id,
            "strategy_key": strategy_key,
            "required_tier": required_tier,
            "message": "Strategy assigned",
        }

    async def unassign_strategy(self, assignment_id: str, admin_id: str) -> dict:
        supabase = get_supabase()
        existing = await async_safe_single(
            supabase.table("strategy_assignments").select("*").eq("id", assignment_id)
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Assignment not found")

        await async_supabase(lambda: supabase.table("strategy_assignments").update({"active": False}).eq("id", assignment_id).execute())

        record_audit(AuditLogEntry(
            user_id=admin_id,
            action="unassign_strategy",
            resource="strategy_assignments",
            resource_id=assignment_id,
            details={"target_user_id": existing["user_id"], "strategy_key": existing["strategy_key"]},
        ))

        return {"message": "Strategy unassigned (deactivated)"}

    async def update_user_tier(self, target_user_id: str, tier: str, admin_id: str) -> dict:
        if tier not in ALLOWED_TIERS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid tier '{tier}'. Allowed: {', '.join(sorted(ALLOWED_TIERS))}",
            )

        supabase = get_supabase()
        target = await async_safe_single(
            supabase.table("profiles").select("*").eq("id", target_user_id)
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

        await async_supabase(lambda: supabase.table("profiles").update({"subscription_tier": tier}).eq("id", target_user_id).execute())

        old_rank = TIER_ORDER.get(old_tier, 0)
        new_rank = TIER_ORDER.get(tier, 0)
        deactivated_count = 0
        if new_rank < old_rank:
            stale = await async_safe_execute(
                supabase.table("strategy_assignments")
                .select("id, strategy_key, required_tier")
                .eq("user_id", target_user_id)
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
                .eq("user_id", target_user_id)
                .eq("active", True)
                .order("created_at", desc=True)
            ) or []
            if len(remaining) > new_limit:
                excess_ids = [a["id"] for a in remaining[new_limit:]]
                await async_supabase(lambda: supabase.table("strategy_assignments").update({"active": False}).in_("id", excess_ids).execute())
                deactivated_count += len(excess_ids)
                logger.info(
                    "Deactivated %d excess strategies on tier downgrade user=%s %s->%s (limit %d)",
                    len(excess_ids), target_user_id, old_tier, tier, new_limit,
                )

        record_audit(AuditLogEntry(
            user_id=admin_id,
            action="update_user_tier",
            resource="profiles",
            resource_id=target_user_id,
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

    async def get_broadcast_recipients(self, strategy_key: str) -> dict:
        if not strategy_key:
            return {"recipients": []}
        recipients = await get_mirror_recipients(strategy_key)
        return {"recipients": recipients}

    async def broadcast(self, strategy_key: str, symbol: str, action: str, quantity: int, price: float, exchange: str, order_type: str, product: str, reason: str, paper: bool) -> dict:
        if strategy_key not in list_strategies():
            raise HTTPException(status_code=400, detail=f"Unknown strategy_key '{strategy_key}'")

        recipients = await get_mirror_recipients(strategy_key)
        if not recipients:
            return {"results": [], "count": 0, "paper": paper, "message": "No recipients found for this strategy"}

        action_upper = action.upper()
        side = OrderSide.BUY if action_upper in ("BUY", "LONG") else OrderSide.SELL
        source = "broadcast_paper" if paper else "broadcast_live"

        results = []
        for r in recipients:
            uid = r["user_id"]
            try:
                scaled = await scaled_qty(uid, quantity, price)
                broadcast_reason = f"{reason} [strategy:{strategy_key}]" if reason else f"[strategy:{strategy_key}]"
                order = NormalizedOrder(
                    symbol=symbol,
                    exchange=Exchange(exchange),
                    side=side,
                    order_type=OrderTypeEnum(order_type),
                    product=ProductType(product),
                    quantity=scaled,
                    price=price if price else 0.0,
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

        return {"results": results, "count": len(results), "paper": paper}

    async def notify_broadcast(self, title: str, message: str, notify_type: str, user_ids: list[str] | None, admin_id: str) -> dict:
        from core.notifications import send_alert_email, send_alert_sms
        supabase = get_supabase()
        if user_ids:
            users = await async_safe_execute(
                supabase.table("profiles").select("id, email, full_name, phone").in_("id", user_ids)
            ) or []
        else:
            users = await async_safe_execute(
                supabase.table("profiles").select("id, email, full_name, phone")
            ) or []
        results = []
        for u in users:
            email = u.get("email", "")
            phone = u.get("phone", "")
            sent = False
            try:
                if notify_type in ("email", "both") and email:
                    sent = await send_alert_email(email, title, message)
                if notify_type in ("sms", "both") and phone:
                    sent = await send_alert_sms(phone, f"{title}\n\n{message}") if sent else (await send_alert_sms(phone, f"{title}\n\n{message}") or sent)
                results.append({"user_id": u["id"], "email": email, "phone": phone, "sent": sent})
            except Exception as e:
                results.append({"user_id": u["id"], "email": email, "sent": False, "error": str(e)})
        success_count = sum(1 for r in results if r.get("sent"))
        await record_audit(admin_id, "broadcast_notify", "broadcast", {"type": notify_type, "recipients": len(users), "success": success_count})
        return {"results": results, "total": len(users), "success": success_count, "failed": len(users) - success_count}

    async def list_brokers(self) -> dict:
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

    async def list_orders(self, user_id: str = "", is_paper: str = "", symbol: str = "", from_date: str = "", to_date: str = "", limit: int = 50, offset: int = 0) -> dict:
        supabase = get_supabase()
        query = supabase.table("orders").select("*").order("created_at", desc=True)
        if user_id:
            query = query.eq("user_id", user_id)
        if is_paper in ("true", "false"):
            query = query.eq("is_paper", is_paper == "true")
        if symbol:
            query = query.ilike("symbol", f"%{symbol}%")
        if from_date:
            query = query.gte("created_at", from_date)
        if to_date:
            query = query.lte("created_at", to_date)

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
                "trigger_price": o.get("trigger_price"),
                "status": o.get("status", ""),
                "is_paper": o.get("is_paper", True),
                "message": o.get("message", ""),
                "filled_quantity": o.get("filled_quantity", 0),
                "average_price": o.get("average_price", 0.0),
                "instrument_type": o.get("instrument_type", "EQ"),
                "strike_price": o.get("strike_price"),
                "expiry_date": o.get("expiry_date"),
                "option_type": o.get("option_type", ""),
                "filled_at": o.get("filled_at", ""),
                "created_at": o.get("created_at", ""),
            })

        return {"orders": orders, "count": len(orders)}

    async def list_positions(self, user_id: str = "") -> dict:
        supabase = get_supabase()
        query = supabase.table("positions_snapshot").select("*").order("snapshot_at", desc=True)
        if user_id:
            query = query.eq("user_id", user_id)

        data = await async_safe_execute(query) or []

        seen: dict[str, dict] = {}
        for p in data:
            key = (p.get("user_id", ""), p.get("symbol", ""))
            if key not in seen:
                seen[key] = p

        user_ids = list(set(p["user_id"] for p in seen.values() if p.get("user_id")))
        profile_map = {}
        if user_ids:
            profiles = await async_safe_execute(
                supabase.table("profiles").select("id, email, full_name").in_("id", user_ids)
            ) or []
            profile_map = {p["id"]: p for p in profiles}

        positions = []
        for p in seen.values():
            prof = profile_map.get(p.get("user_id", ""), {})
            positions.append({
                "id": p.get("id", ""),
                "user_id": p.get("user_id", ""),
                "email": prof.get("email", ""),
                "full_name": prof.get("full_name", ""),
                "broker": p.get("broker", ""),
                "symbol": p.get("symbol", ""),
                "exchange": p.get("exchange", ""),
                "quantity": p.get("quantity", 0),
                "buy_quantity": p.get("buy_quantity", 0),
                "sell_quantity": p.get("sell_quantity", 0),
                "average_buy_price": p.get("average_buy_price", 0.0),
                "average_sell_price": p.get("average_sell_price", 0.0),
                "unrealised_pnl": p.get("unrealised_pnl", 0.0),
                "realised_pnl": p.get("realised_pnl", 0.0),
                "m2m": p.get("m2m", 0.0),
                "product": p.get("product", ""),
                "instrument_type": p.get("instrument_type", "EQ"),
                "strike_price": p.get("strike_price"),
                "expiry_date": p.get("expiry_date"),
                "option_type": p.get("option_type", ""),
                "snapshot_at": p.get("snapshot_at", ""),
            })

        return {"positions": positions, "count": len(positions)}

    async def get_audit_log(self, user_id: str = "", action: str = "", from_date: str = "", to_date: str = "", limit: int = 50, offset: int = 0) -> dict:
        supabase = get_supabase()
        query = supabase.table("audit_log").select("*").order("created_at", desc=True)
        if user_id:
            query = query.eq("user_id", user_id)
        if action:
            query = query.eq("action", action)
        if from_date:
            query = query.gte("created_at", from_date)
        if to_date:
            query = query.lte("created_at", to_date)
        data = await async_safe_execute(query.limit(limit).offset(offset)) or []
        return {"entries": data, "count": len(data)}

    async def get_strategy_performance(self) -> dict:
        supabase = get_supabase()
        catalog = get_strategy_catalog()
        assignments = await async_safe_execute(
            supabase.table("strategy_assignments").select("strategy_key, user_id").eq("active", True)
        ) or []
        strategy_users: dict[str, set[str]] = {}
        for a in assignments:
            sk = a.get("strategy_key", "")
            if sk not in strategy_users:
                strategy_users[sk] = set()
            strategy_users[sk].add(a.get("user_id", ""))

        runs = await async_safe_execute(
            supabase.table("strategy_runs").select("daily_pnl, total_pnl, mode, status, created_at")
        ) or []
        total_run_pnl = sum(r.get("total_pnl", 0) or 0 for r in runs)
        paper_runs = [r for r in runs if r.get("mode") == "PAPER"]
        live_runs = [r for r in runs if r.get("mode") == "LIVE"]
        active_runs = [r for r in runs if r.get("status") == "running"]

        filled_orders = await async_safe_execute(
            supabase.table("orders")
            .select("side, filled_quantity, average_price, status, is_paper, created_at")
            .eq("status", "FILLED")
            .limit(2000)
        ) or []
        total_trades = len(filled_orders)
        profitable = sum(1 for o in filled_orders if o.get("side") == "SELL" and o.get("filled_quantity", 0) > 0)
        win_rate = round((profitable / total_trades * 100) if total_trades > 0 else 0, 1)

        avg_return = 0
        if total_trades > 0:
            total_side_val = sum(
                (1 if o.get("side") == "SELL" else -1) * o.get("filled_quantity", 0) * o.get("average_price", 0)
                for o in filled_orders
            )
            avg_return = round(total_side_val / total_trades, 2)

        returns = [
            (1 if o.get("side") == "SELL" else -1) * o.get("filled_quantity", 0) * o.get("average_price", 0)
            for o in filled_orders if o.get("average_price", 0) > 0
        ]
        sharpe = 0
        if len(returns) > 1:
            mean_r = sum(returns) / len(returns)
            std_r = (sum((r - mean_r) ** 2 for r in returns) / len(returns)) ** 0.5
            sharpe = round(mean_r / std_r, 2) if std_r > 0 else 0

        results = []
        for s in catalog:
            sk = s.get("key", s.get("name", ""))
            users_assigned = len(strategy_users.get(sk, set()))
            paper_trades = sum(1 for o in filled_orders if o.get("is_paper"))
            live_trades = total_trades - paper_trades
            results.append({
                "key": sk,
                "name": s.get("name", sk),
                "tier": s.get("required_tier", "free"),
                "category": s.get("category", ""),
                "users_assigned": users_assigned,
                "total_trades": total_trades,
                "paper_trades": paper_trades,
                "live_trades": live_trades,
                "win_rate": win_rate,
                "avg_return": avg_return,
                "sharpe_ratio": sharpe,
                "total_pnl": total_run_pnl,
                "active_runs": len(active_runs),
                "paper_runs": len(paper_runs),
                "live_runs": len(live_runs),
            })

        return {
            "strategies": results,
            "summary": {
                "total_strategies": len(catalog),
                "total_trades": total_trades,
                "win_rate": win_rate,
                "avg_return": avg_return,
                "sharpe_ratio": sharpe,
                "total_pnl": round(total_run_pnl, 2),
            },
        }

    async def get_pnl_overview(self, user_id: str = "", period: str = "daily", from_date: str = "", to_date: str = "") -> dict:
        supabase = get_supabase()
        start = from_date or (datetime.utcnow().isoformat()[:10] if period == "daily" else "")
        end = to_date or datetime.utcnow().isoformat()[:10]

        q_pos = supabase.table("positions_snapshot").select("*")
        q_ord = supabase.table("orders").select("user_id, side, filled_quantity, average_price, filled_at, created_at, status, symbol, is_paper").eq("status", "FILLED")
        if user_id:
            q_pos = q_pos.eq("user_id", user_id)
            q_ord = q_ord.eq("user_id", user_id)
        if start:
            q_pos = q_pos.gte("snapshot_at", start)
            q_ord = q_ord.gte("filled_at", start) if start else q_ord
        if end:
            q_ord = q_ord.lte("filled_at", end)

        positions = await async_safe_execute(q_pos.order("snapshot_at", desc=True).limit(500)) or []
        orders = await async_safe_execute(q_ord.order("filled_at", desc=True).limit(1000)) or []

        total_realised = sum(p.get("realised_pnl", 0) or 0 for p in positions)
        total_unrealised = sum(p.get("unrealised_pnl", 0) or 0 for p in positions)
        total_m2m = sum(p.get("m2m", 0) or 0 for p in positions)
        open_positions = len([p for p in positions if p.get("quantity", 0) != 0])

        filled_buy = sum(o.get("filled_quantity", 0) * o.get("average_price", 0) for o in orders if o.get("side") == "BUY")
        filled_sell = sum(o.get("filled_quantity", 0) * o.get("average_price", 0) for o in orders if o.get("side") == "SELL")
        trading_pnl = filled_sell - filled_buy

        daily_groups: dict[str, dict] = {}
        for o in orders:
            day = (o.get("filled_at") or o.get("created_at") or "")[:10]
            if not day:
                continue
            if day not in daily_groups:
                daily_groups[day] = {"buy": 0, "sell": 0, "count": 0, "paper_count": 0}
            val = o.get("filled_quantity", 0) * o.get("average_price", 0)
            if o.get("side") == "BUY":
                daily_groups[day]["buy"] += val
            else:
                daily_groups[day]["sell"] += val
            daily_groups[day]["count"] += 1
            if o.get("is_paper"):
                daily_groups[day]["paper_count"] += 1

        daily_pnl = []
        for day in sorted(daily_groups.keys()):
            g = daily_groups[day]
            daily_pnl.append({"date": day, "pnl": round(g["sell"] - g["buy"], 2), "trades": g["count"], "paper_trades": g["paper_count"]})

        user_ids = list(set(p["user_id"] for p in positions) | set(o["user_id"] for o in orders))
        profile_map = {}
        if user_ids:
            profiles = await async_safe_execute(
                supabase.table("profiles").select("id, email, full_name").in_("id", user_ids)
            ) or []
            profile_map = {p["id"]: p for p in profiles}

        return {
            "summary": {
                "total_realised": round(total_realised, 2),
                "total_unrealised": round(total_unrealised, 2),
                "total_m2m": round(total_m2m, 2),
                "trading_pnl": round(trading_pnl, 2),
                "open_positions": open_positions,
                "filled_orders": len(orders),
            },
            "daily_pnl": daily_pnl,
            "users": [{"id": uid, "email": profile_map.get(uid, {}).get("email", ""), "full_name": profile_map.get(uid, {}).get("full_name", "")} for uid in user_ids],
        }

    async def get_stats(self) -> dict:
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

    async def get_risk_overview(self) -> dict:
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

    async def get_active_brokers_count(self) -> dict:
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

    async def validate_fyers_tokens(self) -> dict:
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

    async def fyers_re_auth(self, credential_id: str, admin_id: str) -> dict:
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
            user_id=admin_id,
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

    async def list_admins(self) -> dict:
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

    async def create_admin(self, email: str, role: str, admin_id: str) -> dict:
        if role not in ADMIN_ROLES:
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(ADMIN_ROLES)}")

        supabase = get_supabase()
        profile = await async_safe_single(
            supabase.table("profiles").select("id, email, is_admin, role").eq("email", email)
        )
        if not profile:
            raise HTTPException(status_code=404, detail="User not found")

        await async_supabase(lambda: supabase.table("profiles").update({
            "is_admin": True,
            "role": role,
        }).eq("id", profile["id"]).execute())

        record_audit(AuditLogEntry(
            user_id=admin_id,
            action="admin_create",
            resource="admin",
            details={"target_email": email, "role": role},
        ))

        return {"message": f"User promoted to {role}"}

    async def update_admin_role(self, target_user_id: str, role: str, admin_id: str) -> dict:
        if role not in ADMIN_ROLES:
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(ADMIN_ROLES)}")

        if target_user_id == admin_id:
            raise HTTPException(status_code=400, detail="You cannot change your own role")

        supabase = get_supabase()
        profile = await async_safe_single(
            supabase.table("profiles").select("id, is_admin, role").eq("id", target_user_id)
        )
        if not profile:
            raise HTTPException(status_code=404, detail="Admin user not found")
        if profile["role"] == "super_admin":
            raise HTTPException(status_code=400, detail="Cannot modify a super admin")

        await async_supabase(lambda: supabase.table("profiles").update({
            "is_admin": role in ADMIN_ROLES,
            "role": role,
        }).eq("id", target_user_id).execute())

        record_audit(AuditLogEntry(
            user_id=admin_id,
            action="admin_update_role",
            resource="admin",
            details={"target_user": target_user_id, "new_role": role},
        ))

        return {"message": f"Role updated to {role}"}

    async def remove_admin(self, target_user_id: str, admin_id: str) -> dict:
        if target_user_id == admin_id:
            raise HTTPException(status_code=400, detail="You cannot remove yourself")

        supabase = get_supabase()
        profile = await async_safe_single(
            supabase.table("profiles").select("id, role").eq("id", target_user_id)
        )
        if not profile:
            raise HTTPException(status_code=404, detail="Admin user not found")
        if profile["role"] == "super_admin":
            raise HTTPException(status_code=400, detail="Cannot remove a super admin")

        await async_supabase(lambda: supabase.table("profiles").update({
            "is_admin": False,
            "role": "",
        }).eq("id", target_user_id).execute())

        record_audit(AuditLogEntry(
            user_id=admin_id,
            action="admin_remove",
            resource="admin",
            details={"target_user": target_user_id},
        ))

        return {"message": "Admin access removed"}

    async def list_catalog_strategies(self) -> dict:
        supabase = get_supabase()
        db_entries = await async_safe_execute(
            supabase.table("strategy_catalog").select("*").eq("is_active", True).order("key")
        ) or []
        db_map = {e["key"]: e for e in db_entries}
        code_catalog = get_strategy_catalog()
        merged = []
        for info in code_catalog:
            db = db_map.pop(info.key, None)
            merged.append({
                "key": info.key,
                "name": db["name"] if db else info.name,
                "description": db["description"] if db else info.description,
                "required_tier": db["required_tier"] if db else info.required_tier,
                "category": db.get("category", get_strategy_category(info.key)) if db else get_strategy_category(info.key),
                "is_active": True,
                "db_id": db["id"] if db else None,
            })
        for key, db in db_map.items():
            merged.append({
                "key": key,
                "name": db["name"],
                "description": db["description"],
                "required_tier": db["required_tier"],
                "category": db.get("category", "trend"),
                "is_active": db.get("is_active", True),
                "db_id": db["id"],
            })
        return {"strategies": merged}

    async def create_catalog_strategy(self, key: str, name: str, description: str, required_tier: str, category: str, admin_id: str) -> dict:
        supabase = get_supabase()
        existing = await async_safe_single(
            supabase.table("strategy_catalog").select("id").eq("key", key)
        )
        if existing:
            raise HTTPException(status_code=409, detail=f"Strategy key '{key}' already exists")
        result = await async_supabase(lambda: supabase.table("strategy_catalog").insert({
            "key": key, "name": name, "description": description,
            "required_tier": required_tier, "category": category,
        }).execute())
        new_id = str(cast(dict[str, Any], result.data[0])["id"])
        record_audit(AuditLogEntry(
            user_id=admin_id, action="create_strategy", resource="strategy_catalog",
            resource_id=new_id, details={"key": key, "name": name, "tier": required_tier},
        ))
        return {"id": new_id, "key": key, "name": name, "message": "Strategy created"}

    async def update_catalog_strategy(self, key: str, updates: dict, admin_id: str) -> dict:
        supabase = get_supabase()
        existing = await async_safe_single(
            supabase.table("strategy_catalog").select("id, key").eq("key", key)
        )
        if not existing:
            raise HTTPException(status_code=404, detail=f"Strategy '{key}' not found in catalog")
        await async_supabase(lambda: supabase.table("strategy_catalog").update({
            **updates, "updated_at": "now()",
        }).eq("key", key).execute())
        record_audit(AuditLogEntry(
            user_id=admin_id, action="update_strategy", resource="strategy_catalog",
            resource_id=existing["id"], details={"key": key, "updates": updates},
        ))
        return {"key": key, "message": "Strategy updated"}

    async def delete_catalog_strategy(self, key: str, admin_id: str) -> dict:
        supabase = get_supabase()
        existing = await async_safe_single(
            supabase.table("strategy_catalog").select("id").eq("key", key)
        )
        if not existing:
            raise HTTPException(status_code=404, detail=f"Strategy '{key}' not found in catalog")
        await async_supabase(lambda: supabase.table("strategy_catalog").update({
            "is_active": False, "updated_at": "now()",
        }).eq("key", key).execute())
        record_audit(AuditLogEntry(
            user_id=admin_id, action="delete_strategy", resource="strategy_catalog",
            resource_id=existing["id"], details={"key": key},
        ))
        return {"message": f"Strategy '{key}' deactivated"}

    async def list_live_positions(self, user_id: str) -> dict:
        supabase = get_supabase()
        creds = await async_safe_execute(
            supabase.table("broker_credentials")
            .select("id, user_id, broker, encrypted_access_token, encrypted_api_key")
            .eq("user_id", user_id)
            .eq("is_active", True)
        ) or []
        if not creds:
            return {"positions": [], "count": 0, "message": "No active broker for this user"}

        from brokers.fyers_adapter import FyersAdapter
        from execution.broker_adapter import BrokerExecutionAdapter

        profile = await async_safe_single(
            supabase.table("profiles").select("email, full_name").eq("id", user_id)
        )
        all_positions = []
        for c in creds:
            try:
                token_raw = decrypt_broker_credentials(c["encrypted_access_token"]) if c.get("encrypted_access_token") else None
                api_key_raw = decrypt_broker_credentials(c["encrypted_api_key"]) if c.get("encrypted_api_key") else None
                if not token_raw or not api_key_raw:
                    continue
                if c["broker"] == "fyers":
                    adapter = FyersAdapter()
                    await adapter.authenticate({"client_id": api_key_raw, "access_token": token_raw})
                    raw_positions = await adapter.get_positions()
                    for p in raw_positions:
                        all_positions.append({
                            "user_id": user_id,
                            "email": (profile or {}).get("email", ""),
                            "full_name": (profile or {}).get("full_name", ""),
                            "broker": c["broker"],
                            "symbol": p.symbol,
                            "quantity": p.quantity,
                            "average_buy_price": p.average_buy_price,
                            "average_sell_price": p.average_sell_price,
                            "buy_quantity": p.quantity if p.quantity > 0 else 0,
                            "sell_quantity": abs(p.quantity) if p.quantity < 0 else 0,
                            "unrealised_pnl": p.unrealised_pnl,
                            "realised_pnl": p.realised_pnl,
                            "m2m": p.m2m,
                            "product": p.product.value if hasattr(p.product, 'value') else str(p.product),
                            "instrument_type": "EQ",
                            "snapshot_at": datetime.utcnow().isoformat(),
                        })
            except Exception as e:
                logger.error("Live positions fetch error for user=%s broker=%s: %s", user_id, c["broker"], e)
                continue
        return {"positions": all_positions, "count": len(all_positions), "source": "live"}

    async def export_assignments(self) -> dict:
        supabase = get_supabase()
        data = await async_safe_execute(
            supabase.table("strategy_assignments").select("id, user_id, strategy_key, required_tier, active, assigned_by, created_at").order("created_at", desc=True)
        ) or []
        user_ids = list(set(a["user_id"] for a in data))
        profiles = await async_safe_execute(
            supabase.table("profiles").select("id, email, full_name").in_("id", user_ids)
        ) or []
        profile_map = {p["id"]: p for p in profiles}
        result = []
        for a in data:
            p = profile_map.get(a.get("user_id", ""), {})
            result.append({
                "id": a["id"], "user_id": a["user_id"], "email": p.get("email", ""),
                "full_name": p.get("full_name", ""), "strategy_key": a["strategy_key"],
                "required_tier": a["required_tier"], "active": a["active"],
                "assigned_by": a["assigned_by"], "created_at": a.get("created_at", ""),
            })
        return {"assignments": result, "count": len(result)}

    async def import_assignments(self, entries: list[dict], admin_id: str) -> dict:
        supabase = get_supabase()
        created = 0
        skipped = 0
        errors = []
        for entry in entries:
            uid = entry.get("user_id", "")
            skey = entry.get("strategy_key", "")
            if not uid or not skey:
                skipped += 1
                continue
            if skey not in list_strategies():
                errors.append({"user_id": uid, "strategy_key": skey, "error": "Unknown strategy"})
                skipped += 1
                continue
            user = await async_safe_single(
                supabase.table("profiles").select("id").eq("id", uid)
            )
            if not user:
                errors.append({"user_id": uid, "strategy_key": skey, "error": "User not found"})
                skipped += 1
                continue
            existing = await async_safe_single(
                supabase.table("strategy_assignments")
                .select("id").eq("user_id", uid).eq("strategy_key", skey).eq("active", True)
            )
            if existing:
                skipped += 1
                continue
            try:
                await async_supabase(lambda: supabase.table("strategy_assignments").insert({
                    "user_id": uid, "strategy_key": skey,
                    "required_tier": get_strategy_tier(skey) or "free",
                    "assigned_by": admin_id,
                }).execute())
                created += 1
            except Exception as e:
                errors.append({"user_id": uid, "strategy_key": skey, "error": str(e)[:100]})
        return {"created": created, "skipped": skipped, "errors": errors}

    async def batch_assign(self, user_ids: list[str], strategy_key: str, admin_id: str) -> dict:
        if strategy_key not in list_strategies():
            raise HTTPException(status_code=400, detail=f"Unknown strategy '{strategy_key}'")
        supabase = get_supabase()
        created = 0
        skipped = 0
        for uid in user_ids:
            existing = await async_safe_single(
                supabase.table("strategy_assignments")
                .select("id").eq("user_id", uid).eq("strategy_key", strategy_key).eq("active", True)
            )
            if existing:
                skipped += 1
                continue
            try:
                await async_supabase(lambda: supabase.table("strategy_assignments").insert({
                    "user_id": uid, "strategy_key": strategy_key,
                    "required_tier": get_strategy_tier(strategy_key) or "free",
                    "assigned_by": admin_id,
                }).execute())
                created += 1
            except Exception:
                skipped += 1
        record_audit(AuditLogEntry(
            user_id=admin_id, action="batch_assign", resource="strategy_assignments",
            details={"user_ids": user_ids, "strategy_key": strategy_key, "created": created, "skipped": skipped},
        ))
        return {"created": created, "skipped": skipped, "strategy_key": strategy_key}

    async def list_referrals(self, user_id: str | None = None, status: str | None = None) -> dict:
        supabase = get_supabase()
        q = supabase.table("referrals").select("*").order("created_at", desc=True)
        if user_id:
            q = q.eq("referrer_id", user_id)
        if status:
            q = q.eq("status", status)
        data = await async_safe_execute(q)

        profiles = await async_safe_execute(
            supabase.table("profiles").select("id, email, full_name, referral_code, referral_count")
        )
        profile_map = {p["id"]: p for p in (profiles or [])}

        enriched = []
        for r in (data or []):
            referrer = profile_map.get(r.get("referrer_id", ""), {})
            referred = profile_map.get(r.get("referred_user_id", ""), {}) if r.get("referred_user_id") else {}
            enriched.append({
                **r,
                "referrer_name": referrer.get("full_name", ""),
                "referrer_email": referrer.get("email", ""),
                "referred_name": referred.get("full_name", ""),
                "referred_email": r.get("referred_email", referred.get("email", "")),
            })
        return {"referrals": enriched}

    async def referral_stats(self) -> dict:
        supabase = get_supabase()
        data = await async_safe_execute(supabase.table("referrals").select("status"))
        total = len(data or [])
        completed = sum(1 for r in (data or []) if r["status"] == "completed")
        pending = total - completed

        with_profiles = await async_safe_execute(
            supabase.table("profiles").select("id, referral_code, referral_count").not_.is_("referral_code", "null")
        )
        users_with_codes = len(with_profiles or [])

        return {
            "total_referrals": total,
            "completed_referrals": completed,
            "pending_referrals": pending,
            "users_with_referral_codes": users_with_codes,
            "conversion_rate": round(completed / total * 100, 1) if total > 0 else 0,
        }

    async def list_all_user_strategies(self, user_id: str | None = None) -> dict:
        supabase = get_supabase()
        q = supabase.table("user_strategies").select("*").order("created_at", desc=True)
        if user_id:
            q = q.eq("user_id", user_id)
        data = await async_safe_execute(q)
        return {"strategies": data or []}

    async def execute_trade_for_user(self, req: dict, admin_id: str) -> dict:
        from application.services.engine_service import EngineService

        target_user_id = req.pop("user_id")
        supabase = get_supabase()
        user = await async_safe_single(
            supabase.table("profiles").select("id, email, full_name").eq("id", target_user_id)
        )
        if not user:
            raise ValueError("User not found")

        result = await EngineService().execute_trade(target_user_id, req)

        record_audit(AuditLogEntry(
            user_id=admin_id,
            action="admin_place_trade",
            resource="trade",
            details={"target_user": target_user_id, "symbol": req.get("symbol"), "side": req.get("side"), "quantity": req.get("quantity")},
        ))

        return result
