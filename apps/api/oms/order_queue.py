import asyncio
import heapq
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from oms.models import OrderQueueItem, OrderQueueStats
from oms.observability import oms_metrics

logger = logging.getLogger(__name__)


class OrderQueue:
    def __init__(self):
        self._fifo: list[OrderQueueItem] = []
        self._priority: list[tuple[int, int, OrderQueueItem]] = []
        self._retry: list[tuple[datetime, OrderQueueItem]] = []
        self._counter = 0
        self._processing: set[str] = set()
        self._lock = asyncio.Lock()

    async def enqueue(self, item: OrderQueueItem) -> None:
        async with self._lock:
            self._fifo.append(item)
            heapq.heappush(self._priority, (-item.priority, self._counter, item))
            self._counter += 1
            oms_metrics.record_queue_depth(len(self._fifo))
            logger.debug("Order %s enqueued (priority=%d)", item.oms_order_id, item.priority)

    async def enqueue_retry(self, item: OrderQueueItem, delay_seconds: float = 5.0) -> None:
        async with self._lock:
            item.retry_count += 1
            retry_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
            item.next_retry_at = retry_at
            heapq.heappush(self._retry, (retry_at, item))
            logger.info("Order %s scheduled for retry at %s (attempt %d)", item.oms_order_id, retry_at, item.retry_count)

    async def dequeue(self) -> OrderQueueItem | None:
        async with self._lock:
            now = datetime.now(UTC)
            while self._retry and self._retry[0][0] <= now:
                _, item = heapq.heappop(self._retry)
                if item.oms_order_id not in self._processing:
                    self._processing.add(item.oms_order_id)
                    oms_metrics.record_queue_depth(len(self._fifo) + len(self._retry))
                    return item

            while self._priority:
                _, _, item = heapq.heappop(self._priority)
                if item.oms_order_id not in self._processing:
                    self._processing.add(item.oms_order_id)
                    self._fifo = [i for i in self._fifo if i.oms_order_id != item.oms_order_id]
                    oms_metrics.record_queue_depth(len(self._fifo) + len(self._retry))
                    return item

            return None

    async def remove(self, oms_order_id: str) -> None:
        async with self._lock:
            self._fifo = [i for i in self._fifo if i.oms_order_id != oms_order_id]
            self._priority = [p for p in self._priority if p[2].oms_order_id != oms_order_id]
            heapq.heapify(self._priority)
            self._retry = [r for r in self._retry if r[1].oms_order_id != oms_order_id]
            heapq.heapify(self._retry)
            self._processing.discard(oms_order_id)

    async def complete(self, oms_order_id: str) -> None:
        async with self._lock:
            self._processing.discard(oms_order_id)

    async def stats(self) -> OrderQueueStats:
        async with self._lock:
            fifo_len = len(self._fifo)
            retry_len = len(self._retry)
            oldest = self._fifo[0].enqueued_at if self._fifo else None
            return OrderQueueStats(
                total_pending=fifo_len,
                total_queued=fifo_len + retry_len,
                total_processing=len(self._processing),
                queue_depth=fifo_len + retry_len,
                retry_count=sum(i.retry_count for _, i in self._retry),
                oldest_enqueued=oldest,
            )

    async def clear(self) -> None:
        async with self._lock:
            self._fifo.clear()
            self._priority.clear()
            self._retry.clear()
            self._processing.clear()


order_queue = OrderQueue()
