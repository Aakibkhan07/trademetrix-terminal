import asyncio
import logging
from datetime import UTC, datetime

from builder.compiler import compile_dsl
from builder.manager import builder_manager
from builder.strategy import GraphStrategy
from core.cache import cache
from core.db import async_supabase, get_supabase
from core.models import Candle, Exchange
from engine.gate import execute_order
from market.historical import historical_engine

logger = logging.getLogger(__name__)

POLL_INTERVAL = 60

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

    cache_key = f"graph_runner:{strategy_id}:last_ts"
    seen_ids_key = f"graph_runner:{strategy_id}:seen_ids"
    seen_ids = set(await cache.get(seen_ids_key, []))

    while True:
        try:
            candles = await historical_engine.get_historical(
                symbol=symbol,
                interval=interval,
                days=2,
                user_id=user_id,
            )
            if not candles:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            new_candles = []
            for c in candles:
                ts = c.get("timestamp", "")
                if isinstance(ts, str) and ts not in seen_ids:
                    new_candles.append(c)

            if new_candles:
                for c in new_candles:
                    seen_ids.add(c.get("timestamp", ""))
                    candle = _candle_from_dict(c)
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
                                "Graph signal: symbol=%s side=%s qty=%d success=%s",
                                order.symbol, order.side.value if order.side else "",
                                order.quantity, result.success,
                            )

                seen_list = list(seen_ids)
                if len(seen_list) > 10000:
                    seen_list = seen_list[-5000:]
                await cache.set(seen_ids_key, seen_list, ttl=86400)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception("Graph runner error for %s: %s", strategy_id, e)

        await asyncio.sleep(POLL_INTERVAL)

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
