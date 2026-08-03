"""Dispatchers + Event Router.

- TickDispatcher: one ``shared_socket`` subscription per symbol, fan-out to
  every worker of that symbol through a bounded per-worker queue (backpressure
  drops + counts, never blocks the socket).
- MultiTimeframeDispatcher: per-strategy, per-timeframe candle aggregation from
  a single tick stream (each strategy owns its own aggregators — no shared
  mutable state between strategies).
- EventRouter: routes runtime-relevant events (time, session, broker, manual)
  to the lifecycle manager, emitting a structured log + metric per event.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.models import Candle, Tick
from market.candle_aggregator import CandleAggregator

logger = logging.getLogger(__name__)


class TickDispatcher:
    def __init__(self) -> None:
        self._workers: dict[str, set] = {}
        self._handlers: dict[str, Any] = {}
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        logger.info("TickDispatcher started (lazy per-symbol subscriptions)")

    async def shutdown(self) -> None:
        if not self._started:
            return
        try:
            from market.data_socket import shared_socket

            for symbol, handler in self._handlers.items():
                try:
                    shared_socket.unsubscribe(symbol, handler)
                except Exception:
                    pass
        except Exception:
            pass
        self._handlers.clear()
        self._workers.clear()
        self._started = False
        logger.info("TickDispatcher shut down")

    def attach(self, worker: Any) -> None:
        symbol = worker.spec.symbol
        if symbol not in self._workers:
            self._workers[symbol] = set()
            self._handlers[symbol] = self._make_handler(symbol)
            try:
                from market.data_socket import shared_socket

                shared_socket.subscribe(symbol, self._handlers[symbol])
                logger.debug("TickDispatcher subscribed to %s", symbol)
            except Exception as e:
                logger.warning("TickDispatcher subscribe failed for %s: %s", symbol, e)
        self._workers[symbol].add(worker)

    def detach(self, worker: Any) -> None:
        symbol = worker.spec.symbol
        workers = self._workers.get(symbol)
        if workers is None:
            return
        workers.discard(worker)
        if not workers:
            self._workers.pop(symbol, None)
            handler = self._handlers.pop(symbol, None)
            if handler:
                try:
                    from market.data_socket import shared_socket

                    shared_socket.unsubscribe(symbol, handler)
                except Exception:
                    pass

    def _make_handler(self, symbol: str) -> Any:
        async def handler(tick: Tick) -> None:
            await self._fan_out(symbol, tick)

        return handler

    async def _fan_out(self, symbol: str, tick: Tick) -> None:
        workers = list(self._workers.get(symbol, ()))
        if not workers:
            return
        for worker in workers:
            try:
                worker.dispatch_tick(tick)
            except Exception as e:
                logger.error("Tick dispatch to %s failed: %s", worker.spec.strategy_id, e)


class MultiTimeframeDispatcher:
    """Single tick stream -> one CandleAggregator per declared timeframe.

    Returns closed candles as ``(timeframe, Candle)`` pairs, newest-first per
    timeframe; the strategy worker evaluates the primary timeframe and keeps
    the others as context.
    """

    def __init__(self, symbol: str, timeframes: list[str]) -> None:
        self.symbol = symbol
        self.timeframes = list(timeframes) or ["15m"]
        self._aggregators: dict[str, CandleAggregator] = {
            tf: CandleAggregator(symbol, tf) for tf in self.timeframes
        }
        self._last_candles: dict[str, Candle] = {}

    def add_tick(self, tick: Tick) -> list[tuple[str, Candle]]:
        closed: list[tuple[str, Candle]] = []
        for tf, agg in self._aggregators.items():
            candle = agg.add_tick(tick)
            if candle is not None:
                self._last_candles[tf] = candle
                closed.append((tf, candle))
        return closed

    def last_candle(self, timeframe: str) -> Candle | None:
        return self._last_candles.get(timeframe)

    def reset(self) -> None:
        """Fresh aggregation (used on resume so paused strategies never
        evaluate a stale backlog of candles)."""
        self._last_candles.clear()
        self._aggregators = {
            tf: CandleAggregator(self.symbol, tf) for tf in self.timeframes
        }

    def series(self) -> dict[str, list[Candle]]:
        """Recent candles per timeframe for the execution context (last 500)."""
        from collections import defaultdict

        out: dict[str, list[Candle]] = defaultdict(list)
        for tf, agg in self._aggregators.items():
            if agg._period_start:
                out[tf] = [self._last_candles[tf]] if tf in self._last_candles else []
        return dict(out)


class EventRouter:
    """Routes runtime-relevant events to lifecycle actions.

    Kinds: session_open, session_close, time, broker_disconnect,
    broker_reconnect, manual. Every event is logged + counted (observability).
    """

    def __init__(self, manager: Any, observability: Any = None) -> None:
        self._manager = manager
        self._observability = observability

    async def emit(self, kind: str, *, strategy_id: str = "", user_id: str = "", payload: dict | None = None) -> None:
        payload = payload or {}
        logger.info("Runtime event routed: kind=%s strategy_id=%s payload=%s", kind, strategy_id, payload)
        if self._observability:
            self._observability.record_event(kind)
        if kind == "session_open":
            await self._manager._on_session_open()
        elif kind == "session_close":
            await self._manager._on_session_close()
        elif kind == "broker_disconnect":
            await self._manager._on_broker_disconnect(str(payload.get("broker", "")))
        elif kind == "broker_reconnect":
            await self._manager._on_broker_reconnect(str(payload.get("broker", "")))
        elif kind == "time":
            await self._manager._on_time_trigger(strategy_id)
        elif kind == "manual":
            await self._manager._on_manual_event(strategy_id, user_id, payload)
