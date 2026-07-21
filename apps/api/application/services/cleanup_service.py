import asyncio
import logging
from datetime import UTC, datetime, timedelta

from core.config import settings
from core.db import async_supabase, get_supabase

logger = logging.getLogger(__name__)

ORDER_RETENTION_DAYS = getattr(settings, "order_retention_days", 30)
CHECK_INTERVAL = 86400


class CleanupService:
    def __init__(self):
        self._task: asyncio.Task | None = None

    def start_scheduler(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._cleanup_loop())
            logger.info("Order cleanup scheduler started (retention=%d days, check every %ds)", ORDER_RETENTION_DAYS, CHECK_INTERVAL)

    def stop_scheduler(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
            logger.info("Order cleanup scheduler stopped")

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await self._delete_old_orders()
            except Exception as e:
                logger.error("Order cleanup error: %s", e)
            await asyncio.sleep(CHECK_INTERVAL)

    async def _delete_old_orders(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=ORDER_RETENTION_DAYS)
        supabase = get_supabase()
        result = await async_supabase(lambda: supabase.table("orders").delete().lt("created_at", cutoff.isoformat()).execute())
        deleted = len(result.data or [])
        if deleted:
            logger.info("Deleted %d orders older than %s", deleted, cutoff.date())
        return deleted
