"""Strategy lifecycle & execution logs.

In-memory ring buffer per strategy (survives API restarts via write-through
persistence when the builder_strategy_logs table exists; degrades gracefully
otherwise, same pattern as builder/manager.py).
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque

from builder.models import StrategyLogEntry
from core.db import async_supabase, get_supabase

logger = logging.getLogger(__name__)

MAX_LOGS_PER_STRATEGY = 500

_logs: dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_LOGS_PER_STRATEGY))
_logs_loaded = False


async def _ensure_db() -> None:
    global _logs_loaded
    if _logs_loaded:
        return
    _logs_loaded = True
    try:
        supabase = get_supabase()
        result = await async_supabase(lambda: supabase.table("builder_strategy_logs")
                                      .select("*").order("ts", desc=True).limit(1000).execute())
        for row in result.data or []:
            _logs.setdefault(row.get("strategy_id", ""), deque(maxlen=MAX_LOGS_PER_STRATEGY)).appendleft(row)
        if result.data:
            logger.info("StrategyLogs loaded %d entries from DB", len(result.data))
    except Exception as e:
        logger.warning("StrategyLogs DB load skipped: %s", e)


async def _persist(entry: StrategyLogEntry) -> None:
    try:
        supabase = get_supabase()
        row = entry.model_dump(mode="json")
        await async_supabase(lambda r=row: supabase.table("builder_strategy_logs").upsert(r, on_conflict="id").execute())
    except Exception as e:
        logger.debug("StrategyLog persist skipped: %s", e)


async def record(
    strategy_id: str,
    kind: str,
    message: str,
    level: str = "info",
    user_id: str = "",
    detail: dict | None = None,
) -> StrategyLogEntry:
    await _ensure_db()
    entry = StrategyLogEntry(
        strategy_id=strategy_id,
        user_id=user_id,
        kind=kind,
        level=level,
        message=message,
        detail=detail or {},
    )
    _logs[strategy_id].append(entry)
    await _persist(entry)
    return entry


async def get_logs(strategy_id: str, limit: int = 200) -> list[dict]:
    await _ensure_db()
    entries = list(_logs.get(strategy_id, []))
    entries.reverse()
    return [e.model_dump(mode="json") if hasattr(e, "model_dump") else e for e in entries[-limit:]]
