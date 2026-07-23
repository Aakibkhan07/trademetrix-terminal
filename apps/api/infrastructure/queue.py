import json
import logging

from core.events import EventType

logger = logging.getLogger(__name__)

_QUEUE_KEY = "app:events"


async def publish(_type: EventType | str, payload: dict, _redis=None) -> None:
    try:
        if _redis is None:
            from core.cache import cache
            if not hasattr(cache, '_redis') or cache._redis is None:
                await cache.init()
            _redis = cache._redis
        if _redis:
            await _redis.lpush(_QUEUE_KEY, json.dumps({
                "type": str(_type),
                "payload": payload,
            }))
    except Exception as e:
        logger.warning("Failed to publish event %s: %s", _type, e)


async def subscribe(batch_size: int = 10, timeout: int = 5) -> list[dict]:
    try:
        from core.cache import cache
        if not hasattr(cache, '_redis') or cache._redis is None:
            await cache.init()
        if cache._redis:
            result = await cache._redis.brpop(_QUEUE_KEY, timeout=timeout)
            if result:
                return [json.loads(result[1])]
        return []
    except Exception as e:
        logger.warning("Event queue subscribe error: %s", e)
        return []
