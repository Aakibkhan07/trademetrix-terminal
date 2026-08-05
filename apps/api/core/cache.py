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
                socket_connect_timeout=5,
                socket_timeout=10,
            )
            await self._redis.ping()
            self._enabled = True
            logger.info("Redis cache connected at %s", settings.redis_url)
        except Exception as e:
            self._enabled = False
            logger.warning("Redis not available, cache disabled: %s", e)

    async def get_redis(self):
        """Return the raw async redis client (lazy init), or None if unavailable."""
        if not self._enabled:
            await self.init()
        if not self._enabled:
            return None
        return self._redis

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
            if ttl is None:
                await self._redis.set(key, json.dumps(value))
            else:
                await self._redis.set(key, json.dumps(value), ex=ttl)
            return True
        except Exception:
            return False

    async def set_nx(self, key: str, value: Any, ttl: int = 300) -> bool:
        if not self._enabled or not self._redis:
            return False
        try:
            result = await self._redis.set(key, json.dumps(value), ex=ttl, nx=True)
            return result is not None
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

    async def rpush(self, key: str, value: str) -> bool:
        if not self._enabled or not self._redis:
            return False
        try:
            await self._redis.rpush(key, value)
            return True
        except Exception:
            return False

    async def lpop(self, key: str) -> str | None:
        if not self._enabled or not self._redis:
            return None
        try:
            return await self._redis.lpop(key)
        except Exception:
            return None

    async def increment(self, key: str, ttl: int = 60) -> int:
        if not self._enabled or not self._redis:
            return 0
        try:
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, ttl)
            return count
        except Exception:
            return 0

    async def ttl(self, key: str) -> int:
        if not self._enabled or not self._redis:
            return -1
        try:
            return await self._redis.ttl(key)
        except Exception:
            return -2


cache = RedisCache()
