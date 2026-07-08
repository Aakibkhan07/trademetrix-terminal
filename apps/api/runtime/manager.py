import asyncio
import hashlib
import logging
import time
from datetime import UTC, datetime, timezone
from typing import Any

from core.db import async_supabase, get_supabase
from core.models import Candle, Tick
from core.safe_query import async_safe_execute, async_safe_single, safe_execute
from execution.event_bus import execution_event_bus, ExecutionEvent, fire_and_forget
from execution.models import ExecutionRequest
from market.cache import market_cache
from market.data_socket import shared_socket
from market.status import market_status_service
from portfolio.manager import portfolio_manager
from runtime.context import RuntimeContext
from runtime.models import (
    RuntimeConfig,
    RuntimeMetrics,
    RuntimeSignal,
    SignalSide,
    StrategyPlugin,
    StrategyState,
    TriggerType,
)
from runtime.event_subscriber import runtime_event_subscriber
from runtime.observability import runtime_metrics
from runtime.registry import strategy_registry
from runtime.scheduler import scheduler
from strategies.base import BaseStrategy, SignalResult

logger = logging.getLogger(__name__)

VALID_TRANSITIONS: dict[StrategyState, set[StrategyState]] = {
    StrategyState.DRAFT: {StrategyState.READY, StrategyState.ARCHIVED},
    StrategyState.READY: {StrategyState.RUNNING, StrategyState.STOPPED, StrategyState.ARCHIVED},
    StrategyState.RUNNING: {StrategyState.PAUSED, StrategyState.STOPPED, StrategyState.FAILED},
    StrategyState.PAUSED: {StrategyState.RUNNING, StrategyState.STOPPED, StrategyState.READY},
    StrategyState.STOPPED: {StrategyState.READY, StrategyState.ARCHIVED},
    StrategyState.FAILED: {StrategyState.READY, StrategyState.STOPPED, StrategyState.ARCHIVED},
    StrategyState.ARCHIVED: set(),
}


def _signal_id(strategy_id: str) -> str:
    raw = f"{strategy_id}:{time.time_ns()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class RuntimeManager:
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
        self._configs: dict[str, RuntimeConfig] = {}
        self._contexts: dict[str, RuntimeContext] = {}
        self._evaluation_tasks: dict[str, asyncio.Task] = {}
        self._runtime_start = 0.0
        self._heartbeat_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        discovered = strategy_registry.discover()
        scheduler.register("_market_open", TriggerType.MARKET_OPEN, self._on_market_open)
        scheduler.register("_market_close", TriggerType.MARKET_CLOSE, self._on_market_close)
        await scheduler.start()
        runtime_event_subscriber.subscribe()
        if not self._heartbeat_task:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        await self._recover_running_strategies()
        logger.info("RuntimeManager initialized with %d discovered strategies", len(discovered))

    async def register_strategy(self, config: RuntimeConfig) -> bool:
        if config.strategy_key not in strategy_registry:
            logger.warning("Unknown strategy key: %s", config.strategy_key)
            return False

        strategy_registry.set_state(config.strategy_key, StrategyState.DRAFT)
        self._configs[config.strategy_id] = config
        self._contexts[config.strategy_id] = RuntimeContext(config)
        strategy_registry.enable(config.strategy_key)
        await self._persist_state(config.strategy_id, StrategyState.DRAFT)
        logger.info("Strategy registered: %s (%s)", config.strategy_id, config.strategy_key)
        await self._publish_event("StrategyRegistered", config.strategy_id, config.user_id)
        return True

    async def start_strategy(self, strategy_id: str) -> bool:
        config = self._configs.get(strategy_id)
        if not config:
            logger.warning("Strategy not found: %s", strategy_id)
            return False

        cls = strategy_registry.get_class(config.strategy_key)
        if not cls:
            return False

        current = strategy_registry.get_state(config.strategy_key)
        if StrategyState.RUNNING not in VALID_TRANSITIONS.get(current, set()):
            logger.warning("Cannot start %s from state %s", strategy_id, current)
            return False

        try:
            instance = cls(config.config.get("params", {}))
            await instance.on_start()
            strategy_registry.set_instance(config.strategy_key, instance)
            strategy_registry.set_state(config.strategy_key, StrategyState.RUNNING)
            await self._persist_state(config.strategy_id, StrategyState.RUNNING)
            runtime_metrics.set_strategy_state(config.strategy_key, "RUNNING")

            trigger = config.trigger
            scheduler.register(strategy_id, trigger, self._make_callback(strategy_id), config.interval)
            logger.info("Strategy started: %s with trigger %s", strategy_id, trigger)
            await self._publish_event("StrategyStarted", strategy_id, config.user_id)
            return True
        except Exception as e:
            logger.error("Failed to start strategy %s: %s", strategy_id, e)
            strategy_registry.set_state(config.strategy_key, StrategyState.FAILED)
            runtime_metrics.record_error(config.strategy_key)
            await self._publish_event("RuntimeError", strategy_id, config.user_id, error=str(e))
            return False

    async def stop_strategy(self, strategy_id: str) -> bool:
        config = self._configs.get(strategy_id)
        if not config:
            return False

        current = strategy_registry.get_state(config.strategy_key)
        if StrategyState.STOPPED not in VALID_TRANSITIONS.get(current, set()):
            return False

        scheduler.unregister(strategy_id)
        instance = strategy_registry.get_instance(config.strategy_key)
        if instance:
            try:
                await instance.on_stop()
            except Exception as e:
                logger.warning("Error stopping strategy instance %s: %s", getattr(instance, "config", {}).get("strategy_key", "unknown"), e)
        strategy_registry.set_state(config.strategy_key, StrategyState.STOPPED)
        strategy_registry.set_instance(config.strategy_key, None)
        await self._persist_state(config.strategy_id, StrategyState.STOPPED)
        runtime_metrics.set_strategy_state(config.strategy_key, "STOPPED")
        await self._publish_event("StrategyStopped", strategy_id, config.user_id)
        logger.info("Strategy stopped: %s", strategy_id)
        return True

    async def pause_strategy(self, strategy_id: str) -> bool:
        config = self._configs.get(strategy_id)
        if not config:
            return False
        current = strategy_registry.get_state(config.strategy_key)
        if StrategyState.PAUSED not in VALID_TRANSITIONS.get(current, set()):
            return False
        strategy_registry.set_state(config.strategy_key, StrategyState.PAUSED)
        await self._persist_state(config.strategy_id, StrategyState.PAUSED)
        runtime_metrics.set_strategy_state(config.strategy_key, "PAUSED")
        await self._publish_event("StrategyPaused", strategy_id, config.user_id)
        return True

    async def resume_strategy(self, strategy_id: str) -> bool:
        config = self._configs.get(strategy_id)
        if not config:
            return False
        current = strategy_registry.get_state(config.strategy_key)
        if StrategyState.RUNNING not in VALID_TRANSITIONS.get(current, set()):
            return False
        strategy_registry.set_state(config.strategy_key, StrategyState.RUNNING)
        await self._persist_state(config.strategy_id, StrategyState.RUNNING)
        runtime_metrics.set_strategy_state(config.strategy_key, "RUNNING")
        await self._publish_event("StrategyResumed", strategy_id, config.user_id)
        return True

    async def reload_strategy(self, strategy_id: str) -> bool:
        config = self._configs.get(strategy_id)
        if not config:
            return False
        await self.stop_strategy(strategy_id)
        success = strategy_registry.reload(config.strategy_key)
        if success:
            await self.start_strategy(strategy_id)
        return success

    async def evaluate(self, strategy_id: str, tick: Tick | None = None, candle: Candle | None = None) -> RuntimeSignal | None:
        config = self._configs.get(strategy_id)
        if not config:
            return None

        key = config.strategy_key
        if strategy_registry.get_state(key) != StrategyState.RUNNING:
            return None

        instance = strategy_registry.get_instance(key)
        if not instance:
            return None

        eval_start = time.monotonic()
        context = await self._contexts[strategy_id].build(tick, candle)

        try:
            if tick and hasattr(instance, "on_tick"):
                result = await instance.on_tick(tick)
            elif candle and hasattr(instance, "on_candle"):
                result = await instance.on_candle(candle)
            else:
                if hasattr(instance, "on_tick") and tick:
                    result = await instance.on_tick(tick)
                elif hasattr(instance, "on_candle") and candle:
                    result = await instance.on_candle(candle)
                else:
                    return None
        except Exception as e:
            logger.error("Evaluation error for %s: %s", strategy_id, e)
            runtime_metrics.record_error(key)
            strategy_registry.set_state(key, StrategyState.FAILED)
            await self._publish_event("RuntimeError", strategy_id, config.user_id, error=str(e))
            return None

        latency_ms = (time.monotonic() - eval_start) * 1000
        runtime_metrics.record_evaluation(key, latency_ms)

        if not result:
            return None

        signal = self._signal_from_result(result, config, latency_ms)
        runtime_metrics.record_signal(key)
        await self._publish_event("SignalGenerated", strategy_id, config.user_id, signal=signal.model_dump())
        return signal

    async def submit_signal(self, signal: RuntimeSignal) -> dict:
        config = self._configs.get(signal.strategy_id)
        if not config:
            return {"success": False, "error": "Strategy not registered"}

        if signal.side in (SignalSide.HOLD, SignalSide.IGNORE):
            return {"success": False, "reason": "HOLD/IGNORE signals not submitted"}

        req = ExecutionRequest(
            user_id=config.user_id,
            broker=config.broker,
            symbol=signal.symbol or config.symbol,
            exchange=signal.exchange or config.exchange,
            side=signal.side.value if signal.side in (SignalSide.BUY, SignalSide.SELL) else signal.side.value,
            order_type="MARKET",
            product=signal.product,
            quantity=signal.quantity,
            price=signal.price,
            strategy_id=config.strategy_id,
            source="strategy_runtime",
        )
        from execution.manager import ExecutionManager
        exec_mgr = ExecutionManager()
        result = await exec_mgr.place_order(req)
        return {
            "success": result.success,
            "execution_request_id": result.execution_request_id,
            "broker_order_id": result.broker_order_id,
            "message": result.message,
            "state": result.state.value if result.state else "",
        }

    async def get_status(self, strategy_id: str) -> dict | None:
        config = self._configs.get(strategy_id)
        if not config:
            return None
        key = config.strategy_key
        return {
            "strategy_id": strategy_id,
            "strategy_key": key,
            "state": strategy_registry.get_state(key).value,
            "symbol": config.symbol,
            "trigger": config.trigger.value,
            "interval": config.interval,
            "enabled": config.enabled,
            "broker": config.broker,
            "uptime": time.time() - self._runtime_start if self._runtime_start else 0,
        }

    async def health(self) -> dict:
        running = strategy_registry.list_running()
        enabled = strategy_registry.list_enabled()
        return {
            "status": "healthy",
            "strategies_registered": len(self._configs),
            "strategies_running": len(running),
            "strategies_enabled": len(enabled),
            "running_list": running,
            "scheduler_active": scheduler._running,
            "stats": runtime_metrics.stats,
        }

    def get_strategy_config(self, strategy_id: str) -> RuntimeConfig | None:
        return self._configs.get(strategy_id)

    def _make_callback(self, strategy_id: str) -> Any:
        async def callback(tick=None, candle=None):
            signal = await self.evaluate(strategy_id, tick=tick, candle=candle)
            if signal and signal.side not in (SignalSide.HOLD, SignalSide.IGNORE):
                await self.submit_signal(signal)
        return callback

    def _signal_from_result(self, result: SignalResult, config: RuntimeConfig, latency_ms: float) -> RuntimeSignal:
        if not result.orders:
            return RuntimeSignal(
                strategy_id=config.strategy_id,
                signal_id=_signal_id(config.strategy_id),
                side=SignalSide.HOLD,
                reason=result.reason,
            )
        order = result.orders[0]
        side_map = {
            "BUY": SignalSide.BUY,
            "SELL": SignalSide.SELL,
        }
        signal_side = side_map.get(order.side.value if hasattr(order.side, "value") else str(order.side), SignalSide.HOLD)
        return RuntimeSignal(
            strategy_id=config.strategy_id,
            signal_id=_signal_id(config.strategy_id),
            side=signal_side,
            confidence=1.0,
            reason=result.reason,
            symbol=order.symbol,
            exchange=order.exchange.value if hasattr(order.exchange, "value") else "NSE",
            quantity=order.quantity,
            price=order.price or 0.0,
            product=order.product.value if hasattr(order.product, "value") else "INTRADAY",
            metadata={"latency_ms": round(latency_ms, 2)},
        )

    async def _persist_state(self, strategy_id: str, state: StrategyState) -> None:
        try:
            supabase = get_supabase()
            await async_supabase(lambda: supabase.table("strategy_health").upsert({
                "strategy_id": strategy_id,
                "status": state.value,
                "last_heartbeat": datetime.now(UTC).isoformat(),
            }, on_conflict=["strategy_id"]).execute())
        except Exception as e:
            logger.debug("Failed to persist state for %s: %s", strategy_id, e)

    async def _recover_running_strategies(self) -> None:
        try:
            supabase = get_supabase()
            rows = await async_safe_execute(
                supabase.table("strategy_health")
                .select("*")
                .eq("status", "running")
            ) or []
            for row in rows:
                sid = row.get("strategy_id", "")
                if sid in self._configs:
                    await self.start_strategy(sid)
                    logger.info("Recovered running strategy: %s", sid)
            if rows:
                logger.info("Recovered %d running strategies from DB", len(rows))
        except Exception as e:
            logger.warning("Strategy recovery failed: %s", e)

    async def _on_market_open(self) -> None:
        logger.info("Market opened — triggering market_open strategies")
        tasks = []
        for sid in self._configs:
            config = self._configs[sid]
            if config.trigger == TriggerType.MARKET_OPEN and config.enabled:
                tasks.append(self.start_strategy(sid))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _on_market_close(self) -> None:
        logger.info("Market closed — stopping all strategies")
        tasks = [self.stop_strategy(sid) for sid in list(self._configs.keys())]
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=30)

    async def shutdown(self) -> None:
        runtime_event_subscriber.unsubscribe()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        tasks = [self.stop_strategy(sid) for sid in list(self._configs.keys())]
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=30)
        await scheduler.stop()
        for task in self._evaluation_tasks.values():
            task.cancel()
        self._evaluation_tasks.clear()
        self._configs.clear()
        self._contexts.clear()
        self._runtime_start = 0.0
        logger.info("RuntimeManager shut down")

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(60)
                supabase = get_supabase()
                now = datetime.now(UTC).isoformat()
                for sid in self._configs:
                    if sid in self._contexts:
                        await async_supabase(lambda s=sid, t=now: supabase.table("strategy_health").upsert({
                            "strategy_id": s,
                            "heartbeat_at": t,
                        }, on_conflict=["strategy_id"]).execute())
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Heartbeat error: %s", e)

    async def _publish_event(self, event_type: str, strategy_id: str, user_id: str, **extra) -> None:
        try:
            event = ExecutionEvent(
                event_type=event_type,
                user_id=user_id,
                payload={"strategy_id": strategy_id, **extra},
            )
            fire_and_forget(execution_event_bus.publish(event))
        except Exception as e:
            logger.error("Failed to publish event %s: %s", event_type, e)


runtime_manager = RuntimeManager()
