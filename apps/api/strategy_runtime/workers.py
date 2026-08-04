"""Strategy Workers — one isolated task per strategy.

Evaluation loop: tick stream -> bounded queue -> multi-timeframe aggregation ->
primary-timeframe candle evaluation -> signals -> orders through the Execution
Engine (``engine.gate.execute_order``, same path as the graph runner, so the
Risk Engine and paper routing apply unchanged).

Properties:
- isolation: one worker task, one GraphStrategy instance, a per-strategy
  asyncio.Lock serializes every evaluation (tick, candle, manual) — no
  concurrent entry into the strategy instance.
- determinism: candles are evaluated in arrival order; historical warm-up
  replays candles WITHOUT executing (indicator priming only); seen-candle
  dedup (Redis, fail-open) makes restarts idempotent — no duplicate signals.
- resilience: transient evaluation errors are counted and surfaced; a strategy
  only fails (FAILED state) after ERROR_THRESHOLD consecutive errors.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from core.models import Candle, Tick
from strategy_runtime.dispatchers import MultiTimeframeDispatcher
from strategy_runtime.registry import RuntimeRecord

logger = logging.getLogger(__name__)

QUEUE_MAX = 2000
ERROR_THRESHOLD = 5
SEEN_PERSIST_EVERY = 10

STATUS_ORDER_SOURCE = "graph_strategy"


async def load_strategy(strategy_id: str, symbol: str) -> Any:
    """Build a GraphStrategy instance from the builder DSL (test hook)."""
    from builder.manager import builder_manager
    from builder.strategy import GraphStrategy

    dsl = await builder_manager.get(strategy_id)
    if dsl is None:
        raise RuntimeError(f"Strategy {strategy_id} not found")
    return GraphStrategy(config={
        "_dsl": dsl.model_dump(mode="json") if hasattr(dsl, "model_dump") else dsl,
        "symbol": symbol,
        "strategy_id": strategy_id,
    })


def _ts_key(ts) -> str:
    return ts if isinstance(ts, str) else ts.isoformat()


def _candle_from_dict(d: dict) -> Candle:
    from core.models import Exchange

    return Candle(
        symbol=d.get("symbol", ""),
        exchange=Exchange(d.get("exchange", "NSE")),
        interval=d.get("interval", "15m"),
        open=float(d.get("open", 0)),
        high=float(d.get("high", 0)),
        low=float(d.get("low", 0)),
        close=float(d.get("close", 0)),
        volume=float(d.get("volume", 0)),
        timestamp=d.get("timestamp", datetime.now(UTC).isoformat()),
        oi=float(d.get("oi", 0)),
    )


class StrategyWorker:
    def __init__(self, record: RuntimeRecord, lifecycle: Any) -> None:
        self.record = record
        self.spec = record.spec
        self._lifecycle = lifecycle
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
        self._mtf = MultiTimeframeDispatcher(self.spec.symbol, self.spec.timeframes)
        self._strategy: Any = None
        self._task: asyncio.Task | None = None
        self._eval_lock = asyncio.Lock()
        self._evaluation_allowed = False
        self._paused = False
        self._consecutive_errors = 0
        self._last_price = 0.0
        self._seen_ids: dict[str, set] = {}
        self._tick_window_start = time.monotonic()
        self._tick_window_count = 0

    # -- lifecycle -----------------------------------------------------------
    @property
    def last_price(self) -> float:
        return self._last_price

    def is_alive(self) -> bool:
        return bool(self._task and not self._task.done())

    async def start(self) -> None:
        self._strategy = await load_strategy(self.spec.strategy_id, self.spec.symbol)
        await self._strategy.on_start()
        if self.spec.warmup:
            await self._warmup()
        self._evaluation_allowed = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._evaluation_allowed = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        await self._persist_seen_ids()
        if self._strategy is not None:
            try:
                await self._strategy.on_stop()
            except Exception as e:
                logger.warning("strategy.on_stop failed for %s: %s", self.spec.strategy_id, e)
            self._strategy = None

    def pause(self) -> None:
        self._paused = True
        self._evaluation_allowed = False

    def resume(self) -> None:
        self._paused = False
        self._evaluation_allowed = True
        self._mtf.reset()

    # -- tick path -----------------------------------------------------------
    def dispatch_tick(self, tick: Tick) -> None:
        self._last_price = tick.last_price
        self._tick_window_count += 1
        if self._paused or not self._evaluation_allowed:
            return
        try:
            self._queue.put_nowait(tick)
        except asyncio.QueueFull:
            self.record.stats["dropped_ticks"] += 1

    async def _run(self) -> None:
        try:
            while True:
                tick = await self._queue.get()
                await self._process_tick(tick)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("Strategy worker %s crashed: %s", self.spec.strategy_id, e)
            await self._fail(str(e))
        finally:
            await self._persist_seen_ids()

    async def _process_tick(self, tick: Tick) -> None:
        now = time.monotonic()
        if now - self._tick_window_start >= 60:
            self.record.stats["tick_rate_per_min"] = self._tick_window_count
            self._tick_window_count = 0
            self._tick_window_start = now
        self.record.stats["ticks_processed"] += 1
        self.record.touch()

        if self.spec.trigger.value == "EVERY_TICK" and self._evaluation_allowed:
            await self._evaluate_tick(tick)

        for tf, candle in self._mtf.add_tick(tick):
            if tf == self.spec.interval:
                await self._handle_candle(tf, candle)

    # -- candle path ---------------------------------------------------------
    async def _handle_candle(self, tf: str, candle: Candle) -> None:
        key = _ts_key(candle.timestamp)
        if key in self._seen(tf):
            return
        self._seen(tf).add(key)
        if self._evaluation_allowed:
            await self._evaluate(candle, execute=True)

    def _seen(self, tf: str) -> set:
        return self._seen_ids.setdefault(tf, set())

    async def _persist_seen_ids(self) -> None:
        try:
            from core.cache import cache

            key = f"strategy_runtime:{self.spec.strategy_id}:seen_ids"
            await cache.set(key, {tf: sorted(ids)[-2000:] for tf, ids in self._seen_ids.items()}, ttl=86400)
        except Exception:
            pass

    async def _load_seen_ids(self) -> None:
        try:
            from core.cache import cache

            stored = await cache.get(f"strategy_runtime:{self.spec.strategy_id}:seen_ids", {}) or {}
            self._seen_ids = {tf: set(ids) for tf, ids in stored.items() if isinstance(ids, list)}
        except Exception:
            pass

    # -- warm-up -------------------------------------------------------------
    async def _warmup(self) -> None:
        await self._load_seen_ids()
        try:
            from market.historical import historical_engine

            for tf in self.spec.timeframes:
                try:
                    candles = await historical_engine.get_historical(
                        symbol=self.spec.symbol,
                        interval=tf,
                        days=2,
                        user_id=self.spec.user_id,
                    )
                except Exception as e:
                    logger.warning("Warm-up history failed for %s %s: %s", self.spec.strategy_id, tf, e)
                    continue
                for raw in candles or []:
                    candle = _candle_from_dict(raw)
                    key = _ts_key(candle.timestamp)
                    if key in self._seen(tf):
                        continue
                    self._seen(tf).add(key)
                    if tf == self.spec.interval:
                        await self._evaluate(candle, execute=False)
        except Exception as e:
            logger.warning("Warm-up aborted for %s: %s", self.spec.strategy_id, e)

    # -- evaluation ----------------------------------------------------------
    async def _evaluate_tick(self, tick: Tick) -> None:
        async with self._eval_lock:
            if not self._evaluation_allowed or not self._strategy:
                return
            start = time.monotonic()
            try:
                signal = await self._strategy.on_tick(tick)
            except Exception as e:
                await self._on_eval_error(e)
                return
            if signal and signal.orders:
                self.record.stats["signals"] += 1
                await self._execute_orders(signal)

    async def _evaluate(self, candle: Candle, execute: bool) -> None:
        async with self._eval_lock:
            if not self._strategy:
                return
            start = time.monotonic()
            self.record.touch()
            try:
                from strategy_runtime.context import position_memory_for

                position_memory_for(self._strategy, self.spec)
                signal = await self._strategy.on_candle(candle)
            except Exception as e:
                await self._on_eval_error(e)
                return

            elapsed_ms = (time.monotonic() - start) * 1000
            stats = self.record.stats
            stats["candles_processed"] += 1
            stats["latency_samples"] += 1
            n = stats["latency_samples"]
            stats["avg_latency_ms"] = round(
                stats["avg_latency_ms"] + (elapsed_ms - stats["avg_latency_ms"]) / n, 2
            )
            if self._lifecycle:
                await self._lifecycle._record_evaluation(self.record, elapsed_ms)

            if signal and signal.orders:
                stats["signals"] += 1
                if execute:
                    await self._execute_orders(signal)
                else:
                    logger.debug(
                        "Warm-up signal suppressed (no execution): %s orders=%d",
                        self.spec.strategy_id, len(signal.orders),
                    )

    async def _on_eval_error(self, e: Exception) -> None:
        self.record.stats["errors"] += 1
        self.record.last_error = str(e)[:500]
        self._consecutive_errors += 1
        logger.error("Evaluation error for %s: %s", self.spec.strategy_id, e)
        if self._lifecycle:
            await self._lifecycle._record_error(self.record, str(e)[:500])
        if self._consecutive_errors >= ERROR_THRESHOLD:
            raise RuntimeError(f"strategy {self.spec.strategy_id} failed: {e}")

    async def _fail(self, error: str) -> None:
        self.record.stats["errors"] += 1
        self.record.last_error = error[:500]
        if self._lifecycle:
            await self._lifecycle._on_worker_failed(self.spec.strategy_id, error)

    # -- manual / time-trigger evaluation ------------------------------------
    def last_candle(self) -> Candle | None:
        return self._mtf.last_candle(self.spec.interval)

    async def time_tick(self) -> None:
        """Fold a time trigger into the candle pipeline (deduped — the same
        closed candle is never evaluated twice, so no duplicate orders)."""
        candle = self.last_candle()
        if candle is not None:
            await self._handle_candle(self.spec.interval, candle)

    async def manual_evaluate(self, context: dict) -> Any:
        """Dry-run evaluation against the last closed candle (no order
        execution); returns the strategy signal, if any."""
        async with self._eval_lock:
            if not self._strategy or not self._evaluation_allowed:
                return None
            candle = self.last_candle()
            if candle is None:
                return None
            start = time.monotonic()
            try:
                from strategy_runtime.context import position_memory_for

                position_memory_for(self._strategy, self.spec)
                signal = await self._strategy.on_candle(candle)
            except Exception as e:
                self.record.stats["errors"] += 1
                self.record.last_error = str(e)[:500]
                logger.error("Manual evaluation error for %s: %s", self.spec.strategy_id, e)
                if self._lifecycle:
                    await self._lifecycle._record_error(self.record, str(e)[:500])
                return None
            elapsed_ms = (time.monotonic() - start) * 1000
            stats = self.record.stats
            stats["latency_samples"] += 1
            n = stats["latency_samples"]
            stats["avg_latency_ms"] = round(
                stats["avg_latency_ms"] + (elapsed_ms - stats["avg_latency_ms"]) / n, 2
            )
            if self._lifecycle:
                await self._lifecycle._record_evaluation(self.record, elapsed_ms)
            if signal and signal.orders:
                self.record.stats["signals"] += 1
            return signal

    # -- orders --------------------------------------------------------------
    async def _enforce_order_limits(self, order: Any) -> tuple[bool, str, str]:
        """Auto Trading v1.0 pre-order risk gates (fail-safe by design).

        1. kill switch / emergency stop re-check (right before the order)
        2. max_daily_trades — calendar-day counter, persists across restarts
           via the checkpointed record stats
        3. max_positions — open-position cap for the strategy symbol
        4. max_risk_per_trade — notional exposure cap per order

        Exits (sell / exit sides) are never blocked by position/exposure
        limits — closing is always allowed.
        """
        from strategy_runtime.mode import ModeGuardError, assert_orders_allowed

        try:
            await assert_orders_allowed(self.spec.user_id)
        except ModeGuardError as e:
            return False, str(e), e.code

        today = datetime.now(UTC).date().isoformat()
        stats = self.record.stats
        if stats.get("daily_trades_date") != today:
            stats["daily_trades_date"] = today
            stats["daily_trades"] = 0
        if self.spec.max_daily_trades > 0 and stats.get("daily_trades", 0) >= self.spec.max_daily_trades:
            return False, f"Max daily trades reached ({self.spec.max_daily_trades})", "MAX_DAILY_TRADES"

        side = str(getattr(order, "side", "") or "").upper()
        is_entry = side in ("BUY", "LONG")
        if not is_entry:
            return True, "", ""

        if self.spec.max_positions > 0:
            try:
                from execution_engine.positions import position_manager

                positions = position_manager.get_positions(self.spec.user_id, self.spec.broker or "paper") or []
                open_for_symbol = [p for p in positions
                                   if str(getattr(p, "symbol", "")).upper() == str(order.symbol).upper()
                                   and float(getattr(p, "quantity", 0) or 0) > 0]
                if len(open_for_symbol) >= self.spec.max_positions:
                    return False, f"Max positions reached ({self.spec.max_positions})", "MAX_POSITIONS"
            except Exception as e:
                logger.warning("Position check failed (fail-open) for %s: %s", self.spec.strategy_id, e)

        if self.spec.max_risk_per_trade > 0:
            price = self._last_price or 0.0
            notional = float(order.quantity) * price
            if notional > self.spec.max_risk_per_trade:
                return False, (
                    f"Notional exposure {notional:.2f} exceeds max per trade "
                    f"{self.spec.max_risk_per_trade:.2f}"
                ), "MAX_EXPOSURE"
        return True, "", ""

    async def _execute_orders(self, signal: Any) -> None:
        from engine.gate import execute_order
        from strategy_runtime.manager import _publish_runtime_event

        stats = self.record.stats
        for order in signal.orders:
            allowed, reason, code = await self._enforce_order_limits(order)
            if not allowed:
                stats["orders_rejected"] += 1
                self.record.last_error = reason[:500]
                logger.warning("Order blocked for %s: %s (%s)", self.spec.strategy_id, reason, code)
                await self._audit(
                    "rejection",
                    f"Order blocked: {reason}",
                    level="warning",
                    detail={"symbol": order.symbol, "code": code, "reason": reason[:300]},
                )
                continue
            try:
                order.strategy_id = self.spec.strategy_id
                order.is_paper = self.spec.is_paper
                result = await execute_order(
                    user_id=self.spec.user_id,
                    order=order,
                    source=STATUS_ORDER_SOURCE,
                )
            except Exception as e:
                stats["orders_rejected"] += 1
                self.record.last_error = str(e)[:500]
                logger.error("Order execution failed for %s: %s", self.spec.strategy_id, e)
                await self._audit(
                    "rejection",
                    f"Order rejected: {e}",
                    level="warning",
                    detail={"message": str(e)[:500]},
                )
                continue
            if result and result.success:
                stats["orders_placed"] += 1
                if stats.get("daily_trades_date") == datetime.now(UTC).date().isoformat():
                    stats["daily_trades"] = stats.get("daily_trades", 0) + 1
                if (result.status or "").lower() in ("filled", "complete", "traded"):
                    stats["orders_filled"] += 1
                await self._audit(
                    "order",
                    f"{order.side.value if hasattr(order.side, 'value') else order.side} "
                    f"{order.quantity} {order.symbol} placed ({result.status})",
                    detail={
                        "side": order.side.value if hasattr(order.side, "value") else str(order.side),
                        "qty": order.quantity,
                        "symbol": order.symbol,
                        "broker_order_id": result.broker_order_id,
                        "status": result.status,
                    },
                )
                _publish_runtime_event(
                    "OrderPlaced", self.spec.strategy_id, self.spec.user_id,
                    payload={"symbol": order.symbol, "quantity": order.quantity,
                             "status": result.status, "broker_order_id": result.broker_order_id},
                )
            else:
                stats["orders_rejected"] += 1
                await self._audit(
                    "rejection",
                    f"Order rejected: {result.message if result else 'unknown'}",
                    level="warning",
                    detail={"symbol": order.symbol, "message": result.message if result else ""},
                )

    async def _audit(self, kind: str, message: str, level: str = "info", detail: dict | None = None) -> None:
        try:
            from builder.logs import record as log_record

            await log_record(
                self.spec.strategy_id, kind, message,
                level=level, user_id=self.spec.user_id, detail=detail or {},
            )
        except Exception:
            pass
