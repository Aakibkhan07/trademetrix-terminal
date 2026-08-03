"""Strategy State Manager — durable checkpoints of running strategies.

Writes per-strategy runtime state to the ``execution_checkpoints`` store
(kind ``strategy_runtime``) so recovery can restart RUNNING/PAUSED strategies
after a process restart with identical spec + restart counters. Fail-open: a
broken store never blocks the runtime.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from strategy_runtime.models import RuntimeState, StrategySpec

logger = logging.getLogger(__name__)

KIND = "strategy_runtime"
VERSION = 1

RECOVERY_SKIP_STATES = frozenset({RuntimeState.STOPPED, RuntimeState.FAILED, RuntimeState.CREATED})


class StrategyStateStore:
    def __init__(self) -> None:
        self._store: Any | None = None  # CheckpointStore (supabase or in-memory)

    def configure(self, store: Any | None) -> None:
        self._store = store

    @property
    def configured(self) -> bool:
        return self._store is not None

    async def save(self, record: Any) -> None:
        store = self._store
        if store is None:
            return
        body = {
            "version": VERSION,
            "state": record.state.value,
            "restart_count": record.restart_count,
            "started_at": record.started_at,
            "stopped_at": record.stopped_at,
            "paused_reason": record.paused_reason,
            "spec": record.spec.checkpoint(),
            "saved_at": datetime.now(UTC).isoformat(),
        }
        try:
            await store.upsert(record.spec.user_id, KIND, record.spec.strategy_id, body)
        except Exception as e:
            logger.warning("Runtime checkpoint write failed for %s: %s", record.spec.strategy_id, e)

    async def remove(self, user_id: str, strategy_id: str) -> None:
        store = self._store
        if store is None:
            return
        try:
            await store.delete(user_id, KIND, strategy_id)
        except Exception as e:
            logger.warning("Runtime checkpoint delete failed for %s: %s", strategy_id, e)

    async def load_all(self) -> list[dict[str, Any]]:
        store = self._store
        if store is None:
            return []
        try:
            return await store.load(KIND)
        except Exception as e:
            logger.warning("Runtime checkpoints unreadable (recovery skipped): %s", e)
            return []

    async def load_ids(self) -> set[str]:
        rows = await self.load_all()
        return {str(row.get("key", "")) for row in rows}
