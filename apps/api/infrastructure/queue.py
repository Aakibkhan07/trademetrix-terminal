import asyncio
import json
import logging
import time

from core.events import EventType

logger = logging.getLogger(__name__)

_QUEUE_KEY = "app:events"
_last_redis_attempt: float = 0
_REDIS_RETRY_INTERVAL: float = 30.0


async def _ensure_redis():
    global _last_redis_attempt
    from core.cache import cache
    now = time.monotonic()
    if cache._enabled:
        return cache._redis
    if now - _last_redis_attempt < _REDIS_RETRY_INTERVAL:
        return None
    _last_redis_attempt = now
    try:
        await cache.init()
    except Exception:
        pass
    return cache._redis if cache._enabled else None


async def publish(_type: EventType | str, payload: dict, _redis=None) -> None:
    try:
        if _redis is None:
            _redis = await _ensure_redis()
        if _redis is None:
            return
        await _redis.lpush(_QUEUE_KEY, json.dumps({
            "type": str(_type),
            "payload": payload,
        }))
    except Exception as e:
        logger.warning("Failed to publish event %s: %s", _type, e)


async def subscribe(batch_size: int = 10, timeout: int = 5) -> list[dict]:
    try:
        redis = await _ensure_redis()
        if redis:
            result = await redis.brpop(_QUEUE_KEY, timeout=timeout)
            if result:
                return [json.loads(result[1])]
        await asyncio.sleep(1)
        return []
    except Exception as e:
        logger.warning("Event queue subscribe error: %s", e)
        await asyncio.sleep(1)
        return []
