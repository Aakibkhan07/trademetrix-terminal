import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, cast

from core.db import async_supabase, get_supabase

logger = logging.getLogger(__name__)

_SESSION_TTL_DAYS = 30


class AnalyticsService:
    """Beta Operations Mode analytics.

    All events persist to Supabase `analytics_events` (and feedback to
    `feedback_items`). If the DB is unavailable, events fall back to memory
    (fail-open) and are lost on restart — never crash the request path.
    """

    def __init__(self) -> None:
        self._fallback_events: list[dict] = []
        self._fallback_feedback: list[dict] = []

    # ── ingest ────────────────────────────────────────────────────────────

    async def track_event(
        self,
        event_name: str,
        properties: dict | None = None,
        session_id: str = "",
        user_id: str = "",
        timestamp: str | None = None,
    ) -> dict:
        if not event_name:
            raise ValueError("event is required")
        await self._insert(
            event_name,
            properties or {},
            session_id or "",
            user_id or None,
            timestamp,
        )
        return {"ok": True, "event": event_name}

    async def track_batch(self, events: list[dict]) -> dict:
        accepted = 0
        for e in events:
            name = (e.get("event") or e.get("type") or "").strip()
            if not name:
                continue
            await self._insert(
                name,
                e.get("properties") or {},
                e.get("session_id") or "",
                e.get("user_id") or None,
                e.get("timestamp") or None,
            )
            accepted += 1
        return {"ok": True, "accepted": accepted}

    async def record_server_event(
        self, user_id: str, event: str, properties: dict | None = None
    ) -> None:
        """Authoritative server-side value event (user_id from auth, never client)."""
        try:
            await self._insert(event, properties or {}, "", user_id or None, None)
        except Exception:
            logger.debug("analytics server event skipped: %s", event)

    async def _insert(
        self,
        event: str,
        properties: dict,
        session_id: str,
        user_id: str | None,
        timestamp: str | None,
    ) -> None:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        try:
            supabase = get_supabase()
            await async_supabase(
                lambda: supabase.table("analytics_events")
                .insert({
                    "event": event,
                    "properties": properties,
                    "session_id": session_id,
                    "user_id": user_id,
                    "created_at": ts,
                })
                .execute()
            )
        except Exception as e:
            logger.debug("analytics insert fallback (memory): %s", e)
            self._fallback_events.append({
                "event": event,
                "properties": properties,
                "session_id": session_id,
                "user_id": user_id,
                "created_at": ts,
            })

    # ── feedback ──────────────────────────────────────────────────────────

    async def submit_feedback(
        self,
        user,
        category: str,
        title: str,
        description: str,
        metadata: dict | None = None,
    ) -> dict:
        if not title and not description:
            raise ValueError("title or description is required")
        if category not in ("bug", "feature", "nps", "report"):
            category = "bug"
        row = {
            "user_id": user.id,
            "user_email": getattr(user, "email", "") or "",
            "full_name": getattr(user, "full_name", "") or "",
            "category": category,
            "title": title,
            "description": description,
            "metadata": metadata or {},
            "status": "new",
        }
        try:
            supabase = get_supabase()
            res = await async_supabase(
                lambda: supabase.table("feedback_items").insert(row).execute()
            )
            data = (res.data or [{}])[0] if res else {}
            return {"ok": True, "id": data.get("id")}
        except Exception as e:
            logger.debug("feedback insert fallback (memory): %s", e)
            self._fallback_feedback.append({**row, "id": len(self._fallback_feedback) + 1})
            return {"ok": True, "id": len(self._fallback_feedback)}

    async def list_feedback(
        self, category: str = "", status: str = "", limit: int = 500
    ) -> dict:
        try:
            supabase = get_supabase()
            q = supabase.table("feedback_items").select("*").order("created_at", desc=True).limit(limit)
            if category:
                q = q.eq("category", category)
            if status:
                q = q.eq("status", status)
            res = await async_supabase(lambda: q.execute())
            rows = cast(list[dict], res.data) if res and res.data else []
            return {"feedback": rows, "count": len(rows)}
        except Exception as e:
            logger.debug("feedback list fallback: %s", e)
            rows = self._fallback_feedback
            if category:
                rows = [r for r in rows if r.get("category") == category]
            if status:
                rows = [r for r in rows if r.get("status") == status]
            return {"feedback": rows, "count": len(rows)}

    async def update_feedback(self, feedback_id: int, status: str | None = None, notes: str | None = None) -> dict | None:
        patch: dict[str, Any] = {}
        if status:
            patch["status"] = status
        if notes is not None:
            patch["notes"] = notes
        if not patch:
            return None
        try:
            supabase = get_supabase()
            await async_supabase(
                lambda: supabase.table("feedback_items")
                .update(patch).eq("id", feedback_id).execute()
            )
            return {"ok": True}
        except Exception as e:
            logger.debug("feedback update fallback: %s", e)
            for f in self._fallback_feedback:
                if f.get("id") == feedback_id:
                    f.update(patch)
                    return {"ok": True}
            return None

    # ── queries ───────────────────────────────────────────────────────────

    async def list_events(self, event_filter: str | None = None, limit: int = 100) -> dict:
        events = await self._events_since(30)
        result = [e for e in events if not event_filter or e.get("event") == event_filter]
        return {"events": result[-limit:], "total": len(result)}

    async def _events_since(self, days: int) -> list[dict]:
        try:
            supabase = get_supabase()
            since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            res = await async_supabase(
                lambda: supabase.table("analytics_events")
                .select("event, session_id, user_id, properties, created_at")
                .gte("created_at", since)
                .limit(20000)
                .execute()
            )
            return cast(list[dict], res.data) if res and res.data else []
        except Exception as e:
            logger.debug("events query fallback: %s", e)
            return self._fallback_events

    async def get_funnel(self, steps: list[str], days: int = 30) -> dict:
        events = await self._events_since(days)
        per_step: dict[str, set[str]] = defaultdict(set)
        counts = {}
        for e in events:
            if e.get("event") in steps:
                per_step[e["event"]].add(str(e.get("user_id") or e.get("session_id") or ""))
        funnel = []
        entered: set[str] | None = None
        for step in steps:
            users = per_step.get(step, set())
            entered = users if entered is None else entered | users
            counts[step] = len(users)
            funnel.append({
                "step": step,
                "users": len(users),
                "cumulative": len(entered),
            })
        return {"steps": funnel, "days": days}

    async def get_retention(self, weeks: int = 8) -> dict:
        events = await self._events_since(weeks * 7 + 7)
        cohorts: dict[str, set[str]] = defaultdict(set)
        week_of: dict[str, str] = {}
        for e in events:
            uid = str(e.get("user_id") or e.get("session_id") or "")
            if not uid:
                continue
            ts = e.get("created_at", "")
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            wk = dt.isoformat()[:10]
            week_of[uid] = week_of.get(uid) or wk
            cohorts[wk].add(uid)
        sorted_weeks = sorted(cohorts.keys())[-weeks:]
        matrix = []
        for cw in sorted_weeks:
            base = cohorts[cw]
            if not base:
                continue
            row = {"cohort": cw, "users": len(base)}
            for offset, w2 in enumerate(sorted_weeks):
                if w2 < cw:
                    continue
                if w2 == cw:
                    row[f"w{offset}"] = 100.0
                else:
                    ret = sum(1 for u in base if week_of.get(u) and u in cohorts[w2] and week_of.get(u) != w2)
                    row[f"w{offset}"] = round(ret / len(base) * 100, 1) if base else 0.0
            matrix.append(row)
        return {"weeks": weeks, "cohorts": matrix}

    async def get_feature_usage(self, days: int = 30) -> dict:
        events = await self._events_since(days)
        counts: dict[str, int] = defaultdict(int)
        users: dict[str, set[str]] = defaultdict(set)
        for e in events:
            counts[e.get("event", "")] += 1
            uid = str(e.get("user_id") or e.get("session_id") or "")
            if uid:
                users[e.get("event", "")].add(uid)
        ranked = sorted(
            [{"event": k, "count": v, "users": len(users[k])} for k, v in counts.items()],
            key=lambda r: r["count"], reverse=True,
        )
        return {"days": days, "features": ranked}

    async def get_sessions(self, limit: int = 25, days: int = 7) -> dict:
        events = await self._events_since(days)
        agg: dict[str, dict] = {}
        for e in events:
            sid = e.get("session_id", "")
            if not sid:
                continue
            a = agg.setdefault(sid, {"session_id": sid, "count": 0, "first": None, "last": None, "pages": set()})
            a["count"] += 1
            ts = str(e.get("created_at", ""))
            if a["first"] is None or ts < a["first"]:
                a["first"] = ts
            if a["last"] is None or ts > a["last"]:
                a["last"] = ts
            if e.get("event") == "page.view":
                a["pages"].add(str((e.get("properties") or {}).get("path", "")))
        sessions = sorted(agg.values(), key=lambda s: s["last"] or "", reverse=True)[:limit]
        return {"sessions": sessions, "total": len(agg)}

    async def get_session_events(self, session_id: str, limit: int = 500) -> dict:
        try:
            supabase = get_supabase()
            res = await async_supabase(
                lambda: supabase.table("analytics_events")
                .select("*").eq("session_id", session_id)
                .order("created_at").limit(limit)
                .execute()
            )
            rows = cast(list[dict], res.data) if res and res.data else []
            return {"session_id": session_id, "events": rows, "count": len(rows)}
        except Exception as e:
            logger.debug("session events fallback: %s", e)
            rows = [e for e in self._fallback_events if e.get("session_id") == session_id]
            return {"session_id": session_id, "events": rows, "count": len(rows)}

    async def get_crashes(self, days: int = 30) -> dict:
        events = await self._events_since(days)
        crash_events = [
            e for e in events
            if e.get("event") in ("error", "crash", "unhandled_error", "api_error", "client_error")
        ]
        grouped: dict[str, dict] = {}
        for e in crash_events:
            props = e.get("properties") or {}
            key = str(props.get("key") or props.get("stack_hash") or props.get("path") or "unknown")
            g = grouped.setdefault(key, {"key": key, "count": 0, "first": None, "last": None, "sessions": set(), "message": str(props.get("message") or "")[:200]})
            g["count"] += 1
            ts = str(e.get("created_at", ""))
            if g["first"] is None or ts < g["first"]:
                g["first"] = ts
            if g["last"] is None or ts > g["last"]:
                g["last"] = ts
            if e.get("session_id"):
                g["sessions"].add(e["session_id"])
        crashes = sorted(
            [{"key": k, "count": v["count"], "first": v["first"], "last": v["last"],
              "sessions": list(v["sessions"])[:20], "message": v["message"]} for k, v in grouped.items()],
            key=lambda c: c["count"], reverse=True,
        )
        return {"days": days, "crashes": crashes, "total": len(crash_events)}

    async def get_admin_overview(self) -> dict:
        overview = {
            "dau": 0, "wau": 0, "mau": 0,
            "total_users": 0, "broker_users": 0, "traded_users": 0,
            "live_traded_users": 0, "assigned_users": 0,
            "activation_rate": 0.0, "retention_rate": 0.0,
            "avg_session_seconds": 0, "crash_free_rate": 100.0,
            "crash_events_count": 0, "total_sessions": 0,
            "total_tracked_events": 0, "total_tracked_users": 0,
            "funnel": [], "daily_active_users": {}, "event_counts": {},
        }
        try:
            supabase = get_supabase()

            profiles_q = await async_supabase(
                lambda: supabase.table("profiles").select("id, created_at").execute()
            )
            profiles = cast(list[dict], profiles_q.data) if profiles_q and profiles_q.data else []
            overview["total_users"] = len(profiles)

            brokers_q = await async_supabase(
                lambda: supabase.table("broker_credentials").select("user_id").execute()
            )
            brokers = cast(list[dict], brokers_q.data) if brokers_q and brokers_q.data else []
            overview["broker_users"] = len(set(b.get("user_id") for b in brokers))

            orders_q = await async_supabase(
                lambda: supabase.table("orders").select("user_id, is_paper").execute()
            )
            orders = cast(list[dict], orders_q.data) if orders_q and orders_q.data else []
            overview["traded_users"] = len(set(o.get("user_id") for o in orders))
            overview["live_traded_users"] = len(set(o.get("user_id") for o in orders if not o.get("is_paper", True)))

            events = await self._events_since(30)
            user_days: dict[str, set[str]] = defaultdict(set)
            active_by_day: dict[str, int] = defaultdict(int)
            sessions: dict[str, list[str]] = defaultdict(list)
            for e in events:
                uid = str(e.get("user_id") or "")
                sid = str(e.get("session_id") or "")
                ts = str(e.get("created_at", ""))
                try:
                    day = datetime.fromisoformat(ts.replace("Z", "+00:00")).date().isoformat()
                except (ValueError, TypeError):
                    continue
                if uid:
                    user_days[uid].add(day)
                    active_by_day[day] += 1
                if sid:
                    sessions[sid].append(ts)

            today = datetime.now(timezone.utc).date().isoformat()
            week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
            month_ago = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
            overview["dau"] = sum(1 for d in user_days.values() if today in d)
            overview["wau"] = sum(1 for d in user_days.values() if any(x >= week_ago for x in d))
            overview["mau"] = sum(1 for d in user_days.values() if any(x >= month_ago for x in d))
            overview["daily_active_users"] = dict(sorted(active_by_day.items(), reverse=True)[:30])

            total_users = max(overview["total_users"], 1)
            overview["activation_rate"] = round(overview["traded_users"] / total_users * 100, 1)
            overview["retention_rate"] = round(overview["wau"] / max(overview["mau"], 1) * 100, 1)
            overview["total_sessions"] = len(sessions)
            overview["total_tracked_events"] = len(events)
            overview["total_tracked_users"] = len(user_days)

            lens = []
            for s in sessions.values():
                if len(s) >= 2:
                    try:
                        d0 = datetime.fromisoformat(s[0].replace("Z", "+00:00"))
                        d1 = datetime.fromisoformat(s[-1].replace("Z", "+00:00"))
                        secs = (d1 - d0).total_seconds()
                        if 0 < secs < 86400:
                            lens.append(secs)
                    except (ValueError, TypeError):
                        pass
            overview["avg_session_seconds"] = round(sum(lens) / len(lens), 1) if lens else 0

            crash = await self.get_crashes(30)
            overview["crash_events_count"] = crash["total"]
            overview["crash_free_rate"] = round(
                (1 - crash["total"] / max(overview["total_sessions"], 1)) * 100, 1
            ) if overview["total_sessions"] else 100.0

            overview["funnel"] = [
                {"step": "total_users", "label": "Signed Up", "count": overview["total_users"]},
                {"step": "broker_connected", "label": "Connected Broker", "count": overview["broker_users"]},
                {"step": "traded", "label": "Placed Trade", "count": overview["traded_users"]},
                {"step": "live_traded", "label": "Live Trade", "count": overview["live_traded_users"]},
            ]
            overview["event_counts"] = [
                r for r in (await self.get_feature_usage(30))["features"][:15]
            ]
            return overview
        except Exception as e:
            logger.warning("admin overview degraded: %s", e)
            return overview
