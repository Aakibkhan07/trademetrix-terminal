import asyncio
import logging
from collections.abc import Callable
from typing import Any

from execution.models import ExecutionEvent

logger = logging.getLogger(__name__)


_pending_tasks: set[asyncio.Task] = set()


def fire_and_forget(coro_or_future, *, loop=None) -> asyncio.Task:
    task = asyncio.ensure_future(coro_or_future, loop=loop)
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)

    def _log_error(fut):
        if fut.done() and not fut.cancelled():
            exc = fut.exception()
            if exc:
                logger.error("Fire-and-forget task failed: %s", exc, exc_info=exc)

    task.add_done_callback(_log_error)
    return task


async def cancel_pending_tasks():
    for task in list(_pending_tasks):
        task.cancel()
    _pending_tasks.clear()


class ExecutionEventBus:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: str, callback: Callable[[ExecutionEvent], Any]) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        if event_type in self._subscribers:
            self._subscribers[event_type] = [cb for cb in self._subscribers[event_type] if cb is not callback]
            if not self._subscribers[event_type]:
                del self._subscribers[event_type]

    async def publish(self, event: ExecutionEvent) -> None:
        callbacks = self._subscribers.get(event.event_type, []) + self._subscribers.get("*", [])
        for cb in callbacks:
            try:
                if hasattr(cb, "__call__"):
                    result = cb(event)
                    if hasattr(result, "__await__"):
                        await result
            except Exception as e:
                logger.error("Event bus callback error for %s: %s", event.event_type, e)

    def clear(self) -> None:
        self._subscribers.clear()


execution_event_bus = ExecutionEventBus()
