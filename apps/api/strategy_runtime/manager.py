"""Strategy Runtime Manager — the runtime orchestration facade.

Owns the registry, tick dispatcher, scheduler, event router, state store and
observability; implements every lifecycle verb (start/stop/pause/resume/restart),
manual + broker + session event handling, recovery hooks and the health surface.
Strategies execute on the frozen Execution Engine path (``engine.gate``), so the
Risk Engine, paper routing and the engine's accounting/PnL all apply unchanged.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from strategy_runtime.dispatchers import EventRouter, TickDispatcher
from strategy_runtime.models import RuntimeState, StrategySpec, StrategyTrigger, utc_now
from strategy_runtime.observability import runtime_observability
from strategy_runtime.registry import RuntimeRecord, RuntimeRegistry
from strategy_runtime.scheduler import StrategyScheduler
from strategy_runtime.state_machine import require_transition
from strategy_runtime.state_store import StrategyStateStore

logger = logging.getLogger(__name__)


def _publish_runtime_event(event_type: str, strategy_id: str, user_id: str, payload: dict | None = None) -> None:
    """Emit a legacy-bus event so the per-user SSE stream and web widgets see it."""
    try:
        from execution.event_bus import execution_event_bus, fire_and_forget
        from execution.models import ExecutionEvent

        fire_and_forget(execution_event_bus.publish(ExecutionEvent(
            event_type=event_type,
            user_id=user_id,
            payload={"strategy_id": strategy_id, **(payload or {})},
        )))
    except Exception as e:
        logger.debug("Runtime event publish skipped (%s): %s", event_type, e)


class StrategyRuntimeManager:
    def __init__(self) -> None:
        self.runtime_state: RuntimeState = RuntimeState.CREATED
        self._registry = RuntimeRegistry()
        self._dispatcher = TickDispatcher()
        self._state_store = StrategyStateStore()
        self._observability = runtime_observability
        self._router = EventRouter(self, self._observability)
        self._scheduler = StrategyScheduler(self._router)
        self._initialized = False
        self._broker_subscribed = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._broker_states: dict[str, str] = {}

    # -- setup ---------------------------------------------------------------
    def configure_state_store(self, store: Any | None) -> None:
        self._state_store.configure(store)

    async def initialize(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._loop = asyncio.get_running_loop()
        await self._dispatcher.start()
        await self._scheduler.start()
        self._subscribe_broker_events()
        logger.info("Strategy Runtime v1.0 initialized (persistence=%s)",
                    "on" if self._state_store.configured else "off")

    def _subscribe_broker_events(self) -> None:
        if self._broker_subscribed:
            return
        try:
            from brokers.sdk.events import audit_bus

            audit_bus.subscribe(self._on_broker_event)
            self._broker_subscribed = True
        except Exception as e:
            logger.warning("Broker event subscription failed (non-fatal): %s", e)

    # -- lifecycle verbs -----------------------------------------------------
    async def start_strategy(self, spec: StrategySpec) -> dict:
        guard = await self._guard_start(spec)
        if guard:
            return guard
        existing = await self._registry.get(spec.strategy_id)
        if existing:
            if existing.state in (RuntimeState.STARTING, RuntimeState.RUNNING):
                return {"status": "already_running", "strategy_id": spec.strategy_id}
            require_transition(existing.state, RuntimeState.STARTING)
            record = existing
            record.spec = spec
        else:
            record = RuntimeRecord(spec)
            await self._registry.add(record)
        record.last_error = ""
        await self._start_running(record)
        return {"status": "started", "strategy_id": spec.strategy_id}

    async def _guard_start(self, spec: StrategySpec) -> dict | None:
        """Auto Trading v1.0 trading-mode safety gate (fail-closed).

        Refuses to start a spec whose mode is unknown, a live spec that was
        never explicitly confirmed, or any spec while a kill switch or an
        emergency stop is active for the user / globally.
        """
        from strategy_runtime.mode import ModeGuardError, assert_orders_allowed

        mode = (spec.mode or "").strip().lower()
        if mode not in ("paper", "live"):
            return {"status": "refused", "strategy_id": spec.strategy_id,
                    "reason": f"Unknown trading mode: {spec.mode!r}", "code": "MODE_UNKNOWN"}
        if mode == "live":
            if not spec.confirmed:
                return {"status": "refused", "strategy_id": spec.strategy_id,
                        "reason": "Live deployment requires explicit confirmation", "code": "LIVE_CONFIRMATION_REQUIRED"}
            if spec.is_paper is not False or not spec.broker or spec.broker == "paper":
                return {"status": "refused", "strategy_id": spec.strategy_id,
                        "reason": "Live mode requires a real broker account", "code": "MODE_NO_BROKER"}
        try:
            await assert_orders_allowed(spec.user_id)
        except ModeGuardError as e:
            return {"status": "refused", "strategy_id": spec.strategy_id,
                    "reason": e.message if hasattr(e, "message") else str(e), "code": e.code}
        return None

    async def _start_running(self, record: RuntimeRecord) -> None:
        from strategy_runtime.workers import StrategyWorker

        await self._stop_legacy(record.spec.strategy_id)
        record.state = RuntimeState.STARTING
        self._observability.record_lifecycle("STARTING", record.spec.strategy_id)
        worker = StrategyWorker(record, lifecycle=self)
        record.worker = worker
        self._dispatcher.attach(worker)
        await worker.start()
        record.state = RuntimeState.RUNNING
        record.started_at = utc_now()
        record.stopped_at = ""
        self._observability.set_running(record.spec.strategy_id, True)
        self._observability.record_lifecycle("RUNNING", record.spec.strategy_id)
        await self._state_store.save(record)
        self._sync_runner_stats(record)
        await self._write_strategy_runs(record, "running")
        await self._audit_log(record, "lifecycle",
                              f"Strategy started ({record.spec.mode}, {record.spec.symbol} {record.spec.interval}{' MTF ' + ','.join(record.spec.timeframes) if len(record.spec.timeframes) > 1 else ''})")
        _publish_runtime_event("StrategyStarted", record.spec.strategy_id, record.spec.user_id)
        logger.info("Strategy started: %s (%s)", record.spec.strategy_id, record.spec.mode)

    async def stop_strategy(self, strategy_id: str, user_id: str = "") -> dict:
        record = await self._registry.get(strategy_id)
        if record is None:
            return {"status": "not_found", "strategy_id": strategy_id}
        if user_id and record.spec.user_id != user_id:
            return {"status": "forbidden", "strategy_id": strategy_id}
        if record.state == RuntimeState.STOPPED:
            return {"status": "stopped", "strategy_id": strategy_id}
        require_transition(record.state, RuntimeState.STOPPED)
        await self._halt_worker(record)
        record.state = RuntimeState.STOPPED
        record.stopped_at = utc_now()
        record.worker = None
        self._observability.set_running(strategy_id, False)
        self._observability.record_lifecycle("STOPPED", strategy_id)
        await self._state_store.remove(record.spec.user_id, strategy_id)
        self._sync_runner_stats_stopped(record)
        await self._write_strategy_runs(record, "stopped")
        await self._audit_log(record, "lifecycle", "Strategy stopped")
        _publish_runtime_event("StrategyStopped", strategy_id, record.spec.user_id)
        logger.info("Strategy stopped: %s", strategy_id)
        return {"status": "stopped", "strategy_id": strategy_id}

    async def pause_strategy(self, strategy_id: str, user_id: str = "", reason: str = "manual") -> dict:
        record = await self._registry.get(strategy_id)
        if record is None:
            return {"status": "not_found", "strategy_id": strategy_id}
        if user_id and record.spec.user_id != user_id:
            return {"status": "forbidden", "strategy_id": strategy_id}
        require_transition(record.state, RuntimeState.PAUSED)
        if record.worker:
            record.worker.pause()
        record.state = RuntimeState.PAUSED
        record.paused_reason = reason
        self._observability.record_lifecycle("PAUSED", strategy_id)
        await self._state_store.save(record)
        self._sync_runner_stats(record)
        await self._audit_log(record, "lifecycle", f"Strategy paused ({reason})")
        _publish_runtime_event("StrategyPaused", strategy_id, record.spec.user_id,
                               payload={"reason": reason})
        logger.info("Strategy paused: %s (%s)", strategy_id, reason)
        return {"status": "paused", "strategy_id": strategy_id}

    async def resume_strategy(self, strategy_id: str, user_id: str = "") -> dict:
        record = await self._registry.get(strategy_id)
        if record is None:
            return {"status": "not_found", "strategy_id": strategy_id}
        if user_id and record.spec.user_id != user_id:
            return {"status": "forbidden", "strategy_id": strategy_id}
        require_transition(record.state, RuntimeState.RUNNING)
        if record.worker:
            record.worker.resume()
        record.state = RuntimeState.RUNNING
        record.paused_reason = ""
        self._observability.record_lifecycle("RUNNING", strategy_id)
        await self._state_store.save(record)
        self._sync_runner_stats(record)
        await self._audit_log(record, "lifecycle", "Strategy resumed")
        _publish_runtime_event("StrategyResumed", strategy_id, record.spec.user_id)
        logger.info("Strategy resumed: %s", strategy_id)
        return {"status": "resumed", "strategy_id": strategy_id}

    async def restart_strategy(self, strategy_id: str, user_id: str = "") -> dict:
        record = await self._registry.get(strategy_id)
        if record is None:
            return {"status": "not_found", "strategy_id": strategy_id}
        if user_id and record.spec.user_id != user_id:
            return {"status": "forbidden", "strategy_id": strategy_id}
        if record.state not in (RuntimeState.RUNNING, RuntimeState.PAUSED, RuntimeState.FAILED, RuntimeState.STOPPED):
            return {"status": "invalid_state", "strategy_id": strategy_id,
                    "state": record.state.value}
        # graceful halt (hot restart: no checkpoint removal)
        await self._halt_worker(record)
        record.state = RuntimeState.STOPPED
        await self._start_running(record)
        record.restart_count += 1
        self._observability.record_restart()
        await self._state_store.save(record)
        _publish_runtime_event("StrategyRestarted", strategy_id, record.spec.user_id,
                               payload={"restart_count": record.restart_count})
        logger.info("Strategy restarted: %s (restart #%d)", strategy_id, record.restart_count)
        return {"status": "restarted", "restart_count": record.restart_count, "strategy_id": strategy_id}

    async def _halt_worker(self, record: RuntimeRecord) -> None:
        worker = record.worker
        record.worker = None
        self._dispatcher.detach(worker) if worker else None
        await worker.stop() if worker else None
        await self._stop_legacy(record.spec.strategy_id)

    async def _stop_legacy(self, strategy_id: str) -> None:
        """Cancel any surviving legacy ``graph_strategy_runner`` task for this
        strategy (adopted strategies). Safe no-op when the runtime owns it."""
        try:
            from engine.graph_strategy_runner import _running_tasks, stop_graph_strategy

            task = _running_tasks.get(strategy_id)
            if task and not task.done():
                logger.info("Stopping legacy runner task for %s (runtime takeover)", strategy_id)
                await stop_graph_strategy(strategy_id)
        except Exception as e:
            logger.debug("Legacy runner stop skipped for %s: %s", strategy_id, e)

    # -- manual events -------------------------------------------------------
    async def manual_evaluate(self, strategy_id: str, user_id: str = "") -> dict:
        record = await self._registry.get(strategy_id)
        if record is None:
            return {"status": "not_found", "strategy_id": strategy_id}
        if user_id and record.spec.user_id != user_id:
            return {"status": "forbidden", "strategy_id": strategy_id}
        context = await self._build_context(record)
        if record.state != RuntimeState.RUNNING or not record.worker:
            return {"evaluated": False, "status": record.state.value, "context": context, "signal": None}
        signal = await record.worker.manual_evaluate(context)
        return {"evaluated": True, "status": record.state.value, "context": context,
                "signal": _signal_to_dict(signal)}

    async def _build_context(self, record: RuntimeRecord) -> dict:
        from strategy_runtime.context import build_execution_context

        worker = record.worker
        last_candle = None
        candles_by_tf = {}
        if worker:
            last_candle = worker.last_candle()
            candles_by_tf = {tf: [c] for tf, c in worker._mtf._last_candles.items()}
        return await build_execution_context(
            record.spec,
            candle=last_candle,
            candles=candles_by_tf,
            last_price=worker.last_price if worker else 0.0,
        )

    # -- views ---------------------------------------------------------------
    async def shutdown(self) -> None:
        """Graceful runtime shutdown: stop the scheduler, stop all workers
        (each persists its seen-ids + the manager persists checkpoints), then
        detach tick subscriptions."""
        await self._scheduler.stop()
        records = await self._registry.list_all()
        for record in records:
            if record.state == RuntimeState.RUNNING and record.worker:
                try:
                    await self._halt_worker(record)
                except Exception as e:
                    logger.warning("Worker halt failed for %s on shutdown: %s",
                                   record.spec.strategy_id, e)
        await self._dispatcher.shutdown()
        logger.info("Strategy Runtime shut down (%d records halted)", len(records))

    async def get_status(self, strategy_id: str, user_id: str = "") -> dict | None:
        record = await self._registry.get(strategy_id)
        if record is None:
            return None
        if user_id and record.spec.user_id != user_id:
            return None
        status = record.status()
        status.stats = record.stats
        body = status.model_dump()
        body["confirmed"] = record.spec.confirmed
        body["account"] = record.spec.account
        body["broker"] = record.spec.broker
        body["mode"] = record.spec.mode
        return body

    # -- Auto Trading v1.0: kill switch / emergency stop / reconcile -----------
    async def emergency_stop(self, user_id: str, reason: str = "", strategy_id: str = "") -> dict:
        """Emergency stop: trigger the user-level emergency flag, halt the
        matching strategy(s), and return what was affected."""
        from risk.kill_switch import kill_switch

        triggered = await kill_switch.trigger_emergency_stop(user_id or "system",
                                                             reason=reason or "User emergency stop")
        halted: list[str] = []
        if strategy_id:
            res = await self.pause_strategy(strategy_id, user_id=user_id, reason="emergency_stop")
            if res.get("status") in ("paused",):
                halted.append(strategy_id)
        else:
            for record in await self._registry.list_all():
                if record.spec.user_id != user_id:
                    continue
                if record.state == RuntimeState.RUNNING:
                    await self.pause_strategy(record.spec.strategy_id, user_id=user_id, reason="emergency_stop")
                    halted.append(record.spec.strategy_id)
        self._observability.record_lifecycle("EMERGENCY_STOP", strategy_id or "")
        _publish_runtime_event("EmergencyStop", strategy_id or "", user_id,
                               payload={"reason": reason, "halted": halted, "triggered": triggered})
        engaged = triggered or kill_switch.active(user_id)
        return {"status": "emergency_stopped" if engaged else "emergency_failed",
                "triggered": triggered, "halted": halted}

    async def release_emergency_stop(self, user_id: str, triggered_by: str = "") -> dict:
        from risk.kill_switch import kill_switch

        released = await kill_switch.release_emergency_stop(user_id or "local", triggered_by=triggered_by)
        engaged = kill_switch.active(user_id)
        _publish_runtime_event("EmergencyStopReleased", "", user_id, payload={"released": released})
        return {"status": "emergency_released" if (released or not engaged) else "release_failed",
                "released": released}

    async def pause_all(self, user_id: str, reason: str = "manual") -> dict:
        halted: list[str] = []
        for record in await self._registry.list_all():
            if record.spec.user_id != user_id:
                continue
            if record.state == RuntimeState.RUNNING:
                await self.pause_strategy(record.spec.strategy_id, user_id=user_id, reason=reason)
                halted.append(record.spec.strategy_id)
        return {"status": "paused", "halted": halted}

    async def reconcile(self, strategy_id: str, user_id: str = "") -> dict:
        """Trade reconciliation: compare runtime bookkeeping (orders placed /
        filled, current position) against the broker-connected truth for the
        strategy's symbol. Read-only reconciliation surface for Auto Trading."""
        record = await self._registry.get(strategy_id)
        if record is None:
            return {"status": "not_found", "strategy_id": strategy_id}
        if user_id and record.spec.user_id != user_id:
            return {"status": "forbidden", "strategy_id": strategy_id}
        broker = record.spec.broker or "paper"
        reconciliation = {
            "strategy_id": strategy_id,
            "mode": record.spec.mode,
            "broker": broker,
            "state": record.state.value,
            "runtime": {
                "orders_placed": record.stats.get("orders_placed", 0),
                "orders_filled": record.stats.get("orders_filled", 0),
                "orders_open": record.stats.get("orders_open", 0),
            },
            "checks": [],
        }
        try:
            from execution_engine.positions import position_manager

            positions = position_manager.get_positions(user_id, broker)
            open_positions = [p for p in (positions or []) if str(getattr(p, "symbol", "")).upper() == str(record.spec.symbol).upper()]
            reconciliation["broker_positions"] = {"open_positions": len(open_positions), "positions": open_positions}
            runtime_open = record.stats.get("orders_open", 0)
            reconciled = runtime_open == 0 and len(open_positions) >= 0
            mismatch = runtime_open > 0 != (len(open_positions) > 0)
            reconciliation["checks"].append({
                "name": "position_consistency",
                "ok": not mismatch,
                "detail": f"runtime_open_orders={runtime_open} broker_positions={len(open_positions)}",
            })
            reconciliation["reconciled"] = not mismatch
        except Exception as e:
            logger.warning("Reconcile read failed for %s: %s", strategy_id, e)
            reconciliation["checks"].append({"rule": "broker_read", "ok": False, "detail": str(e)[:200]})
            reconciliation["reconciled"] = False
        return reconciliation

    async def list_strategies(self, user_id: str = "") -> list[dict]:
        records = await self._registry.list_all()
        out = []
        for record in records:
            if user_id and record.spec.user_id != user_id:
                continue
            out.append(record.status().model_dump())
        return sorted(out, key=lambda s: s.get("started_at", ""), reverse=True)

    async def health(self) -> dict:
        records = await self._registry.list_all()
        by_state: dict[str, int] = {}
        for r in records:
            by_state[r.state.value] = by_state.get(r.state.value, 0) + 1
        running = sorted(r.spec.strategy_id for r in records if r.state == RuntimeState.RUNNING)
        return {
            "status": "healthy",
            "runtime_state": self.runtime_state.value,
            "strategies_total": len(records),
            "strategies_by_state": by_state,
            "strategies_running": len(running),
            "running_list": running,
            "scheduler_active": self._scheduler._running,
            "broker_states": dict(self._broker_states),
            "metrics": self._observability.snapshot(),
        }

    # -- runtime events (scheduler / broker / manual) --------------------------
    async def emit_event(self, kind: str, payload: dict | None = None) -> None:
        await self._router.emit(kind, payload=payload or {})

    async def _on_session_open(self) -> None:
        _publish_runtime_event("SessionOpen", "", "")
        for record in await self._registry.list_all():
            if record.spec.trigger == StrategyTrigger.MARKET_OPEN and record.state in (
                RuntimeState.CREATED, RuntimeState.STOPPED,
            ):
                await self.start_strategy(record.spec)

    async def _on_session_close(self) -> None:
        _publish_runtime_event("SessionClose", "", "")
        for record in await self._registry.list_all():
            if record.spec.trigger == StrategyTrigger.MARKET_CLOSE and record.state in (
                RuntimeState.RUNNING, RuntimeState.PAUSED,
            ):
                await self.stop_strategy(record.spec.strategy_id)

    async def _on_time_trigger(self, strategy_id: str) -> None:
        record = await self._registry.get(strategy_id)
        if record is None or record.state != RuntimeState.RUNNING or not record.worker:
            return
        self._observability.record_event("time")
        await record.worker.time_tick()

    async def _on_broker_disconnect(self, broker: str) -> None:
        self._broker_states[broker] = "disconnected"
        for record in await self._registry.list_all():
            if record.spec.broker == broker and record.state == RuntimeState.RUNNING:
                await self.pause_strategy(record.spec.strategy_id, reason="broker_disconnect")
        _publish_runtime_event("BrokerDisconnected", "", "", payload={"broker": broker})

    async def _on_broker_reconnect(self, broker: str) -> None:
        self._broker_states[broker] = "connected"
        for record in await self._registry.list_all():
            if record.spec.broker == broker and record.paused_reason == "broker_disconnect":
                await self.resume_strategy(record.spec.strategy_id)

    async def _on_manual_event(self, strategy_id: str, user_id: str, payload: dict) -> None:
        await self.manual_evaluate(strategy_id, user_id)

    def _on_broker_event(self, event: Any) -> None:
        """Sync broker audit-bus callback → thread-safe lifecycle action."""
        try:
            kind = getattr(event, "kind", "")
            broker = getattr(event, "broker", "") or ""
            from brokers.sdk.events import BrokerEventKind

            payload = None
            if kind in (BrokerEventKind.WEBSOCKET_DISCONNECTED,):
                payload = "broker_disconnect"
            elif kind in (BrokerEventKind.WEBSOCKET_CONNECTED,):
                payload = "broker_reconnect"
            elif kind == BrokerEventKind.HEALTH_CHANGED:
                to = (getattr(event, "payload", None) or {}).get("to", "")
                payload = "broker_disconnect" if "DISCONNECTED" in str(to) or "AUTH" in str(to) else ("broker_reconnect" if "CONNECTED" in str(to) else None)
            if payload and self._loop:
                self._loop.call_soon_threadsafe(
                    asyncio.ensure_future, self._router.emit(payload, payload={"broker": broker})
                )
        except Exception as e:
            logger.debug("Broker event handling skipped: %s", e)

    # -- worker callbacks -----------------------------------------------------
    async def _record_evaluation(self, record: RuntimeRecord, latency_ms: float) -> None:
        self._observability.record_evaluation(latency_ms)
        self._sync_runner_stats(record)

    async def _record_error(self, record: RuntimeRecord, error: str) -> None:
        self._observability.record_error()

    async def _on_worker_failed(self, strategy_id: str, error: str) -> None:
        record = await self._registry.get(strategy_id)
        if record is None:
            return
        if record.worker:
            self._dispatcher.detach(record.worker)
            record.worker = None
        if record.state != RuntimeState.FAILED:
            record.state = RuntimeState.FAILED
            self._observability.set_running(strategy_id, False)
            self._observability.record_lifecycle("FAILED", strategy_id)
        await self._state_store.remove(record.spec.user_id, strategy_id)
        self._sync_runner_stats(record)
        self._sync_runner_stats_stopped(record)
        await self._audit_log(record, "error", f"Strategy failed: {error[:500]}", level="error",
                              detail={"error": error[:500]})
        _publish_runtime_event("RuntimeError", strategy_id, record.spec.user_id,
                               payload={"error": error[:500]})
        logger.error("Strategy failed: %s: %s", strategy_id, error)

    # -- audit + observability plumbing --------------------------------------
    async def _audit_log(self, record: RuntimeRecord, kind: str, message: str,
                         level: str = "info", detail: dict | None = None) -> None:
        try:
            from builder.logs import record as log_record

            await log_record(record.spec.strategy_id, kind, message, level=level,
                             user_id=record.spec.user_id, detail=detail or {})
        except Exception:
            pass

    async def _write_strategy_runs(self, record: RuntimeRecord, status: str) -> None:
        try:
            from core.db import async_supabase, get_supabase

            supabase = get_supabase()
            if status == "running":
                await async_supabase(lambda: supabase.table("strategy_runs").insert({
                    "user_id": record.spec.user_id,
                    "strategy_id": record.spec.strategy_id,
                    "broker": record.spec.broker or "graph",
                    "mode": "GRAPH",
                    "symbols": [record.spec.symbol],
                    "status": "running",
                    "started_at": utc_now(),
                }).execute())
            else:
                await async_supabase(lambda: supabase.table("strategy_runs").update({
                    "status": "stopped",
                    "stopped_at": utc_now(),
                }).eq("strategy_id", record.spec.strategy_id).eq("status", "running").execute())
        except Exception as e:
            logger.warning("strategy_runs row for %s skipped (runner continues): %s",
                           record.spec.strategy_id, e)

    def _sync_runner_stats(self, record: RuntimeRecord) -> None:
        try:
            from engine.graph_strategy_runner import _runtime_stats

            stats = _runtime_stats(record.spec.strategy_id)
            stats.update({
                "status": record.state.value.lower(),
                "user_id": record.spec.user_id,
                "started_at": record.started_at,
                "stopped_at": record.stopped_at,
                "symbol": record.spec.symbol,
                "interval": record.spec.interval,
                "mode": record.spec.mode,
                "capital": record.spec.quantity * 0.0,
                "candles_processed": record.stats.get("candles_processed", 0),
                "signals": record.stats.get("signals", 0),
                "orders_placed": record.stats.get("orders_placed", 0),
                "orders_filled": record.stats.get("orders_filled", 0),
                "orders_rejected": record.stats.get("orders_rejected", 0),
                "errors": record.stats.get("errors", 0),
                "last_error": record.last_error,
                "last_activity": record.last_activity,
                "avg_latency_ms": record.stats.get("avg_latency_ms", 0.0),
                "latency_samples": record.stats.get("latency_samples", 0),
            })
        except Exception as e:
            logger.debug("runner stats sync skipped for %s: %s", record.spec.strategy_id, e)

    def _sync_runner_stats_stopped(self, record: RuntimeRecord) -> None:
        try:
            from engine.graph_strategy_runner import _runtime_stats

            stats = _runtime_stats(record.spec.strategy_id)
            stats["status"] = "stopped"
            stats["stopped_at"] = record.stopped_at
            stats["last_activity"] = utc_now()
        except Exception:
            pass


def _signal_to_dict(signal: Any | None) -> dict | None:
    if signal is None:
        return None
    if hasattr(signal, "model_dump"):
        return signal.model_dump(mode="json")
    return {"orders": len(getattr(signal, "orders", [])), "reason": getattr(signal, "reason", "")}


strategy_runtime_manager = StrategyRuntimeManager()