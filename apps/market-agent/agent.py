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
import time

import httpx

logger = logging.getLogger("market-agent")


async def _fetch_fyers_token() -> str | None:
    supabase_url = os.environ.get("SUPABASE_URL", "")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    encryption_key = os.environ.get("ENCRYPTION_KEY", "")

    if not supabase_url or not service_key or not encryption_key:
        logger.info("Supabase env vars not set, falling back to FYERS_ACCESS_TOKEN")
        return os.environ.get("FYERS_ACCESS_TOKEN") or None

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
        return os.environ.get("FYERS_ACCESS_TOKEN") or None

    row = rows[0]
    encrypted_api_key = row.get("encrypted_api_key", "")
    encrypted_token = row.get("encrypted_access_token", "")

    if not encrypted_token:
        logger.warning("Fyers credentials exist but no access_token — run OAuth flow first")
        return None

    try:
        access_token = None
        if encrypted_token:
            try:
                access_token = fernet.decrypt(encrypted_token.encode()).decode()
            except Exception as e:
                logger.warning("Failed to decrypt access_token: %s", e)
        client_id = ""
        if encrypted_api_key:
            try:
                client_id = fernet.decrypt(encrypted_api_key.encode()).decode()
            except Exception as e:
                logger.warning("Failed to decrypt api_key (non-fatal): %s", e)
        if not access_token:
            logger.warning("Fyers credentials exist but no access_token could be decrypted")
            return None
        logger.info("Fetched Fyers credentials from DB (client_id=%s)", client_id)
        return access_token
    except Exception as e:
        logger.warning("Failed to decrypt Fyers credentials: %s", e)
        return None


MAX_RECONNECT_DELAY = 60
INITIAL_RECONNECT_DELAY = 2


async def publish_ticks(redis_url: str, symbols: list[str]) -> None:
    import redis.asyncio as aioredis
    from fyers_apiv3.FyersWebsocket import data_ws

    access_token = await _fetch_fyers_token()
    if not access_token:
        logger.warning("No valid Fyers token — idle until credentials are provided via OAuth flow")
        await asyncio.Event().wait()
        return

    r = aioredis.from_url(redis_url, decode_responses=False)
    await r.ping()
    logger.info("Connected to Redis at %s", redis_url)

    loop = asyncio.get_running_loop()
    tick_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1000)
    shutdown_event = asyncio.Event()
    ws_disconnected = asyncio.Event()

    def _signal():
        logger.info("Shutdown signal received")
        shutdown_event.set()

    loop.add_signal_handler(signal.SIGTERM, _signal)
    loop.add_signal_handler(signal.SIGINT, _signal)

    async def handle_tick(tick: dict) -> None:
        try:
            await asyncio.wait_for(tick_queue.put(tick), timeout=0.5)
        except (asyncio.QueueFull, asyncio.TimeoutError):
            pass

    async def publisher():
        while not shutdown_event.is_set():
            try:
                tick = await asyncio.wait_for(tick_queue.get(), timeout=1)
                symbol = tick.get("symbol", "unknown")
                channel = f"market:ticks:{symbol}"
                try:
                    await r.publish(channel, json.dumps(tick))
                except Exception as e:
                    logger.warning("Redis publish error: %s", e)
            except asyncio.TimeoutError:
                continue

    pub_task = asyncio.create_task(publisher())

    reconnect_delay = INITIAL_RECONNECT_DELAY

    while not shutdown_event.is_set():
        ws_disconnected.clear()
        fyers = None

        def on_message(message: dict) -> None:
            if not isinstance(message, dict):
                return
            asyncio.run_coroutine_threadsafe(handle_tick(message), loop)

        def on_error(msg: str) -> None:
            logger.error("Fyers WS error: %s", msg)

        def on_connect() -> None:
            logger.info("Fyers WS connected")
            nonlocal reconnect_delay
            reconnect_delay = INITIAL_RECONNECT_DELAY

        def on_close(msg: str) -> None:
            logger.info("Fyers WS closed: %s", msg)
            ws_disconnected.set()

        fyers = data_ws.FyersDataSocket(
            access_token=access_token,
            write_to_file=False,
            log_path="",
            on_message=on_message,
            on_error=on_error,
            on_connect=on_connect,
            on_close=on_close,
        )

        def ws_connect():
            fyers.connect()

        try:
            await loop.run_in_executor(None, ws_connect)
            ws_connected = asyncio.Event()
            original_on_connect = on_connect

            def wrapped_on_connect():
                original_on_connect()
                ws_connected.set()
            fyers.on_connect = wrapped_on_connect
            await loop.run_in_executor(None, ws_connect)
            try:
                await asyncio.wait_for(ws_connected.wait(), timeout=10)
            except asyncio.TimeoutError:
                logger.warning("Fyers WS connect callback timed out — subscribing anyway")
            logger.info("Fyers WS connected, subscribing to %s", symbols)
            fyers.subscribe(symbols=symbols, data_type="SymbolUpdate", channel=11)
        except Exception as e:
            logger.error("Fyers WS connection failed: %s", e)
            ws_disconnected.set()

        wait_task = asyncio.create_task(shutdown_event.wait())
        disconnect_task = asyncio.create_task(ws_disconnected.wait())
        done, _ = await asyncio.wait(
            [wait_task, disconnect_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        if shutdown_event.is_set():
            break

        if reconnect_delay > INITIAL_RECONNECT_DELAY:
            logger.info("Reconnecting in %ds...", reconnect_delay)
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=reconnect_delay)
            break
        except asyncio.TimeoutError:
            reconnect_delay = min(reconnect_delay * 2, MAX_RECONNECT_DELAY)
            continue

    if fyers:
        fyers.close_connection()
    pub_task.cancel()
    await r.aclose()
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
