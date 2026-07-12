import asyncio
import time
from datetime import UTC, datetime
from typing import Any, cast

from core.db import async_supabase, get_supabase
from core.models import NormalizedOrder
from core.safe_query import async_safe_execute, async_safe_single
from engine.executor import ExecutionEngine
from engine.gate import execute_order
from engine.token_refresh import get_token_status

_engine_cache: dict[str, tuple[ExecutionEngine, float]] = {}
_ENGINE_TTL = 120


class EngineService:
    def start_run(self, user_id: str, strategy_id: str, broker: str, mode: str, symbols: list[str]) -> dict:
        raise NotImplementedError("Use create_run instead")

    async def create_run(self, user_id: str, strategy_id: str, broker: str, mode: str, symbols: list[str] | None = None) -> dict:
        payload = {
            "user_id": user_id,
            "strategy_id": strategy_id,
            "broker": broker,
            "mode": mode,
            "symbols": symbols or [],
            "status": "running",
            "started_at": datetime.now(UTC).isoformat(),
        }
        result = await async_supabase(lambda: get_supabase().table("strategy_runs").insert(payload).execute())
        return {"run_id": cast(dict[str, Any], result.data[0])["id"], "status": "running"}

    async def stop_run(self, user_id: str, run_id: str) -> dict:
        await async_supabase(lambda: get_supabase().table("strategy_runs").update(
            {"status": "stopped", "stopped_at": datetime.now(UTC).isoformat()}
        ).eq("id", run_id).eq("user_id", user_id).execute())
        return {"message": "Engine stopped"}

    async def execute_trade(self, user_id: str, req: dict) -> dict:
        from core.models import Exchange, InstrumentType, OptionType, OrderSide, OrderType, ProductType

        order = NormalizedOrder(
            symbol=req["symbol"],
            exchange=Exchange(req.get("exchange", "NSE")),
            side=OrderSide(req["side"]),
            order_type=OrderType(req.get("order_type", "MARKET")),
            product=ProductType(req.get("product", "INTRADAY")),
            quantity=req["quantity"],
            price=req.get("price", 0.0),
            trigger_price=req.get("trigger_price"),
            strategy_id=req.get("strategy_id"),
            instrument_type=InstrumentType(req.get("instrument_type", "EQ")),
            strike_price=req.get("strike_price"),
            expiry_date=req.get("expiry_date"),
            option_type=OptionType(req["option_type"]) if req.get("option_type") else None,
            source="manual",
        )
        result = await execute_order(user_id, order, source="manual")
        return {"result": result.model_dump()}

    async def get_orders(self, user_id: str, limit: int = 100) -> list[dict]:
        data = await async_safe_execute(
            get_supabase().table("orders").select("*")
            .eq("user_id", user_id).order("created_at", desc=True).limit(limit)
        )
        return data or []

    async def cancel_order(self, user_id: str, order_id: str) -> dict:
        from execution import execution_manager
        from execution.models import ExecutionRequest

        creds = await async_safe_single(
            get_supabase().table("broker_credentials").select("broker").eq("user_id", user_id).eq("is_active", True)
        )
        if not creds:
            raise ValueError("No active broker configured")

        req = ExecutionRequest(
            user_id=user_id, broker=creds["broker"], symbol="", side="", quantity=0, source="cancel",
        )
        result = await execution_manager.cancel_order(req, order_id)
        return {"result": result.model_dump()}

    async def add_order_note(self, user_id: str, order_id: str, note: str, tags: list[str] | None = None) -> dict:
        order = await async_safe_single(
            get_supabase().table("orders").select("id").eq("id", order_id).eq("user_id", user_id)
        )
        if not order:
            raise ValueError("Order not found")
        result = await async_supabase(lambda: get_supabase().table("journal_entries").insert({
            "user_id": user_id, "entry_type": "trade_note", "content": note,
            "tags": tags or [], "trade_ids": [order_id],
        }).execute())
        return {"note": result.data[0]}

    async def get_order_notes(self, user_id: str) -> dict:
        data = await async_safe_execute(
            get_supabase().table("journal_entries").select("*")
            .eq("user_id", user_id).eq("entry_type", "trade_note")
            .order("created_at", desc=True).limit(100)
        ) or []
        return {"notes": data}

    async def get_active_broker(self, user_id: str) -> str | None:
        creds = await async_safe_single(
            get_supabase().table("broker_credentials").select("broker").eq("user_id", user_id).eq("is_active", True)
        )
        return creds["broker"] if creds else None

    async def get_positions(self, user_id: str) -> list[dict]:
        broker = await self.get_active_broker(user_id)
        if not broker:
            return []
        try:
            engine = await self._get_engine(user_id, broker)
            positions = await engine.get_positions()
            return [p.model_dump() for p in positions]
        except ValueError:
            return []

    async def get_funds(self, user_id: str) -> dict:
        broker = await self.get_active_broker(user_id)
        if not broker:
            return {"total_margin": 0, "used_margin": 0, "available_margin": 0}
        try:
            engine = await self._get_engine(user_id, broker)
            funds = await engine.get_funds()
            return funds.model_dump()
        except ValueError:
            return {"total_margin": 0, "used_margin": 0, "available_margin": 0}

    async def get_runs(self, user_id: str) -> list[dict]:
        data = await async_safe_execute(
            get_supabase().table("strategy_runs").select("*")
            .eq("user_id", user_id).order("created_at", desc=True)
        )
        return data or []

    async def get_token_status(self, user_id: str) -> dict:
        broker = await self.get_active_broker(user_id)
        if not broker:
            return {"status": "unknown", "broker": ""}
        return await get_token_status(user_id, broker)

    async def _get_engine(self, user_id: str, broker: str) -> ExecutionEngine:
        global _engine_cache
        key = f"{user_id}:{broker}"
        now = time.monotonic()
        stale = [k for k, (_, ts) in _engine_cache.items() if now - ts >= _ENGINE_TTL]
        for k in stale:
            entry = _engine_cache.pop(k, None)
            if entry:
                asyncio.ensure_future(entry[0].stop())

        entry = _engine_cache.get(key)
        if entry and now - entry[1] < _ENGINE_TTL:
            return entry[0]

        engine = ExecutionEngine(user_id, broker)
        await engine.start()
        _engine_cache[key] = (engine, now)
        return engine
