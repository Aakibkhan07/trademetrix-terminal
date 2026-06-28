import logging
from datetime import UTC, date, datetime

from core.db import get_supabase
from core.models import NormalizedOrder, RiskSettings

logger = logging.getLogger(__name__)


class RiskGuard:
    def __init__(self, user_id: str):
        self.user_id = user_id

    async def check_order(self, order: NormalizedOrder) -> dict:
        settings = await self._load_settings(order.strategy_id)
        if not settings:
            return {"allowed": True, "reason": ""}

        if settings.kill_switch_enabled:
            return {"allowed": False, "reason": "Kill switch is enabled. All trading halted."}

        if not settings.is_live and not self._is_paper_safe():
            return {"allowed": False, "reason": "LIVE trading not enabled in risk settings."}

        checks = [
            self._check_max_capital(order, settings),
            self._check_max_position_size(order, settings),
            self._check_max_open_positions(order, settings),
            self._check_max_daily_loss(settings),
            self._check_drawdown(settings),
        ]

        for check in checks:
            if not check["allowed"]:
                return check

        return {"allowed": True, "reason": ""}

    async def _load_settings(self, strategy_id: str | None = None) -> RiskSettings | None:
        supabase = get_supabase()
        query = supabase.table("risk_settings").select("*").eq("user_id", self.user_id)

        if strategy_id:
            query = query.eq("strategy_id", strategy_id)

        result = query.maybe_single().execute()
        if result.data:
            return RiskSettings(**result.data)
        return None

    async def update_settings(self, settings: RiskSettings) -> None:
        supabase = get_supabase()
        data = settings.model_dump(exclude={"user_id"}, exclude_none=True)
        data["user_id"] = self.user_id
        data["updated_at"] = datetime.now(UTC).isoformat()

        supabase.table("risk_settings").upsert(
            data,
            on_conflict=["user_id", "strategy_id"],
        ).execute()

    async def enable_kill_switch(self, strategy_id: str | None = None) -> None:
        supabase = get_supabase()
        query = supabase.table("risk_settings").select("id").eq("user_id", self.user_id)
        if strategy_id:
            query = query.eq("strategy_id", strategy_id)
        else:
            query = query.is_("strategy_id", "null")
        result = query.maybe_single().execute()
        if not result or not result.data:
            supabase.table("risk_settings").insert({
                "user_id": self.user_id,
                "strategy_id": strategy_id,
                "kill_switch_enabled": True,
            }).execute()
        else:
            update = supabase.table("risk_settings").update({"kill_switch_enabled": True}).eq("user_id", self.user_id)
            if strategy_id:
                update = update.eq("strategy_id", strategy_id)
            else:
                update = update.is_("strategy_id", "null")
            update.execute()
        logger.warning(f"Kill switch enabled for user={self.user_id} strategy={strategy_id}")

    async def disable_kill_switch(self, strategy_id: str | None = None) -> None:
        supabase = get_supabase()
        query = supabase.table("risk_settings").update({"kill_switch_enabled": False}).eq("user_id", self.user_id)
        if strategy_id:
            query = query.eq("strategy_id", strategy_id)
        else:
            query = query.is_("strategy_id", "null")
        query.execute()
        logger.info(f"Kill switch disabled for user={self.user_id} strategy={strategy_id}")

    async def enable_live(self, multi_step_confirm: bool = False) -> bool:
        if not multi_step_confirm:
            return False

        supabase = get_supabase()
        supabase.table("risk_settings").update({"is_live": True}).eq("user_id", self.user_id).execute()

        record_audit_entry(self.user_id, "enable_live", "risk_settings")
        logger.warning(f"LIVE trading enabled for user={self.user_id}")
        return True

    async def disable_live(self) -> None:
        supabase = get_supabase()
        supabase.table("risk_settings").update({"is_live": False}).eq("user_id", self.user_id).execute()
        logger.info(f"LIVE trading disabled for user={self.user_id}")

    async def get_kill_switch_status(self) -> bool:
        supabase = get_supabase()
        result = supabase.table("risk_settings").select("kill_switch_enabled").eq("user_id", self.user_id).maybe_single().execute()
        if result and result.data:
            return result.data.get("kill_switch_enabled", False)
        return False

    async def get_live_status(self) -> bool:
        supabase = get_supabase()
        result = supabase.table("risk_settings").select("is_live").eq("user_id", self.user_id).maybe_single().execute()
        if result and result.data:
            return result.data.get("is_live", False)
        return False

    def _check_max_capital(self, order: NormalizedOrder, settings: RiskSettings) -> dict:
        if settings.max_capital <= 0:
            return {"allowed": True, "reason": ""}

        order_value = order.quantity * (order.price or 0)
        current_usage = self._get_current_capital_usage()

        if current_usage + order_value > settings.max_capital:
            return {
                "allowed": False,
                "reason": f"Order value {order_value:.2f} would exceed max capital {settings.max_capital:.2f}",
            }
        return {"allowed": True, "reason": ""}

    def _check_max_position_size(self, order: NormalizedOrder, settings: RiskSettings) -> dict:
        if settings.max_position_size <= 0:
            return {"allowed": True, "reason": ""}

        order_value = order.quantity * (order.price or 0)
        if order_value > settings.max_position_size:
            return {
                "allowed": False,
                "reason": f"Order value {order_value:.2f} exceeds max position size {settings.max_position_size:.2f}",
            }
        return {"allowed": True, "reason": ""}

    def _check_max_open_positions(self, order: NormalizedOrder, settings: RiskSettings) -> dict:
        if settings.max_open_positions <= 0:
            return {"allowed": True, "reason": ""}

        open_count = self._get_open_position_count()
        if open_count >= settings.max_open_positions:
            return {
                "allowed": False,
                "reason": f"Open positions {open_count} >= max {settings.max_open_positions}",
            }
        return {"allowed": True, "reason": ""}

    def _check_max_daily_loss(self, settings: RiskSettings) -> dict:
        if settings.max_daily_loss <= 0:
            return {"allowed": True, "reason": ""}

        today_pnl = self._get_today_pnl()
        if today_pnl <= -settings.max_daily_loss:
            return {
                "allowed": False,
                "reason": f"Daily loss {today_pnl:.2f} exceeds max {settings.max_daily_loss:.2f} Circuit breaker triggered",
            }
        return {"allowed": True, "reason": ""}

    def _check_drawdown(self, settings: RiskSettings) -> dict:
        if settings.max_drawdown_pct <= 0:
            return {"allowed": True, "reason": ""}

        current_dd = self._get_current_drawdown()
        if current_dd >= settings.max_drawdown_pct:
            return {
                "allowed": False,
                "reason": f"Drawdown {current_dd:.1f}% exceeds max {settings.max_drawdown_pct:.1f}% Auto-pause triggered",
            }
        return {"allowed": True, "reason": ""}

    def _get_current_capital_usage(self) -> float:
        try:
            supabase = get_supabase()
            result = supabase.table("positions_snapshot").select("*").eq("user_id", self.user_id).execute()
            total = 0
            for pos in result.data or []:
                total += abs(pos.get("quantity", 0)) * pos.get("average_buy_price", 0)
            return total
        except Exception:
            return 0

    def _get_open_position_count(self) -> int:
        try:
            supabase = get_supabase()
            result = supabase.table("positions_snapshot").select("*").eq("user_id", self.user_id).execute()
            return len([p for p in (result.data or []) if p.get("quantity", 0) != 0])
        except Exception:
            return 0

    def _get_today_pnl(self) -> float:
        try:
            supabase = get_supabase()
            today = date.today().isoformat()
            result = supabase.table("orders").select("total_value, side, status").eq("user_id", self.user_id).gte("created_at", today).execute()
            pnl = 0
            for o in result.data or []:
                if o.get("status") == "FILLED":
                    val = float(o.get("total_value", 0))
                    if o.get("side") == "SELL":
                        pnl += val
                    else:
                        pnl -= val
            return pnl
        except Exception:
            return 0

    def _get_current_drawdown(self) -> float:
        try:
            supabase = get_supabase()
            result = supabase.table("strategy_runs").select("total_pnl").eq("user_id", self.user_id).execute()
            if not result.data:
                return 0
            pnls = [float(r.get("total_pnl", 0)) for r in result.data]
            peak = max(pnls) if pnls else 0
            current = sum(pnls)
            if peak <= 0:
                return 0
            return max(0, (peak - current) / peak * 100)
        except Exception:
            return 0

    @staticmethod
    def _is_paper_safe() -> bool:
        return True


def record_audit_entry(user_id: str, action: str, resource: str) -> None:
    try:
        from core.audit import record_audit
        from core.models import AuditLogEntry
        record_audit(AuditLogEntry(
            user_id=user_id,
            action=action,
            resource=resource,
        ))
    except Exception:
        pass
