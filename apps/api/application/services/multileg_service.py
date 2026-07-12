import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from core.db import get_supabase
from core.models import Exchange, InstrumentType, NormalizedOrder, OptionType, OrderSide, OrderType, ProductType
from core.safe_query import async_safe_execute, async_safe_single
from engine.gate import execute_order

logger = logging.getLogger(__name__)


class MultiLegService:
    async def list_strategies(self, user_id: str) -> list[dict]:
        data = await async_safe_execute(
            get_supabase().table("multi_leg_strategies")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
        )
        return data or []

    async def get_strategy(self, strategy_id: str, user_id: str) -> dict | None:
        data = await async_safe_single(
            get_supabase().table("multi_leg_strategies")
            .select("*")
            .eq("id", strategy_id)
            .eq("user_id", user_id)
        )
        if not data:
            return None
        legs = await async_safe_execute(
            get_supabase().table("multi_leg_strategy_legs")
            .select("*")
            .eq("strategy_id", strategy_id)
            .order("leg_index")
        )
        data["legs"] = legs or []
        return data

    async def create_strategy(self, user_id: str, req: Any) -> dict:
        supabase = get_supabase()
        strat_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        strat_payload = {
            "id": strat_id,
            "user_id": user_id,
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

    async def delete_strategy(self, strategy_id: str, user_id: str) -> bool:
        existing = await async_safe_single(
            get_supabase().table("multi_leg_strategies").select("id").eq("id", strategy_id).eq("user_id", user_id)
        )
        if not existing:
            return False

        await async_safe_execute(get_supabase().table("multi_leg_strategy_legs").delete().eq("strategy_id", strategy_id))
        await async_safe_execute(get_supabase().table("multi_leg_strategies").delete().eq("id", strategy_id))
        return True

    async def place_strategy(self, strategy_id: str, user_id: str) -> dict:
        data = await async_safe_single(
            get_supabase().table("multi_leg_strategies").select("*").eq("id", strategy_id).eq("user_id", user_id)
        )
        if not data:
            raise ValueError("Strategy not found")

        legs = await async_safe_execute(
            get_supabase().table("multi_leg_strategy_legs").select("*").eq("strategy_id", strategy_id).order("leg_index")
        )
        if not legs:
            raise ValueError("No legs defined")

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
            result = await execute_order(user_id, order, source="multi_leg")
            results.append(result)
            order_ids.append(result.broker_order_id)

        now = datetime.now(UTC).isoformat()
        await async_safe_execute(
            get_supabase().table("multi_leg_strategies")
            .update({"status": "active", "last_placed_at": now, "updated_at": now})
            .eq("id", strategy_id)
        )

        return {
            "message": f"Placed {len(results)} legs",
            "strategy_id": strategy_id,
            "order_ids": order_ids,
            "results": [r.model_dump() for r in results],
        }
