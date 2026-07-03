import logging
from datetime import UTC, datetime

from core.db import async_supabase, get_supabase
from core.safe_query import safe_execute, safe_single

logger = logging.getLogger(__name__)


class KillSwitch:
    def __init__(self):
        self._emergency_stops: dict[str, bool] = {}

    async def recover(self) -> None:
        try:
            supabase = get_supabase()
            rows = safe_execute(
                supabase.table("risk_audit_log")
                .select("user_id, event, created_at")
                .eq("event", "EMERGENCY_STOP")
                .order("created_at", desc=True)
                .limit(1000)
            )
            for row in rows or []:
                uid = row.get("user_id", "")
                if uid:
                    released = safe_single(
                        supabase.table("risk_audit_log")
                        .select("id")
                        .eq("user_id", uid)
                        .eq("event", "EMERGENCY_STOP_RELEASED")
                        .gte("created_at", row.get("created_at", ""))
                        .limit(1)
                    )
                    if not released:
                        self._emergency_stops[uid] = True
        except Exception as e:
            logger.error("Failed to recover emergency stops: %s", e)

    def active(self, user_id: str | None = None) -> bool:
        if user_id:
            return self._emergency_stops.get(user_id, False)
        return any(self._emergency_stops.values())

    async def trigger_emergency_stop(self, user_id: str, reason: str = "", triggered_by: str = "") -> bool:
        try:
            await async_supabase(lambda: get_supabase().table("risk_audit_log").insert({
                "user_id": user_id,
                "event": "EMERGENCY_STOP",
                "reason": reason or "Manual emergency stop",
                "triggered_by": triggered_by,
                "created_at": datetime.now(UTC).isoformat(),
            }).execute())
            self._emergency_stops[user_id] = True
            logger.warning("EMERGENCY STOP triggered for user %s: %s", user_id, reason)
            return True
        except Exception as e:
            logger.error("Failed to trigger emergency stop: %s", e)
            return False

    async def release_emergency_stop(self, user_id: str, triggered_by: str = "") -> bool:
        try:
            await async_supabase(lambda: get_supabase().table("risk_audit_log").insert({
                "user_id": user_id,
                "event": "EMERGENCY_STOP_RELEASED",
                "reason": "Emergency stop released",
                "triggered_by": triggered_by,
                "created_at": datetime.now(UTC).isoformat(),
            }).execute())
            self._emergency_stops[user_id] = False
            logger.warning("EMERGENCY STOP released for user %s", user_id)
            return True
        except Exception as e:
            logger.error("Failed to release emergency stop: %s", e)
            return False

    async def global_kill_switch_active(self) -> bool:
        try:
            row = safe_single(
                get_supabase().table("risk_settings")
                .select("kill_switch_enabled")
                .eq("user_id", "system")
                .limit(1)
                .execute()
            )
            return bool(row and row.get("kill_switch_enabled", False))
        except Exception:
            return False


kill_switch = KillSwitch()
