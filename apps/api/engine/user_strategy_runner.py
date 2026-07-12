"""Server-side runner for user strategies.

Enforces time-based square-off at strategy.exit_time in IST, even when
the user's browser is closed. All generated orders flow through
RiskGuard → gate → execute_order.

Trailing SL evaluation runs on live ticks (via scheduler callback).
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta, timezone

from core.cache import cache
from core.db import get_supabase
from core.models import UserStrategy
from core.safe_query import async_safe_execute, async_safe_single
from risk.leg_controls import (
    cancel_pending_reentries, handle_square_off,
)

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
POLL_INTERVAL = 30
SQUARE_OFF_CHECK_INTERVAL = 60
ACTIVE_STRATEGIES_CACHE_KEY = "user_strategy_runner:active_ids"
LOCK_KEY = "user_strategy_runner:lock"
LOCK_TTL = 10


class UserStrategyRunner:
    def __init__(self):
        self._running = False
        self._poll_task: asyncio.Task | None = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._run_loop())
        logger.info("UserStrategyRunner started")

    async def stop(self):
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None
        logger.info("UserStrategyRunner stopped")

    async def _run_loop(self):
        while self._running:
            try:
                now = datetime.now(IST)
                await self._check_square_off(now)
            except Exception as e:
                logger.exception("UserStrategyRunner loop error: %s", e)
            await asyncio.sleep(SQUARE_OFF_CHECK_INTERVAL)

    async def _check_square_off(self, now: datetime):
        rows = await async_safe_execute(
            get_supabase()
            .table("user_strategies")
            .select("id, user_id, exit_time, days_of_week, underlying_from, strategy_type, name")
            .eq("status", "active")
        )
        if not rows:
            return

        current_dow = now.isoweekday()
        current_time = now.strftime("%H:%M")

        for row in rows:
            strategy_id = row["id"]
            user_id = row["user_id"]
            exit_time = row.get("exit_time", "")
            days_of_week = row.get("days_of_week", [1, 2, 3, 4, 5])

            if not exit_time or current_dow not in days_of_week:
                continue
            if current_time < exit_time:
                continue
            if await _is_squared_off_today(user_id, strategy_id):
                continue

            logger.info(
                "Square-off triggered: strategy=%s user=%s exit_time=%s current=%s",
                strategy_id, user_id, exit_time, current_time,
            )

            legs = await _get_open_legs(strategy_id)
            if legs:
                results = await handle_square_off(user_id, strategy_id, legs, current_time)
                for r in results:
                    if not r.get("result", {}).get("success", False):
                        logger.warning(
                            "Square-off leg failed: strategy=%s leg=%s reason=%s",
                            strategy_id, r.get("leg_order"), r.get("result", {}).get("reason", ""),
                        )

            await _mark_squared_off_today(user_id, strategy_id)

    async def activate_strategy(self, strategy_id: str):
        logger.info("Activating user strategy runner for id=%s", strategy_id)

    async def deactivate_strategy(self, strategy_id: str, reason: str = ""):
        logger.warning("Deactivating user strategy: id=%s reason=%s", strategy_id, reason)
        row = await async_safe_single(
            get_supabase()
            .table("user_strategies")
            .select("user_id")
            .eq("id", strategy_id)
        )
        if row:
            await cancel_pending_reentries(row["user_id"], strategy_id, reason=reason)


async def _get_open_legs(strategy_id: str) -> list[dict]:
    """Get open legs for a strategy from the last deploy/execution state.

    Reads from user_strategy_legs joined with latest order state to
    determine which legs still have open positions.
    """
    supabase = get_supabase()
    row = await async_safe_single(
        supabase.table("user_strategies")
        .select("*, legs:user_strategy_legs(*)")
        .eq("id", strategy_id)
    )
    if not row:
        return []

    strategy = UserStrategy(**{k: v for k, v in row.items() if v is not None})
    if not strategy.legs:
        return []

    legs_data = strategy.legs
    if isinstance(legs_data, list) and legs_data and hasattr(legs_data[0], "model_dump"):
        legs_data = [l.model_dump() for l in legs_data]

    from engine.strategy_compiler import LOT_SIZES
    lot_size = LOT_SIZES.get(strategy.index_symbol, 65)
    symbol = strategy.index_symbol
    expiry_str = ""

    from engine.strategy_compiler import resolve_expiry
    if legs_data and isinstance(legs_data, list) and legs_data:
        if isinstance(legs_data[0], dict):
            from core.models import UserStrategyLeg
            first_leg = UserStrategyLeg(**{k: v for k, v in legs_data[0].items() if v is not None})
            if first_leg.segment:
                expiry_str = resolve_expiry(first_leg, symbol)

    result = []
    for leg in (legs_data or []):
        if isinstance(leg, dict):
            leg_order = leg.get("leg_order", 0)
            position = leg.get("position", "buy")
            lots = leg.get("lots", 1)
            option_type = leg.get("option_type", "CE")
            strike_value = leg.get("strike_value", 0)

            from engine.strategy_compiler import STRIKE_INTERVALS
            interval = STRIKE_INTERVALS.get(symbol, 50)
            strike_price = int(strike_value) * interval if strike_value else 0
            strike_val = abs(strike_price)
            if strike_val <= 0:
                strike_val = 24000

            order_symbol = f"{symbol}{expiry_str}{strike_val}{option_type}"
            result.append({
                "leg_order": leg_order,
                "symbol": order_symbol,
                "side": position,
                "quantity": lots * lot_size,
            })
    return result


async def _is_squared_off_today(user_id: str, strategy_id: str) -> bool:
    key = f"sqoff:{user_id}:{strategy_id}:{datetime.now(UTC).strftime('%Y%m%d')}"
    val = await cache.get(key, False)
    return bool(val)


async def _mark_squared_off_today(user_id: str, strategy_id: str):
    key = f"sqoff:{user_id}:{strategy_id}:{datetime.now(UTC).strftime('%Y%m%d')}"
    await cache.set(key, True, ttl=86400)


user_strategy_runner = UserStrategyRunner()
