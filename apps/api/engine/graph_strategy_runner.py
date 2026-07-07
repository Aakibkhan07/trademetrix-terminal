import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta

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
    shared_socket.subscribe("*", tick_handler)
    logger.info("Graph runner subscribed to live tick feed for %s", strategy_id)

    seen_ids_key = f"graph_runner:{strategy_id}:seen_ids"
    seen_ids = set(await cache.get(seen_ids_key, []))

    async def process_candle(candle: Candle) -> None:
        nonlocal strategy
        signal = await strategy.on_candle(candle)
        if signal and signal.orders:
            for order in signal.orders:
                order.strategy_id = strategy_id
                result = await execute_order(
                    user_id=user_id,
                    order=order,
                    source="graph_strategy",
                )
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
                tick_signal = await strategy.on_tick(tick)
                if tick_signal and tick_signal.orders:
                    for order in tick_signal.orders:
                        order.strategy_id = strategy_id
                        await execute_order(user_id=user_id, order=order, source="graph_strategy")

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
                        seen_list = list(seen_ids)
                        if len(seen_list) > 10000:
                            seen_list = seen_list[-5000:]
                        await cache.set(seen_ids_key, seen_list, ttl=86400)

            seen_list = list(seen_ids)
            if len(seen_list) > 10000:
                seen_list = seen_list[-5000:]
            await cache.set(seen_ids_key, seen_list, ttl=86400)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.exception("Graph runner error for %s: %s", strategy_id, e)
    finally:
        shared_socket.unsubscribe(symbol, tick_handler)
        shared_socket.unsubscribe("*", tick_handler)
        await strategy.on_stop()


async def start_graph_strategy(
    strategy_id: str,
    user_id: str,
    symbol: str = "NIFTY",
    interval: str = "15m",
) -> str:
    if strategy_id in _running_tasks and not _running_tasks[strategy_id].done():
        return "already_running"

    task = asyncio.create_task(
        _feed_loop(strategy_id, user_id, symbol, interval)
    )
    _running_tasks[strategy_id] = task
    logger.info("Graph strategy runner started for %s (symbol=%s)", strategy_id, symbol)

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

    return "started"


async def stop_graph_strategy(strategy_id: str):
    task = _running_tasks.pop(strategy_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("Graph strategy runner stopped for %s", strategy_id)

    supabase = get_supabase()
    await async_supabase(lambda: supabase.table("strategy_runs").update({
        "status": "stopped",
        "stopped_at": datetime.now(UTC).isoformat(),
    }).eq("strategy_id", strategy_id).eq("status", "running").execute())
