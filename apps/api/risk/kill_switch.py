import logging
from datetime import UTC, datetime

from core.cache import cache
from core.db import async_supabase, get_supabase
from core.safe_query import async_safe_execute, async_safe_single

logger = logging.getLogger(__name__)

# Redis key under which emergency-stop state is persisted so it survives API
# restarts (the per-user in-memory dict is process-local only).
EMERGENCY_REDIS_PREFIX = "kill_switch:emergency:"
# Global kill switch flag key (single source of truth, shared with the admin
# enable/disable endpoints and risk rules).
GLOBAL_KILL_SWITCH_KEY = "global:kill_switch"


async def _persist_audit(user_id: str, event: str, reason: str = "", triggered_by: str = "") -> bool:
    """Best-effort kill-switch audit write.

    `risk_audit_log` is the primary table (created by migration
    20260804_01600_risk_audit_log.sql); on older deployments where it is
    missing we fall back to the existing `audit_log` table so the audit trail
    is never silently lost.
    """
    payload = {
        "user_id": user_id,
        "event": event,
        "reason": reason or "",
        "triggered_by": triggered_by or "",
        "created_at": datetime.now(UTC).isoformat(),
    }
    try:
        await async_supabase(lambda: get_supabase().table("risk_audit_log").insert(payload).execute())
        return True
    except Exception:
        pass
    try:
        await async_supabase(lambda: get_supabase().table("audit_log").insert({
            "user_id": user_id,
            "action": event,
            "resource": "kill_switch",
            "details": {"reason": reason or "", "triggered_by": triggered_by or ""},
        }).execute())
        return True
    except Exception as e:
        logger.warning("Failed to persist kill-switch audit %s for user %s: %s", event, user_id, e)
        return False


async def _set_emergency_redis(user_id: str, engaged: bool) -> None:
    """Persist/release the emergency-stop flag in Redis (survives restarts)."""
    try:
        r = await cache.get_redis()
        if not r:
            return
        key = f"{EMERGENCY_REDIS_PREFIX}{user_id}"
        if engaged:
            await r.set(key, "1")
        else:
            await r.delete(key)
    except Exception as e:
        logger.warning("Failed to persist emergency stop state to cache for %s: %s", user_id, e)


class KillSwitch:
    def __init__(self):
        self._emergency_stops: dict[str, bool] = {}

    async def recover(self) -> None:
        # 1) Redis state is authoritative across restarts (set by trigger/
        #    release since the restart-safety hardening).
        try:
            r = await cache.get_redis()
            if r:
                keys = await r.keys(f"{EMERGENCY_REDIS_PREFIX}*")
                for key in keys or []:
                    uid = str(key).rsplit(":", 1)[-1]
                    if uid:
                        self._emergency_stops[uid] = True
        except Exception as e:
            logger.error("Failed to recover emergency stops from cache: %s", e)

        # 2) DB audit trail (works once risk_audit_log exists).
        try:
            supabase = get_supabase()
            rows = await async_safe_execute(
                supabase.table("risk_audit_log")
                .select("user_id, event, created_at")
                .eq("event", "EMERGENCY_STOP")
                .order("created_at", desc=True)
                .limit(1000)
            )
            for row in rows or []:
                uid = row.get("user_id", "")
                if uid:
                    released = await async_safe_single(
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
            logger.error("Failed to recover emergency stops from audit log: %s", e)

    def active(self, user_id: str | None = None) -> bool:
        if user_id:
            return self._emergency_stops.get(user_id, False)
        return any(self._emergency_stops.values())

    async def trigger_emergency_stop(self, user_id: str, reason: str = "", triggered_by: str = "") -> bool:
        # engage the in-memory flag FIRST — trading halts even if the audit
        # persistence fails (fail-open infra, fail-closed trading)
        self._emergency_stops[user_id] = True
        await _set_emergency_redis(user_id, engaged=True)
        logger.warning("EMERGENCY STOP triggered for user %s: %s", user_id, reason)
        return await _persist_audit(user_id, "EMERGENCY_STOP", reason, triggered_by)

    async def release_emergency_stop(self, user_id: str, triggered_by: str = "") -> bool:
        self._emergency_stops[user_id] = False
        await _set_emergency_redis(user_id, engaged=False)
        await _persist_audit(user_id, "EMERGENCY_STOP_RELEASED", "Emergency stop released", triggered_by)
        logger.warning("EMERGENCY STOP released for user %s", user_id)
        return True

    async def global_kill_switch_active(self) -> bool:
        # The global kill switch lives in Redis (`global:kill_switch`), set by
        # the admin enable/disable endpoints and consulted by risk rules.
        # The previous DB probe (`risk_settings` where user_id='system') could
        # never match (uuid FK column) and silently disabled the gate.
        try:
            val = await cache.get(GLOBAL_KILL_SWITCH_KEY)
            return val == "1"
        except Exception:
            return False


kill_switch = KillSwitch()
