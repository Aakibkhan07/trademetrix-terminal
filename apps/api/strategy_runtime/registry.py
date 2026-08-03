"""Runtime Registry — one record per running strategy.

The registry stores identity/state/stats records only; each strategy owns one
worker task and one GraphStrategy instance (strategy isolation: no shared
mutable strategy state anywhere in the runtime).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from strategy_runtime.models import (
    RuntimeState,
    StrategyRuntimeStatus,
    StrategySpec,
    utc_now,
)

logger = logging.getLogger(__name__)

STATS_KEYS = (
    "candles_processed",
    "signals",
    "orders_placed",
    "orders_filled",
    "orders_rejected",
    "errors",
    "dropped_ticks",
    "ticks_processed",
    "avg_latency_ms",
    "latency_samples",
)


class RuntimeRecord:
    """Mutable per-strategy runtime state (owned by one worker task)."""

    def __init__(self, spec: StrategySpec) -> None:
        self.spec = spec
        self.state: RuntimeState = RuntimeState.CREATED
        self.started_at = ""
        self.stopped_at = ""
        self.restart_count = 0
        self.worker: Any | None = None  # StrategyWorker
        self.last_error = ""
        self.last_activity = ""
        self.paused_reason = ""
        self.stats: dict[str, Any] = {k: 0 for k in STATS_KEYS}

    def status(self) -> StrategyRuntimeStatus:
        return StrategyRuntimeStatus(
            strategy_id=self.spec.strategy_id,
            user_id=self.spec.user_id,
            state=self.state,
            symbol=self.spec.symbol,
            exchange=self.spec.exchange,
            interval=self.spec.interval,
            timeframes=list(self.spec.timeframes),
            mode=self.spec.mode,
            broker=self.spec.broker,
            account=self.spec.account,
            trigger=self.spec.trigger.value,
            started_at=self.started_at,
            stopped_at=self.stopped_at,
            restart_count=self.restart_count,
            worker_active=bool(self.worker and self.worker.is_alive()),
            last_error=self.last_error,
            last_activity=self.last_activity,
            paused_reason=self.paused_reason,
            last_price=float(self.worker.last_price if self.worker else 0.0),
            stats=dict(self.stats),
        )

    def touch(self) -> None:
        self.last_activity = utc_now()


class RuntimeRegistry:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._records: dict[str, RuntimeRecord] = {}

    async def add(self, record: RuntimeRecord) -> None:
        async with self._lock:
            self._records[record.spec.strategy_id] = record

    async def get(self, strategy_id: str) -> RuntimeRecord | None:
        async with self._lock:
            return self._records.get(strategy_id)

    async def remove(self, strategy_id: str) -> None:
        async with self._lock:
            self._records.pop(strategy_id, None)

    async def list_by_user(self, user_id: str) -> list[RuntimeRecord]:
        async with self._lock:
            return [r for r in self._records.values() if r.spec.user_id == user_id]

    async def list_all(self) -> list[RuntimeRecord]:
        async with self._lock:
            return list(self._records.values())

    async def running_ids(self) -> list[str]:
        async with self._lock:
            return [
                sid for sid, r in self._records.items()
                if r.state == RuntimeState.RUNNING
            ]
