import asyncio
import logging
import time
from datetime import UTC, datetime

from builder.logs import record
from builder.manager import builder_manager
from builder.strategy import GraphStrategy
from core.cache import cache
from core.db import async_supabase, get_supabase
from core.models import Candle, Exchange, Tick
from engine.gate import execute_order
from market.candle_aggregator import CandleAggregator
from market.data_socket import shared_socket
from market.historical import historical_engine

logger = logging.getLogger(__name__)

_running_tasks: dict[str, asyncio.Task] = {}
_runtime: dict[str, dict] = {}


def _runtime_stats(strategy_id: str) -> dict:
    stats = _runtime.setdefault(strategy_id, {
        "strategy_id": strategy_id,
        "status": "idle",
        "started_at": "",
        "stopped_at": "",
        "symbol": "",
        "interval": "",
        "mode": "paper",
        "capital": 0.0,
        "candles_processed": 0,
        "signals": 0,
        "orders_placed": 0,
        "orders_filled": 0,
        "orders_rejected": 0,
        "errors": 0,
        "last_error": "",
        "last_activity": "",
        "avg_latency_ms": 0.0,
        "latency_samples": 0,
    })
    return stats


def _candle_from_dict(d: dict) -> Candle:
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


async def _feed_loop(
    strategy_id: str,
    user_id: str,
    symbol: str,
    interval: str,
    is_paper: bool = True,
):
    dsl = await builder_manager.get(strategy_id)
    if not dsl:
        logger.warning("Graph strategy %s not found", strategy_id)
        return

    strategy = GraphStrategy(config={
        "_dsl": dsl.model_dump(mode="json") if hasattr(dsl, "model_dump") else dsl,
        "symbol": symbol,
        "strategy_id": strategy_id,
    })
    await strategy.on_start()

    aggregator = CandleAggregator(symbol, interval)
    tick_queue: asyncio.Queue[Tick] = asyncio.Queue()
    live_feed_active = False

    async def tick_handler(tick: Tick) -> None:
        if tick.symbol == symbol or tick.symbol.endswith(f":{symbol}"):
            await tick_queue.put(tick)

    shared_socket.subscribe(symbol, tick_handler)
    logger.info("Graph runner subscribed to live tick feed for %s", strategy_id)

    seen_ids_key = f"graph_runner:{strategy_id}:seen_ids"
    seen_ids = set(await cache.get(seen_ids_key, []))
    _persist_counter = 0

    async def _persist_seen_ids():
        nonlocal _persist_counter
        _persist_counter += 1
        if _persist_counter % 10 != 0:
            return
        seen_list = list(seen_ids)
        if len(seen_list) > 10000:
            seen_list = seen_list[-5000:]
            seen_ids.clear()
            seen_ids.update(seen_list)
        await cache.set(seen_ids_key, seen_list, ttl=86400)

    async def process_candle(candle: Candle) -> None:
        nonlocal strategy
        stats = _runtime_stats(strategy_id)
        start = time.monotonic()
        signal = await strategy.on_candle(candle)
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        stats["latency_samples"] += 1
        n = stats["latency_samples"]
        stats["avg_latency_ms"] = round(stats["avg_latency_ms"] + (elapsed_ms - stats["avg_latency_ms"]) / n, 2)
        stats["candles_processed"] += 1
        stats["last_activity"] = datetime.now(UTC).isoformat()
        if signal and signal.orders:
            stats["signals"] += 1
            await record(strategy_id, "signal", f"Signal fired: {len(signal.orders)} order(s) on candle close",
                         level="info", user_id=user_id, detail={"symbol": candle.symbol, "close": candle.close})
            for order in signal.orders:
                order.strategy_id = strategy_id
                order.is_paper = is_paper
                result = await execute_order(
                    user_id=user_id,
                    order=order,
                    source="graph_strategy",
                )
                if result and result.success:
                    stats["orders_placed"] += 1
                    if (result.status or "").lower() in ("filled", "complete", "traded"):
                        stats["orders_filled"] += 1
                    await record(strategy_id, "order", f"{order.side.value if order.side else ''} {order.quantity} {order.symbol} placed ({result.status})",
                                 level="info", user_id=user_id,
                                 detail={"side": order.side.value if order.side else "", "qty": order.quantity,
                                         "symbol": order.symbol, "broker_order_id": result.broker_order_id, "status": result.status})
                else:
                    stats["orders_rejected"] += 1
                    await record(strategy_id, "rejection", f"{order.side.value if order.side else ''} {order.quantity} {order.symbol} rejected: {result.message if result else 'unknown'}",
                                 level="warning", user_id=user_id,
                                 detail={"symbol": order.symbol, "message": result.message if result else ""})
                logger.info(
                    "Graph signal: symbol=%s side=%s qty=%d success=%s msg=%s",
                    order.symbol, order.side.value if order.side else "",
                    order.quantity, result.success, result.message,
                )

    try:
        while True:
            try:
                tick = await asyncio.wait_for(tick_queue.get(), timeout=10)
                live_feed_active = True
                stats = _runtime_stats(strategy_id)
                stats["last_activity"] = datetime.now(UTC).isoformat()
                tick_signal = await strategy.on_tick(tick)
                if tick_signal and tick_signal.orders:
                    stats["signals"] += 1
                    for order in tick_signal.orders:
                        order.strategy_id = strategy_id
                        order.is_paper = is_paper
                        result = await execute_order(user_id=user_id, order=order, source="graph_strategy")
                        if result and result.success:
                            stats["orders_placed"] += 1
                        else:
                            stats["orders_rejected"] += 1

                candle = aggregator.add_tick(tick)
                if candle:
                    ts_key = candle.timestamp if isinstance(candle.timestamp, str) else candle.timestamp.isoformat()
                    if ts_key not in seen_ids:
                        seen_ids.add(ts_key)
                        await process_candle(candle)

            except asyncio.TimeoutError:
                if not live_feed_active:
                    candles = await historical_engine.get_historical(
                        symbol=symbol,
                        interval=interval,
                        days=2,
                        user_id=user_id,
                    )
                    if candles:
                        for c in candles:
                            ts = c.get("timestamp", "")
                            if isinstance(ts, str) and ts not in seen_ids:
                                seen_ids.add(ts)
                                await process_candle(_candle_from_dict(c))
                        await _persist_seen_ids()

            await _persist_seen_ids()

    except asyncio.CancelledError:
        pass
    except Exception as e:
        stats = _runtime_stats(strategy_id)
        stats["errors"] += 1
        stats["last_error"] = str(e)[:500]
        logger.exception("Graph runner error for %s: %s", strategy_id, e)
        await record(strategy_id, "error", f"Runner error: {e}", level="error", user_id=user_id)
    finally:
        shared_socket.unsubscribe(symbol, tick_handler)
        await strategy.on_stop()


async def start_graph_strategy(
    strategy_id: str,
    user_id: str,
    symbol: str = "NIFTY",
    interval: str = "15m",
    is_paper: bool = True,
) -> str:
    if strategy_id in _running_tasks and not _running_tasks[strategy_id].done():
        return "already_running"

    task = asyncio.create_task(
        _feed_loop(strategy_id, user_id, symbol, interval, is_paper)
    )
    _running_tasks[strategy_id] = task
    stats = _runtime_stats(strategy_id)
    stats.update({
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "stopped_at": "",
        "symbol": symbol,
        "interval": interval,
        "mode": "paper" if is_paper else "live",
    })
    logger.info("Graph strategy runner started for %s (symbol=%s)", strategy_id, symbol)
    await record(strategy_id, "lifecycle", f"Strategy started ({'paper' if is_paper else 'live'}, {symbol} {interval})",
                 level="info", user_id=user_id)

    try:
        supabase = get_supabase()
        await async_supabase(lambda: supabase.table("strategy_runs").insert({
            "user_id": user_id,
            "strategy_id": strategy_id,
            "broker": "graph",
            "mode": "GRAPH",
            "symbols": [symbol],
            "status": "running",
            "started_at": datetime.now(UTC).isoformat(),
        }).execute())
    except Exception as e:
        logger.warning("Could not persist strategy_runs row for %s (runner continues): %s", strategy_id, e)

    return "started"


async def stop_graph_strategy(strategy_id: str, user_id: str = ""):
    task = _running_tasks.pop(strategy_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("Graph strategy runner stopped for %s", strategy_id)
    stats = _runtime_stats(strategy_id)
    stats["status"] = "stopped"
    stats["stopped_at"] = datetime.now(UTC).isoformat()
    stats["last_activity"] = datetime.now(UTC).isoformat()
    await record(strategy_id, "lifecycle", "Strategy stopped", level="info", user_id=user_id)

    try:
        supabase = get_supabase()
        await async_supabase(lambda: supabase.table("strategy_runs").update({
            "status": "stopped",
            "stopped_at": datetime.now(UTC).isoformat(),
        }).eq("strategy_id", strategy_id).eq("status", "running").execute())
    except Exception as e:
        logger.warning("Could not update strategy_runs row for %s: %s", strategy_id, e)


async def get_runtime_dashboard() -> list[dict]:
    """Execution dashboard: per-strategy runtime stats + read-only PnL from the
    orders audit table (source=graph_strategy). No OMS/broker writes."""
    out: list[dict] = []
    for strategy_id, stats in _runtime.items():
        entry = dict(stats)
        entry["health"] = "degraded" if stats.get("errors") and stats["errors"] > 2 else "ok"
        try:
            entry["pnl"] = await _estimate_pnl(strategy_id)
        except Exception as e:
            logger.debug("PnL estimate failed for %s: %s", strategy_id, e)
            entry["pnl"] = 0.0
        out.append(entry)
    return sorted(out, key=lambda r: r.get("started_at", ""), reverse=True)


async def _estimate_pnl(strategy_id: str) -> float:
    """Read-only realized PnL estimate from the orders audit table:
    (total sell value) - (total buy value) for graph strategy orders."""
    supabase = get_supabase()
    result = await async_supabase(lambda: supabase.table("orders")
                                  .select("side,quantity,average_price")
                                  .eq("strategy_id", strategy_id)
                                  .eq("source", "graph_strategy").execute())
    total = 0.0
    for row in result.data or []:
        qty = float(row.get("quantity") or 0)
        price = float(row.get("average_price") or 0)
        side = str(row.get("side", "")).upper()
        if side == "BUY":
            total -= qty * price
        elif side == "SELL":
            total += qty * price
    return round(total, 2)


def get_running_strategies() -> dict[str, dict]:
    return {sid: dict(s) for sid, s in _runtime.items() if s.get("status") == "running"}
