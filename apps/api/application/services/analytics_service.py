import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, cast

from core.db import async_supabase, get_supabase

logger = logging.getLogger(__name__)


class AnalyticsService:
    def __init__(self) -> None:
        self._events: list[dict] = []
        self._sessions: dict[str, list[dict]] = defaultdict(list)
        self._feedback_store: list[dict] = []

    def track_event(
        self,
        event_name: str,
        properties: dict | None = None,
        session_id: str = "",
        user_id: str = "",
        timestamp: str | None = None,
    ) -> dict:
        if not event_name:
            raise ValueError("event is required")

        entry = {
            "event": event_name,
            "properties": properties or {},
            "session_id": session_id or "",
            "user_id": user_id or "",
            "timestamp": timestamp or datetime.utcnow().isoformat(),
            "received_at": datetime.utcnow().isoformat(),
        }
        self._events.append(entry)

        if session_id:
            self._sessions[session_id].append(entry)

        logger.debug("Analytics event: %s user=%s session=%s", event_name, user_id, session_id)
        return {"ok": True, "event": event_name}

    def list_events(self, event_filter: str | None = None, limit: int = 100) -> dict:
        result = self._events
        if event_filter:
            result = [e for e in result if e["event"] == event_filter]
        return {"events": result[-limit:], "total": len(result)}

    async def get_admin_overview(self) -> dict:
        supabase = get_supabase()

        profiles_q = await async_supabase(
            lambda: supabase.table("profiles").select("id, created_at").execute()
        )
        all_profiles: list[dict[str, Any]] = cast(list[dict[str, Any]], profiles_q.data) if profiles_q and profiles_q.data else []
        total_users = len(all_profiles)

        brokers_q = await async_supabase(
            lambda: supabase.table("broker_credentials").select("user_id").execute()
        )
        brokers_data: list[dict[str, Any]] = cast(list[dict[str, Any]], brokers_q.data) if brokers_q and brokers_q.data else []
        broker_users = len(set(b["user_id"] for b in brokers_data))

        orders_q = await async_supabase(
            lambda: supabase.table("orders").select("user_id, is_paper").execute()
        )
        all_orders: list[dict[str, Any]] = cast(list[dict[str, Any]], orders_q.data) if orders_q and orders_q.data else []
        traded_users = len(set(o["user_id"] for o in all_orders))
        live_traded_users = len(set(o["user_id"] for o in all_orders if not o.get("is_paper", True)))

        assignments_q = await async_supabase(
            lambda: supabase.table("strategy_assignments").select("user_id").execute()
        )
        assignments_data: list[dict[str, Any]] = cast(list[dict[str, Any]], assignments_q.data) if assignments_q and assignments_q.data else []
        assigned_users = len(set(a["user_id"] for a in assignments_data))

        audit_q = await async_supabase(
            lambda: supabase.table("audit_log").select("user_id, created_at").order("created_at", desc=True).limit(10000).execute()
        )
        audit_entries: list[dict[str, Any]] = cast(list[dict[str, Any]], audit_q.data) if audit_q and audit_q.data else []

        today = datetime.utcnow().date()
        last_7d = today - timedelta(days=7)
        last_30d = today - timedelta(days=30)

        dau_users: set[str] = set()
        wau_users: set[str] = set()
        mau_users: set[str] = set()
        daily_active: dict[str, int] = {}

        for entry in audit_entries:
            uid = str(entry.get("user_id", ""))
            created = entry.get("created_at", "")
            if created:
                try:
                    d = datetime.fromisoformat(str(created).replace("Z", "+00:00")).date()
                    key = d.isoformat()
                    daily_active[key] = daily_active.get(key, 0) + 1
                    if d == today:
                        dau_users.add(uid)
                    if d >= last_7d:
                        wau_users.add(uid)
                    if d >= last_30d:
                        mau_users.add(uid)
                except (ValueError, TypeError):
                    pass

        track_unique_users: set[str] = set()
        for e in self._events:
            uid = e.get("user_id", "")
            ts = e.get("timestamp", "")
            if uid and ts:
                try:
                    d = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
                    track_unique_users.add(uid)
                    if d == today:
                        dau_users.add(uid)
                    if d >= last_7d:
                        wau_users.add(uid)
                    if d >= last_30d:
                        mau_users.add(uid)
                except (ValueError, TypeError):
                    pass

        session_lengths = []
        for sid, entries in self._sessions.items():
            if len(entries) >= 2:
                try:
                    start = min(datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")) for e in entries)
                    end = max(datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")) for e in entries)
                    diff = (end - start).total_seconds()
                    if 0 < diff < 86400:
                        session_lengths.append(diff)
                except (ValueError, TypeError):
                    pass

        avg_session_seconds = round(sum(session_lengths) / len(session_lengths), 1) if session_lengths else 0

        crash_events = [e for e in self._events if e["event"] in ("error", "crash", "unhandled_error")]
        total_sessions = len(self._sessions) or 1
        crash_free_rate = round((1 - len(crash_events) / max(total_sessions, 1)) * 100, 1)

        dau = len(dau_users)
        wau = len(wau_users)
        mau = len(mau_users)

        total_tracked_users = len(track_unique_users)

        funnel_steps = [
            {"step": "total_users", "label": "Signed Up", "count": total_users},
            {"step": "broker_connected", "label": "Connected Broker", "count": broker_users},
            {"step": "strategy_assigned", "label": "Assigned Strategy", "count": assigned_users},
            {"step": "traded", "label": "Placed Trade", "count": traded_users},
            {"step": "live_traded", "label": "Live Trade", "count": live_traded_users},
        ]

        activation_rate = round((traded_users / max(total_users, 1)) * 100, 1)
        retention_rate = round((wau / max(mau, 1)) * 100, 1)

        event_counts: dict[str, int] = {}
        for e in self._events:
            event_counts[e["event"]] = event_counts.get(e["event"], 0) + 1

        return {
            "dau": dau,
            "wau": wau,
            "mau": mau,
            "total_users": total_users,
            "broker_users": broker_users,
            "traded_users": traded_users,
            "live_traded_users": live_traded_users,
            "assigned_users": assigned_users,
            "activation_rate": activation_rate,
            "retention_rate": retention_rate,
            "avg_session_seconds": avg_session_seconds,
            "crash_free_rate": crash_free_rate,
            "crash_events_count": len(crash_events),
            "total_sessions": total_sessions,
            "total_tracked_events": len(self._events),
            "total_tracked_users": total_tracked_users,
            "funnel": funnel_steps,
            "daily_active_users": dict(sorted(daily_active.items(), reverse=True)[:30]),
            "event_counts": event_counts,
        }
