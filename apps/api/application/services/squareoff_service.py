import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from core.db import get_supabase
from core.deps import get_user_by_id
from core.models import Exchange, NormalizedOrder, OrderSide, OrderType, ProductType, UserProfile
from core.safe_query import async_safe_execute, async_safe_single
from engine.executor import ExecutionEngine
from engine.gate import execute_order

logger = logging.getLogger(__name__)

SQUAREOFF_TABLE = "squareoff_config"


class SquareoffConfigModel:
    def __init__(self, enabled: bool = False, time: str = "15:15", days: list[int] | None = None, user_id: str = ""):
        self.enabled = enabled
        self.time = time
        self.days = days or [0, 1, 2, 3, 4]
        self.user_id = user_id


class SquareoffService:
    def __init__(self) -> None:
        self._cache: dict[str, SquareoffConfigModel] = {}
        self._task: asyncio.Task | None = None

    async def get_config(self, user_id: str) -> dict:
        supabase = get_supabase()
        data = await async_safe_single(
            supabase.table(SQUAREOFF_TABLE).select("*").eq("user_id", user_id)
        )
        if not data:
            return {"enabled": False, "time": "15:15", "days": [0, 1, 2, 3, 4]}
        return {
            "enabled": data.get("enabled", False),
            "time": data.get("squareoff_time", "15:15"),
            "days": data.get("days", [0, 1, 2, 3, 4]),
        }

    async def set_config(
        self, user_id: str, enabled: bool, time: str, days: list[int]
    ) -> dict:
        supabase = get_supabase()
        existing = await async_safe_single(
            supabase.table(SQUAREOFF_TABLE).select("id").eq("user_id", user_id)
        )
        payload: dict[str, Any] = {
            "user_id": user_id,
            "enabled": enabled,
            "squareoff_time": time,
            "days": days,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if existing:
            await async_safe_execute(
                supabase.table(SQUAREOFF_TABLE).update(payload).eq("user_id", user_id)
            )
        else:
            payload["created_at"] = datetime.now(UTC).isoformat()
            await async_safe_execute(supabase.table(SQUAREOFF_TABLE).insert(payload))

        self._set_cache(
            user_id, SquareoffConfigModel(enabled=enabled, time=time, days=days, user_id=user_id)
        )
        return {"message": "Squareoff config updated"}

    async def run_squareoff(self, user_id: str) -> dict:
        supabase = get_supabase()
        creds = await async_safe_single(
            supabase.table("broker_credentials")
            .select("broker")
            .eq("user_id", user_id)
            .eq("is_active", True)
        )
        if not creds:
            return {"message": "No active broker", "squareoff_count": 0}

        engine = ExecutionEngine(user_id, creds["broker"])
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
            result = await execute_order(user_id, order, source="squareoff")
            results.append(result)

        return {
            "message": f"Squareoff executed for {len(intraday)} positions",
            "squareoff_count": len(results),
            "results": [r.model_dump() for r in results],
        }

    async def run_squareoff_for_user(self, user: UserProfile) -> None:
        supabase = get_supabase()
        creds = await async_safe_single(
            supabase.table("broker_credentials")
            .select("broker")
            .eq("user_id", user.id)
            .eq("is_active", True)
        )
        if not creds:
            return

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

    def start_scheduler(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._squareoff_loop())
            logger.info("Squareoff scheduler started")

    def stop_scheduler(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
            logger.info("Squareoff scheduler stopped")

    async def _squareoff_loop(self) -> None:
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
                        cfg = SquareoffConfigModel(
                            enabled=True, time=sq_time, days=days, user_id=user_id,
                        )
                        self._set_cache(user_id, cfg)
                        try:
                            user = await get_user_by_id(user_id)
                            if user:
                                await self.run_squareoff_for_user(user)
                        except Exception as e:
                            logger.error("Auto squareoff failed for %s: %s", user_id, e)
            except Exception as e:
                logger.error("Squareoff loop error: %s", e)
            await asyncio.sleep(30)

    def _set_cache(self, user_id: str, config: SquareoffConfigModel) -> None:
        self._cache[user_id] = config
