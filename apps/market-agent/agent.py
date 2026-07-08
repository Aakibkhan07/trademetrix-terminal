"""Fyers Market Data Agent — streams ticks to Redis pub/sub.

Runs as a standalone container. Connects to Fyers WebSocket and publishes
each tick as JSON to Redis channel `market:ticks`. The API subscribes to
these channels and broadcasts to local subscribers via SharedDataSocket.

Credentials are fetched from Supabase broker_credentials table on startup
(decrypted via ENCRYPTION_KEY). Falls back to FYERS_ACCESS_TOKEN env var.

Environment:
  - SUPABASE_URL / SUPABASE_SERVICE_KEY / ENCRYPTION_KEY (for DB lookup)
  - FYERS_ACCESS_TOKEN (fallback if DB unavailable)
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

import httpx

logger = logging.getLogger("market-agent")


async def _fetch_fyers_token() -> str:
    supabase_url = os.environ.get("SUPABASE_URL", "")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    encryption_key = os.environ.get("ENCRYPTION_KEY", "")

    if not supabase_url or not service_key or not encryption_key:
        logger.info("Supabase env vars not set, falling back to FYERS_ACCESS_TOKEN")
        token = os.environ.get("FYERS_ACCESS_TOKEN", "")
        if not token:
            logger.error("FYERS_ACCESS_TOKEN not set and Supabase unavailable")
            sys.exit(0)
        return token

    from cryptography.fernet import Fernet

    fernet = Fernet(encryption_key.encode())

    rest_url = f"{supabase_url}/rest/v1/broker_credentials"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }
    params = {
        "broker": "eq.fyers",
        "is_active": "eq.true",
        "select": "encrypted_api_key,encrypted_access_token",
        "limit": "1",
        "order": "updated_at.desc",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(rest_url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        rows = resp.json()

    if not rows:
        logger.warning("No active Fyers credentials found in DB, falling back to env")
        token = os.environ.get("FYERS_ACCESS_TOKEN", "")
        if not token:
            logger.error("No Fyers credentials in DB and FYERS_ACCESS_TOKEN not set")
            sys.exit(0)
        return token

    row = rows[0]
    encrypted_api_key = row.get("encrypted_api_key", "")
    encrypted_token = row.get("encrypted_access_token", "")

    if not encrypted_token:
        logger.warning("Fyers credentials exist but no access_token — run OAuth flow first")
        sys.exit(0)

    try:
        client_id = fernet.decrypt(encrypted_api_key.encode()).decode() if encrypted_api_key else ""
        access_token = fernet.decrypt(encrypted_token.encode()).decode()
        logger.info("Fetched Fyers credentials from DB (client_id=%s)", client_id)
        return access_token
    except Exception as e:
        logger.warning(
            "Could not decrypt Fyers credentials (key may have been rotated). "
            "Re-run OAuth flow via the web app to get a fresh token. %s", e
        )
        sys.exit(0)


async def publish_ticks(redis_url: str, symbols: list[str]) -> None:
    import redis.asyncio as aioredis
    from fyers_apiv3.FyersWebsocket import data_ws

    access_token = await _fetch_fyers_token()

    r = aioredis.from_url(redis_url, decode_responses=False)
    await r.ping()
    logger.info("Connected to Redis at %s", redis_url)

    loop = asyncio.get_running_loop()
    tick_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1000)

    async def handle_tick(tick: dict) -> None:
        try:
            await asyncio.wait_for(tick_queue.put(tick), timeout=0.5)
        except (asyncio.QueueFull, asyncio.TimeoutError):
            pass

    def on_message(message: dict) -> None:
        if not isinstance(message, dict):
            return
        asyncio.run_coroutine_threadsafe(handle_tick(message), loop)

    fyers = data_ws.FyersDataSocket(
        access_token=access_token,
        write_to_file=False,
        log_path="",
        on_message=on_message,
        on_error=lambda msg: logger.error("Fyers WS error: %s", msg),
        on_connect=lambda: logger.info("Fyers WS connected"),
        on_close=lambda msg: logger.info("Fyers WS closed: %s", msg),
    )

    def ws_connect():
        fyers.connect()

    await loop.run_in_executor(None, ws_connect)
    logger.info("Fyers WS connected, subscribing to %s", symbols)

    fyers.subscribe(symbols=symbols, data_type="SymbolUpdate", channel=11)

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

    shutdown_event = asyncio.Event()

    def _signal():
        logger.info("Shutdown signal received")
        shutdown_event.set()

    loop.add_signal_handler(signal.SIGTERM, _signal)
    loop.add_signal_handler(signal.SIGINT, _signal)

    await shutdown_event.wait()

    fyers.close_connection()
    pub_task.cancel()
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
