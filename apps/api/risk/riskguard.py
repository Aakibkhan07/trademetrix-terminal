import logging
from datetime import UTC, datetime

from core.capabilities import resolve_capabilities_by_id
from core.db import async_supabase, get_supabase
from core.models import NormalizedOrder, RiskSettings
from core.safe_query import async_safe_execute, async_safe_insert, async_safe_single, async_safe_update
from risk.helpers import compute_daily_pnl_fifo, get_current_capital_usage, get_current_exposure, get_drawdown, get_open_position_count

logger = logging.getLogger(__name__)


class RiskGuard:
    def __init__(self, user_id: str):
        self.user_id = user_id

    async def check_order(self, order: NormalizedOrder) -> dict:
        settings = await self._load_settings(order.strategy_id)
        if not settings:
            settings = RiskSettings(user_id=self.user_id)

        if settings.kill_switch_enabled:
            return {"allowed": False, "reason": "Kill switch is enabled. All trading halted."}

        if not order.is_paper and not settings.is_live:
            return {"allowed": False, "reason": "LIVE mode not enabled. Enable it first via POST /risk/live/enable with confirm=true."}

        checks = [
            await self._check_max_capital(order, settings),
            await self._check_max_position_size(order, settings),
            await self._check_max_open_positions(order, settings),
            await self._check_max_daily_loss(settings),
            await self._check_drawdown(settings),
        ]

        for check in checks:
            if not check["allowed"]:
                return check

        return {"allowed": True, "reason": ""}

    async def _load_settings(self, strategy_id: str | None = None) -> RiskSettings | None:
        supabase = get_supabase()
        if strategy_id:
            query = supabase.table("risk_settings").select("*").eq("user_id", self.user_id).eq("strategy_id", strategy_id)
            data = await async_safe_single(query)
            if data:
                return RiskSettings(**data)
        query = supabase.table("risk_settings").select("*").eq("user_id", self.user_id)
        data = await async_safe_single(query)
        if data:
            return RiskSettings(**data)
        return None

    async def update_settings(self, settings: RiskSettings) -> None:
        supabase = get_supabase()
        data = settings.model_dump(exclude={"user_id"}, exclude_none=True)
        data["user_id"] = self.user_id
        data["updated_at"] = datetime.now(UTC).isoformat()
        try:
            await async_supabase(lambda: supabase.table("risk_settings").upsert(data, on_conflict=["user_id", "strategy_id"]).execute())
        except Exception as e:
            logger.warning("Failed to update risk settings: %s", e)

    async def enable_kill_switch(self, strategy_id: str | None = None) -> None:
        data = await async_safe_single(get_supabase().table("risk_settings").select("id").eq("user_id", self.user_id))
        if not data:
            await async_safe_insert("risk_settings", {"user_id": self.user_id, "strategy_id": strategy_id, "kill_switch_enabled": True})
        else:
            await async_safe_update("risk_settings", {"kill_switch_enabled": True}, "user_id", self.user_id)
        logger.warning(f"Kill switch enabled for user={self.user_id}")

    async def disable_kill_switch(self, strategy_id: str | None = None) -> None:
        await async_safe_update("risk_settings", {"kill_switch_enabled": False}, "user_id", self.user_id)
        logger.info(f"Kill switch disabled for user={self.user_id}")

    async def enable_live(self, multi_step_confirm: bool = False) -> bool:
        if not multi_step_confirm:
            return False
        data = await async_safe_single(get_supabase().table("risk_settings").select("id").eq("user_id", self.user_id))
        if not data:
            await async_safe_insert("risk_settings", {"user_id": self.user_id, "is_live": True})
        else:
            await async_safe_update("risk_settings", {"is_live": True}, "user_id", self.user_id)
        record_audit_entry(self.user_id, "enable_live", "risk_settings")
        logger.warning(f"LIVE trading enabled for user={self.user_id}")
        return True

    async def disable_live(self) -> None:
        await async_safe_update("risk_settings", {"is_live": False}, "user_id", self.user_id)
        logger.info(f"LIVE trading disabled for user={self.user_id}")

    async def get_kill_switch_status(self) -> bool:
        data = await async_safe_single(get_supabase().table("risk_settings").select("kill_switch_enabled").eq("user_id", self.user_id))
        if data:
            return data.get("kill_switch_enabled", False)
        return False

    async def get_live_status(self) -> bool:
        data = await async_safe_single(get_supabase().table("risk_settings").select("is_live").eq("user_id", self.user_id))
        if data:
            return data.get("is_live", False)
        return False

    async def _check_max_capital(self, order: NormalizedOrder, settings: RiskSettings) -> dict:
        if settings.max_capital <= 0:
            return {"allowed": True, "reason": ""}
        order_value = order.quantity * (order.price or 0)
        current_usage = await self._get_current_capital_usage()
        if current_usage + order_value > settings.max_capital:
            return {"allowed": False, "reason": f"Order value {order_value:.2f} would exceed max capital {settings.max_capital:.2f}"}
        return {"allowed": True, "reason": ""}

    async def _check_max_position_size(self, order: NormalizedOrder, settings: RiskSettings) -> dict:
        if settings.max_position_size <= 0:
            return {"allowed": True, "reason": ""}
        order_value = order.quantity * (order.price or 0)
        if order_value > settings.max_position_size:
            return {"allowed": False, "reason": f"Order value {order_value:.2f} exceeds max position size {settings.max_position_size:.2f}"}
        return {"allowed": True, "reason": ""}

    async def _check_max_open_positions(self, order: NormalizedOrder, settings: RiskSettings) -> dict:
        if settings.max_open_positions <= 0:
            return {"allowed": True, "reason": ""}
        open_count = await self._get_open_position_count()
        if open_count >= settings.max_open_positions:
            return {"allowed": False, "reason": f"Open positions {open_count} >= max {settings.max_open_positions}"}
        return {"allowed": True, "reason": ""}

    async def _check_max_daily_loss(self, settings: RiskSettings) -> dict:
        max_loss = settings.max_daily_loss
        if max_loss <= 0:
            caps = await resolve_capabilities_by_id(self.user_id)
            max_loss = caps.daily_loss_floor
        today_pnl = await self._get_today_pnl()
        if today_pnl <= -max_loss:
            return {"allowed": False, "reason": f"Daily loss {today_pnl:.2f} exceeds max {max_loss:.2f}. Circuit breaker triggered."}
        return {"allowed": True, "reason": ""}

    async def _check_drawdown(self, settings: RiskSettings) -> dict:
        if settings.max_drawdown_pct <= 0:
            return {"allowed": True, "reason": ""}
        current_dd = await self._get_current_drawdown()
        if current_dd >= settings.max_drawdown_pct:
            return {"allowed": False, "reason": f"Drawdown {current_dd:.1f}% exceeds max {settings.max_drawdown_pct:.1f}% Auto-pause triggered"}
        return {"allowed": True, "reason": ""}

    async def _get_current_capital_usage(self) -> float:
        return await get_current_capital_usage(self.user_id)

    async def _get_open_position_count(self) -> int:
        return await get_open_position_count(self.user_id)

    async def _get_today_pnl(self) -> float:
        return await compute_daily_pnl_fifo(self.user_id)

    async def _get_current_drawdown(self) -> float:
        return await get_drawdown(self.user_id)

def record_audit_entry(user_id: str, action: str, resource: str) -> None:
    try:
        from core.audit import record_audit
        from core.models import AuditLogEntry
        record_audit(AuditLogEntry(user_id=user_id, action=action, resource=resource))
    except Exception as e:
        logger.warning("RiskGuard audit record failed: %s", e)
