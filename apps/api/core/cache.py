import asyncio
import json
import logging
from typing import Any, Optional

from core.config import settings

logger = logging.getLogger(__name__)


class RedisCache:
    _instance: Optional["RedisCache"] = None
    _redis = None
    _enabled = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def init(self):
        if self._enabled:
            return
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await self._redis.ping()
            self._enabled = True
            logger.info("Redis cache connected at %s", settings.redis_url)
        except Exception as e:
            self._enabled = False
            logger.warning("Redis not available, cache disabled: %s", e)

    async def get(self, key: str, default: Any = None) -> Any:
        if not self._enabled or not self._redis:
            return default
        try:
            val = await self._redis.get(key)
            if val is None:
                return default
            return json.loads(val)
        except Exception:
            return default

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        if not self._enabled or not self._redis:
            return False
        try:
            await self._redis.setex(key, ttl, json.dumps(value))
            return True
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        if not self._enabled or not self._redis:
            return False
        try:
            await self._redis.delete(key)
            return True
        except Exception:
            return False

    async def close(self):
        if self._redis:
            await self._redis.close()
            self._redis = None


cache = RedisCache()
