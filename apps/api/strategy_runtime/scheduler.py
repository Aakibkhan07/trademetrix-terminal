"""Strategy Scheduler — time-based triggers + session edge detection.

- Every 30s: detects market session open/close edges and emits session events
  through the EventRouter (MARKET_OPEN / MARKET_CLOSE strategies).
- Every 30s: fires EVERY_MINUTE / EVERY_5_MINUTES / CRON triggers for the
  registered strategies (time events).
Injected clock keeps the scheduler deterministic for tests.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from strategy_runtime.models import StrategyTrigger

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
POLL_SECONDS = 30


class StrategyScheduler:
    def __init__(self, router: Any, now_fn: Callable[[], datetime] | None = None) -> None:
        self._router = router
        self._now_fn = now_fn or (lambda: datetime.now(IST))
        self._task: asyncio.Task | None = None
        self._running = False
        self._was_open: bool | None = None
        self._last_minute: dict[str, int] = {}

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("StrategyScheduler started")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("StrategyScheduler stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._tick_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("StrategyScheduler loop error: %s", e)
            await asyncio.sleep(POLL_SECONDS)

    async def _tick_once(self) -> None:
        now = self._now_fn()
        is_open = self._market_open()
        if self._was_open is not None and is_open != self._was_open:
            await self._router.emit("session_open" if is_open else "session_close")
        self._was_open = is_open

        for record in await self._router._manager._registry.list_all():
            trigger = record.spec.trigger
            if trigger == StrategyTrigger.EVERY_MINUTE:
                minute = now.hour * 60 + now.minute
                if self._last_minute.get(record.spec.strategy_id) != minute:
                    self._last_minute[record.spec.strategy_id] = minute
                    await self._router.emit("time", strategy_id=record.spec.strategy_id)
            elif trigger == StrategyTrigger.EVERY_5_MINUTES:
                if now.minute % 5 == 0:
                    minute = now.hour * 60 + now.minute
                    if self._last_minute.get(record.spec.strategy_id) != minute:
                        self._last_minute[record.spec.strategy_id] = minute
                        await self._router.emit("time", strategy_id=record.spec.strategy_id)
            elif trigger == StrategyTrigger.CRON:
                if self._cron_matches(record.spec.cron_expression, now):
                    minute = now.hour * 60 + now.minute
                    if self._last_minute.get(record.spec.strategy_id) != minute:
                        self._last_minute[record.spec.strategy_id] = minute
                        await self._router.emit("time", strategy_id=record.spec.strategy_id)

    def _market_open(self) -> bool:
        try:
            from market.status import market_status_service

            return market_status_service.is_market_open()
        except Exception:
            return False

    @staticmethod
    def _cron_matches(expression: str, dt: datetime) -> bool:
        if not expression:
            return False
        parts = expression.strip().split()
        if len(parts) < 5:
            return False
        return _field(parts[0], dt.minute) and _field(parts[1], dt.hour)


def _field(pattern: str, value: int) -> bool:
    if pattern == "*":
        return True
    if "/" in pattern:
        base, step = pattern.split("/", 1)
        try:
            step = int(step)
        except ValueError:
            return False
        if base == "*":
            return value % step == 0
        try:
            return value >= int(base) and (value - int(base)) % step == 0
        except ValueError:
            return False
    try:
        return int(pattern) == value
    except ValueError:
        return False
