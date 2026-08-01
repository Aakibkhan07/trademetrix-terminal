import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

from core.cache import cache
from oms.models import OrderQueueItem, OrderQueueStats
from oms.observability import oms_metrics

logger = logging.getLogger(__name__)

QUEUE_KEY = "oms:order_queue"


def _serialize(item: OrderQueueItem) -> str:
    return json.dumps(item.model_dump(mode="json"))


class OrderQueue:
    """Redis-backed FIFO queue with delayed retry support.

    Cross-process safe: enqueues/dequeues are atomic Redis list operations, so
    any process can enqueue and any worker process can dequeue. Retries carry a
    `next_retry_at` timestamp; items not yet due are requeued at the tail.
    """

    def __init__(self, key: str = QUEUE_KEY):
        self._key = key

    async def _redis(self):
        return await cache.get_redis()

    async def enqueue(self, item: OrderQueueItem) -> None:
        r = await self._redis()
        if not r:
            logger.warning("Redis unavailable — order %s not queued", item.oms_order_id)
            return
        try:
            await r.rpush(self._key, _serialize(item))
            await self._record_depth(r)
            logger.debug("Order %s enqueued (priority=%d)", item.oms_order_id, item.priority)
        except Exception as e:
            logger.error("Failed to enqueue order %s: %s", item.oms_order_id, e)

    async def enqueue_retry(self, item: OrderQueueItem, delay_seconds: float = 5.0) -> None:
        item.retry_count += 1
        item.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        await self.enqueue(item)
        logger.info("Order %s scheduled for retry at %s (attempt %d)", item.oms_order_id, item.next_retry_at, item.retry_count)

    async def dequeue(self) -> OrderQueueItem | None:
        r = await self._redis()
        if not r:
            return None
        try:
            raw = await r.blpop(self._key, timeout=0.1)
            if not raw:
                return None
            item = OrderQueueItem(**json.loads(raw[1]))
            if item.next_retry_at and item.next_retry_at > datetime.now(UTC):
                await r.rpush(self._key, raw[1])
                return None
            await self._record_depth(r)
            return item
        except Exception as e:
            logger.error("Failed to dequeue order: %s", e)
            return None

    async def remove(self, oms_order_id: str) -> bool:
        r = await self._redis()
        if not r:
            return False
        try:
            removed = 0
            start = 0
            while True:
                chunk = await r.lrange(self._key, start, start + 50)
                if not chunk:
                    break
                for raw in chunk:
                    try:
                        item = OrderQueueItem(**json.loads(raw))
                    except Exception:
                        continue
                    if item.oms_order_id == oms_order_id:
                        count = await r.lrem(self._key, 1, raw)
                        removed += count
                        break
                if removed:
                    break
                start += 50
            return removed > 0
        except Exception as e:
            logger.error("Failed to remove order %s from queue: %s", oms_order_id, e)
            return False

    async def complete(self, oms_order_id: str) -> None:
        pass

    async def stats(self) -> OrderQueueStats:
        r = await self._redis()
        if not r:
            return OrderQueueStats()
        try:
            depth = await r.llen(self._key)
            retry_count = 0
            oldest = None
            chunk = await r.lrange(self._key, 0, -1)
            for raw in chunk:
                try:
                    item = OrderQueueItem(**json.loads(raw))
                except Exception:
                    continue
                retry_count += item.retry_count
                if oldest is None or item.enqueued_at < oldest:
                    oldest = item.enqueued_at
            return OrderQueueStats(
                total_pending=depth,
                total_queued=depth,
                total_processing=0,
                queue_depth=depth,
                retry_count=retry_count,
                oldest_enqueued=oldest,
            )
        except Exception as e:
            logger.error("Queue stats failed: %s", e)
            return OrderQueueStats()

    async def clear(self) -> None:
        r = await self._redis()
        if not r:
            return
        try:
            await r.delete(self._key)
        except Exception as e:
            logger.error("Queue clear failed: %s", e)

    async def _record_depth(self, r) -> None:
        try:
            depth = await r.llen(self._key)
            oms_metrics.record_queue_depth(depth)
        except Exception:
            pass


order_queue = OrderQueue()
