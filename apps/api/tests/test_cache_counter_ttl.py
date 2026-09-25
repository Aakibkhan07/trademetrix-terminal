"""Regression tests: Redis counter TTL must self-heal.

`cache.increment` used to set the expiry only when the counter read 1. That is
the normal path, but if the EXPIRE is ever lost — process killed between the
two calls, a restored dump, a failover — the counter becomes immortal and
permanently rate-limits that client against every /api/v1 route until somebody
deletes the key by hand. An immortal `ratelimit:<ip>` key was observed in the
dev environment at count=660 with TTL -1.

Redis semantics relied on here:
  TTL returns -2 when the key does not exist, -1 when it exists with no expiry.
"""
import pytest

from core.cache import RedisCache


class FakeRedis:
    """Minimal async stand-in covering the incr/ttl/expire surface used here."""

    def __init__(self, initial=None, ttl=-1):
        self.value = initial
        self.ttl_value = ttl if initial is not None else -2
        self.expire_calls = []

    async def incr(self, key):
        self.value = (self.value or 0) + 1
        return self.value

    async def ttl(self, key):
        if self.value is None:
            return -2
        return self.ttl_value

    async def expire(self, key, ttl):
        self.expire_calls.append((key, ttl))
        self.ttl_value = ttl
        return True


def make_cache(redis):
    c = RedisCache()
    c._enabled = True
    c._redis = redis
    return c


@pytest.mark.asyncio
async def test_first_increment_sets_expiry():
    redis = FakeRedis()
    cache = make_cache(redis)

    assert await cache.increment("ratelimit:1.2.3.4", ttl=60) == 1
    assert redis.expire_calls == [("ratelimit:1.2.3.4", 60)]


@pytest.mark.asyncio
async def test_immortal_counter_gets_ttl_rearmed():
    """The bug: a stuck key with no expiry is healed on the next request."""
    redis = FakeRedis(initial=660, ttl=-1)
    cache = make_cache(redis)

    assert await cache.increment("ratelimit:1.2.3.4", ttl=60) == 661
    assert redis.expire_calls == [("ratelimit:1.2.3.4", 60)]
    assert redis.ttl_value == 60


@pytest.mark.asyncio
async def test_healthy_counter_does_not_extend_window():
    """Re-arming must not slide the window forward on every request."""
    redis = FakeRedis(initial=5, ttl=42)
    cache = make_cache(redis)

    assert await cache.increment("ratelimit:1.2.3.4", ttl=60) == 6
    assert redis.expire_calls == []


@pytest.mark.asyncio
async def test_disabled_cache_is_a_noop():
    cache = RedisCache()
    cache._enabled = False
    assert await cache.increment("ratelimit:1.2.3.4") == 0
