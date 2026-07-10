import logging

from core.capabilities import Capabilities
from core.db import async_supabase, get_supabase
from core.models import CreateUserStrategyRequest, DeployStrategyRequest, UpdateUserStrategyRequest, UserProfile, UserStrategy, UserStrategyLeg
from core.safe_query import async_safe_execute, async_safe_single
from engine.gate import execute_order
from engine.strategy_compiler import compile_user_strategy, validate_user_strategy

logger = logging.getLogger(__name__)


class StrategyService:
    async def list_strategies(self, user_id: str, status_filter: str | None = None) -> list[dict]:
        supabase = get_supabase()
        query = supabase.table("user_strategies").select("*, legs:user_strategy_legs(*)").eq("user_id", user_id)
        if status_filter:
            query = query.eq("status", status_filter)
        data = await async_safe_execute(query.order("created_at", desc=True))
        return [self._row_to_strategy(row) for row in (data or [])]

    async def create_strategy(self, req: CreateUserStrategyRequest, user: UserProfile, caps: Capabilities) -> dict:
        supabase = get_supabase()
        if user.role != "super_admin":
            existing = await async_safe_execute(
                supabase.table("user_strategies").select("id").eq("user_id", user.id).neq("status", "draft")
            )
            if existing and len(existing) >= caps.max_active_strategies:
                raise ValueError(f"Your plan allows a maximum of {caps.max_active_strategies} active strategies.")

        strategy = UserStrategy(
            user_id=user.id, name=req.name, strategy_type=req.strategy_type,
            index_symbol=req.index_symbol, underlying_from=req.underlying_from,
            entry_time=req.entry_time, exit_time=req.exit_time,
            days_of_week=req.days_of_week,
            overall_sl_type=req.overall_sl_type, overall_sl_value=req.overall_sl_value,
            overall_target_type=req.overall_target_type, overall_target_value=req.overall_target_value,
            legs=req.legs,
        )
        validate_user_strategy(strategy)

        strategy_data = strategy.model_dump(exclude={"id", "legs", "created_at", "updated_at"})
        strategy_data["user_id"] = user.id
        strategy_data["days_of_week"] = f"{{{','.join(str(d) for d in (req.days_of_week or [1,2,3,4,5]))}}}"

        result = await async_supabase(lambda: supabase.table("user_strategies").insert(strategy_data).execute())
        if not result or not result.data:
            raise ValueError("Failed to create strategy")

        strategy_id = result.data[0]["id"]
        legs_to_insert = [
            leg.model_dump(exclude={"id", "strategy_id"}, exclude_none=True) | {"strategy_id": strategy_id}
            for leg in req.legs
        ]
        if legs_to_insert:
            try:
                await async_supabase(lambda: supabase.table("user_strategy_legs").insert(legs_to_insert).execute())
            except Exception:
                await async_supabase(lambda: supabase.table("user_strategies").delete().eq("id", strategy_id).execute())
                raise ValueError("Failed to create strategy legs")

        return {"id": strategy_id, "message": "Strategy created"}

    async def get_strategy(self, user_id: str, strategy_id: str) -> UserStrategy:
        row = await async_safe_single(
            get_supabase().table("user_strategies").select("*, legs:user_strategy_legs(*)")
            .eq("id", strategy_id).eq("user_id", user_id)
        )
        if not row:
            raise ValueError("Strategy not found")
        return self._row_to_strategy(row)

    async def update_strategy(self, user_id: str, strategy_id: str, req: UpdateUserStrategyRequest) -> None:
        supabase = get_supabase()
        row = await async_safe_single(supabase.table("user_strategies").select("id").eq("id", strategy_id).eq("user_id", user_id))
        if not row:
            raise ValueError("Strategy not found")

        updates = {}
        for field in ("name", "status", "strategy_type", "index_symbol", "underlying_from", "entry_time", "exit_time",
                      "overall_sl_type", "overall_sl_value", "overall_target_type", "overall_target_value"):
            val = getattr(req, field, None)
            if val is not None:
                updates[field] = val
        if req.days_of_week is not None:
            updates["days_of_week"] = f"{{{','.join(str(d) for d in req.days_of_week)}}}"

        if updates:
            await async_supabase(lambda: supabase.table("user_strategies").update(updates).eq("id", strategy_id).execute())

        if req.legs is not None:
            await async_supabase(lambda: supabase.table("user_strategy_legs").delete().eq("strategy_id", strategy_id).execute())
            legs_to_insert = [
                leg.model_dump(exclude={"id", "strategy_id"}, exclude_none=True) | {"strategy_id": strategy_id}
                for leg in req.legs
            ]
            if legs_to_insert:
                await async_supabase(lambda: supabase.table("user_strategy_legs").insert(legs_to_insert).execute())

    async def delete_strategy(self, user_id: str, strategy_id: str) -> None:
        await async_supabase(lambda: get_supabase().table("user_strategies").delete().eq("id", strategy_id).eq("user_id", user_id).execute())

    async def deploy_strategy(self, user_id: str, strategy_id: str, req: DeployStrategyRequest, user: UserProfile, caps: Capabilities) -> dict:
        mode = req.mode.upper()
        if mode not in ("PAPER", "LIVE"):
            raise ValueError("mode must be 'PAPER' or 'LIVE'")

        supabase = get_supabase()
        if user.role != "super_admin":
            existing = await async_safe_execute(
                supabase.table("user_strategies").select("id").eq("user_id", user.id).neq("status", "draft")
            )
            if existing and len(existing) >= caps.max_active_strategies:
                raise ValueError(f"Your plan allows a maximum of {caps.max_active_strategies} active strategies.")

        strategy = await self.get_strategy(user_id, strategy_id)
        validate_user_strategy(strategy)

        if mode == "LIVE":
            from risk.riskguard import RiskGuard
            rg = RiskGuard(user_id)
            if not await rg.get_live_status():
                raise ValueError("LIVE mode not enabled. Enable it first via POST /risk/live/enable with confirm=true.")

        plan = compile_user_strategy(strategy)

        results = []
        for i, order in enumerate(plan.orders):
            try:
                if mode == "PAPER":
                    from paper.paper_broker import PaperBroker
                    pb = PaperBroker(user_id)
                    await pb.connect()
                    result = await pb.place_order(order)
                else:
                    result = await execute_order(user_id=user_id, order=order, source="user_strategy")
                results.append({
                    "leg_order": plan.legs[i].leg_order if i < len(plan.legs) else i + 1,
                    "symbol": order.symbol, "side": order.side.value,
                    "quantity": order.quantity, "success": result.success,
                    "status": result.status, "message": result.message,
                    "broker_order_id": result.broker_order_id,
                })
            except Exception as e:
                logger.exception("Deploy leg %d failed: %s", i, e)
                results.append({
                    "leg_order": plan.legs[i].leg_order if i < len(plan.legs) else i + 1,
                    "symbol": order.symbol, "side": order.side.value,
                    "quantity": order.quantity, "success": False,
                    "status": "error", "message": str(e),
                })

        if all(r["success"] for r in results):
            await async_supabase(lambda: supabase.table("user_strategies").update({"status": "active"}).eq("id", strategy_id).execute())

        return {"strategy_id": strategy_id, "mode": mode, "results": results}

    def _row_to_strategy(self, row: dict) -> UserStrategy:
        legs_data = row.pop("legs", []) or []
        strategy = UserStrategy(**{k: v for k, v in row.items() if v is not None})
        strategy.legs = [UserStrategyLeg(**leg) for leg in sorted(legs_data, key=lambda x: x.get("leg_order", 0))]
        return strategy
