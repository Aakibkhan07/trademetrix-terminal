"""Fyers Market Data Agent — streams ticks to Redis pub/sub.

Runs as a standalone container. Connects to Fyers WebSocket and publishes
each tick as JSON to Redis channel `market:ticks`. The API subscribes to
these channels and broadcasts to local subscribers via SharedDataSocket.

Environment:
  - FYERS_CLIENT_ID
  - FYERS_ACCESS_TOKEN
  - REDIS_URL (default redis://redis:6379/0)
  - SYMBOLS (comma-separated, default NSE:NIFTY50-INDEX,NSE:NIFTYBANK-INDEX)
  - LOG_LEVEL (default INFO)
"""

import asyncio
import json
import logging
import os
import signal
import sys

logger = logging.getLogger("market-agent")


async def publish_ticks(redis_url: str, symbols: list[str]) -> None:
    import redis.asyncio as aioredis

    r = aioredis.from_url(redis_url, decode_responses=False)
    await r.ping()
    logger.info("Connected to Redis at %s", redis_url)

    loop = asyncio.get_running_loop()
    tick_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1000)

    def on_tick(tick: dict) -> None:
        try:
            asyncio.ensure_future(handle_tick(tick))
        except Exception:
            pass

    async def handle_tick(tick: dict) -> None:
        try:
            await asyncio.wait_for(tick_queue.put(tick), timeout=0.5)
        except (asyncio.QueueFull, asyncio.TimeoutError):
            pass

    from fyers_apiv3.FyersWebsocket import data_ws

    fyers = data_ws.FyersDataSocket(
        access_token="",
        write_to_file=False,
        log_path="",
        on_ticks=on_tick,
        on_open=lambda: logger.info("Fyers WS connected"),
        on_error=lambda e: logger.error("Fyers WS error: %s", e),
        on_close=lambda: logger.info("Fyers WS closed"),
    )

    def ws_connect():
        fyers.connect()

    fyers.access_token = os.environ.get("FYERS_ACCESS_TOKEN", "")
    if not fyers.access_token:
        logger.error("FYERS_ACCESS_TOKEN not set")
        sys.exit(1)

    await loop.run_in_executor(None, ws_connect)
    logger.info("Fyers WS subscribed to %s", symbols)

    fyers.subscribe(symbols=symbols)

    pub_tasks = []

    async def publisher():
        while True:
            tick = await tick_queue.get()
            symbol = tick.get("symbol", "unknown")
            channel = f"market:ticks:{symbol}"
            try:
                await r.publish(channel, json.dumps(tick))
            except Exception as e:
                logger.warning("Redis publish error: %s", e)

    pub_task = asyncio.create_task(publisher())
    pub_tasks.append(pub_task)

    shutdown_event = asyncio.Event()

    def _signal():
        shutdown_event.set()

    loop.add_signal_handler(signal.SIGTERM, _signal)
    loop.add_signal_handler(signal.SIGINT, _signal)

    await shutdown_event.wait()

    fyers.close()
    for t in pub_tasks:
        t.cancel()
    await r.close()
    logger.info("Market agent shutdown complete")


def main():
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    raw_symbols = os.environ.get(
        "SYMBOLS",
        "NSE:NIFTY50-INDEX,NSE:NIFTYBANK-INDEX,BSE:SENSEX-INDEX",
    )
    symbols = [s.strip() for s in raw_symbols.split(",") if s.strip()]

    logger.info("Starting market agent with symbols: %s", symbols)
    asyncio.run(publish_ticks(redis_url, symbols))


if __name__ == "__main__":
    main()
