"""Runtime Recovery — idempotent startup restoration.

Rehydrates strategy runtime state from the checkpoint store after a process
restart: restarts RUNNING strategies from their persisted spec, restores
PAUSED strategies as paused (post-start pause), preserves restart counters,
and can "adopt" strategies the legacy runtime already restarted. Recovery is
deterministic (checkpoint -> spec -> same start path), idempotent (already
running → adopt; no duplicate workers), and fail-open (never blocks startup).
"""
from __future__ import annotations

import logging
import time
from typing import Any

from strategy_runtime.models import RuntimeState, StrategySpec
from strategy_runtime.state_store import RECOVERY_SKIP_STATES

logger = logging.getLogger(__name__)


class RuntimeRecovery:
    def __init__(self, manager: Any) -> None:
        self._manager = manager

    async def recover(self) -> dict[str, Any]:
        result = {
            "restored": 0,
            "adopted": 0,
            "skipped": 0,
            "paused": 0,
            "errors": 0,
            "elapsed_ms": 0.0,
        }
        start = time.monotonic()
        self._manager.runtime_state = RuntimeState.RECOVERING
        try:
            rows = await self._manager._state_store.load_all()
            for row in rows:
                try:
                    data = row.get("data") or {}
                    spec = StrategySpec(**(data.get("spec") or {}))
                    state = RuntimeState(data.get("state", "RUNNING"))
                    restart_count = int(data.get("restart_count", 0) or 0)
                    if state in RECOVERY_SKIP_STATES:
                        result["skipped"] += 1
                        continue
                    if await self._manager._registry.get(spec.strategy_id) is not None:
                        result["skipped"] += 1
                        continue
                    if self._already_running(spec.strategy_id):
                        record = await self._adopt(spec, restart_count)
                        if record:
                            result["adopted"] += 1
                        else:
                            result["skipped"] += 1
                        continue
                    outcome = await self._manager.start_strategy(spec)
                    if outcome.get("status") == "started":
                        result["restored"] += 1
                        record = await self._manager._registry.get(spec.strategy_id)
                        if record:
                            record.restart_count = max(record.restart_count, restart_count) + 1
                        if state == RuntimeState.PAUSED:
                            await self._manager.pause_strategy(
                                spec.strategy_id, reason="restored_paused"
                            )
                            result["paused"] += 1
                    else:
                        result["skipped"] += 1
                except Exception as e:
                    logger.warning("Runtime recovery failed for %s: %s", row.get("key", ""), e)
                    result["errors"] += 1
            result["elapsed_ms"] = round((time.monotonic() - start) * 1000, 2)
            self._manager.runtime_state = RuntimeState.RECOVERED
            runtime_observability.record_recovery(result["elapsed_ms"])
            logger.info(
                "Strategy Runtime recovery complete: %s",
                {k: result[k] for k in ("restored", "adopted", "skipped", "paused", "errors", "elapsed_ms")},
            )
        except Exception as e:  # recovery must never block startup
            result["errors"] += 1
            logger.warning("Strategy Runtime recovery aborted (non-fatal): %s", e)
            self._manager.runtime_state = RuntimeState.RECOVERED
        return result

    def _already_running(self, strategy_id: str) -> bool:
        """Adopt strategies the legacy/independent recovery already started."""
        try:
            from engine.graph_strategy_runner import _running_tasks

            return strategy_id in _running_tasks and not _running_tasks[strategy_id].done()
        except Exception:
            return False

    async def _adopt(self, spec: StrategySpec, restart_count: int) -> Any:
        from strategy_runtime.registry import RuntimeRecord

        record = RuntimeRecord(spec)
        record.state = RuntimeState.RUNNING
        record.restart_count = restart_count
        record.started_at = spec.created_at
        await self._manager._registry.add(record)
        self._manager._observability.set_running(spec.strategy_id, True)
        logger.info("Runtime recovery adopted already-running strategy %s", spec.strategy_id)
        return record


# re-export for symmetric imports inside recovery (avoids a manager import)
from strategy_runtime.observability import runtime_observability  # noqa: E402