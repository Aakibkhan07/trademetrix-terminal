import asyncio
import json
import logging
from datetime import UTC, datetime

from core.cache import cache
from core.notifications import send_telegram_alert

logger = logging.getLogger(__name__)

WEBHOOK_RETRY_KEY = "webhook:retry_queue"
MAX_RETRIES = 3
RETRY_BACKOFF = [30, 120, 600]

async def enqueue_webhook(payload: dict) -> None:
    entry = {
        "payload": payload,
        "retries": 0,
        "last_attempt": None,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await cache.rpush(WEBHOOK_RETRY_KEY, json.dumps(entry))
    logger.info("Webhook queued for retry: %s", payload.get("symbol", "?"))

async def dequeue_webhooks() -> list[dict]:
    entries = []
    while True:
        raw = await cache.lpop(WEBHOOK_RETRY_KEY)
        if not raw:
            break
        try:
            entries.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return entries

async def retry_webhook_worker():
    from application.services.tradingview_service import TradingViewService
    svc = TradingViewService()
    await asyncio.sleep(15)
    while True:
        try:
            entries = await dequeue_webhooks()
            for entry in entries:
                retries = entry.get("retries", 0)
                if retries >= MAX_RETRIES:
                    await send_telegram_alert(
                        f"\u274c <b>Webhook failed after {MAX_RETRIES} retries</b>\n"
                        f"Symbol: {entry['payload'].get('symbol', '?')}\n"
                        f"Action: {entry['payload'].get('action', '?')}"
                    )
                    continue
                try:
                    result = await svc.handle_webhook(
                        json.dumps(entry["payload"]).encode(),
                        entry["payload"].get("_signature", ""),
                    )
                    err_str = str(result).lower()
                    if result and "error" not in err_str and "invalid" not in err_str:
                        logger.info("Webhook retry success: %s", entry["payload"].get("symbol", "?"))
                        continue
                except Exception as e:
                    logger.warning("Webhook retry attempt %d failed: %s", retries + 1, e)

                entry["retries"] = retries + 1
                entry["last_attempt"] = datetime.now(UTC).isoformat()
                await cache.rpush(WEBHOOK_RETRY_KEY, json.dumps(entry))
                logger.info("Webhook re-queued for retry %d", entry["retries"])
        except Exception as e:
            logger.warning("Webhook retry worker error: %s", e)
        await asyncio.sleep(30)