import asyncio
import logging
from datetime import UTC, datetime, timedelta

from core.db import async_supabase, get_supabase

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 3600

STALE_PENDING_MINUTES = 15


class CleanupService:
    def __init__(self):
        self._task: asyncio.Task | None = None

    def start_scheduler(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._cleanup_loop())
            logger.info("Order cleanup scheduler started (stale_pending=%dmin, check every %ds)", STALE_PENDING_MINUTES, CHECK_INTERVAL)

    def stop_scheduler(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
            logger.info("Order cleanup scheduler stopped")

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await self._cancel_stale_pending()
            except Exception as e:
                logger.error("Order cleanup error: %s", e)
            await asyncio.sleep(CHECK_INTERVAL)

    async def _cancel_stale_pending(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(minutes=STALE_PENDING_MINUTES)
        supabase = get_supabase()
        result = await async_supabase(lambda: supabase.table("orders").update({
            "status": "REJECTED", "message": "Stale pending — auto-cancelled",
        }).in_("status", ["PENDING", "OPEN"]).lt("updated_at", cutoff.isoformat()).execute())
        cancelled = len(result.data or [])
        if cancelled:
            logger.info("Auto-cancelled %d stale pending orders older than %dmin", cancelled, STALE_PENDING_MINUTES)
        return cancelled

    async def _delete_orders_before(self, cutoff: datetime, user_id: str | None = None) -> int:
        supabase = get_supabase()
        query = supabase.table("orders").delete().lt("created_at", cutoff.isoformat())
        if user_id:
            query = query.eq("user_id", user_id)
        result = await async_supabase(lambda: query.execute())
        deleted = len(result.data or [])
        if deleted:
            logger.info("Deleted %d orders from previous days", deleted)
        return deleted
