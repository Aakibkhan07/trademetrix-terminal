"""
Kill switch — SEBI-mandated ability to halt algo execution instantly.

  - GLOBAL: admin panic button. When tripped, dispatch_signal aborts the whole
    batch before any order is placed.
  - PER-USER: halt one customer (e.g. margin call, dispute) without affecting
    others.

Redis-backed so every worker/process sees the same state immediately.
"""

from __future__ import annotations

from functools import lru_cache

import redis.asyncio as aioredis

from ..config import get_settings

_GLOBAL = "exec:kill:global"
_USER = "exec:kill:user:"


@lru_cache(maxsize=1)
def _redis() -> aioredis.Redis:
    return aioredis.from_url(get_settings().redis_url, decode_responses=True)


async def is_global_tripped() -> bool:
    return await _redis().exists(_GLOBAL) == 1


async def trip_global(reason: str = "admin") -> None:
    await _redis().set(_GLOBAL, reason)


async def reset_global() -> None:
    await _redis().delete(_GLOBAL)


async def is_user_tripped(user_id: str) -> bool:
    return await _redis().exists(f"{_USER}{user_id}") == 1


async def trip_user(user_id: str, reason: str = "admin") -> None:
    await _redis().set(f"{_USER}{user_id}", reason)


async def reset_user(user_id: str) -> None:
    await _redis().delete(f"{_USER}{user_id}")


# ---------------------------------------------------------------------------
# Idempotency guard — stops the same signal double-firing to the same user
# on retries or concurrent dispatch.
# ---------------------------------------------------------------------------
async def claim_once(signal_id: str, user_id: str, ttl: int = 86400) -> bool:
    """
    Returns True if this (signal, user) pair is claimed for the first time.
    False means it was already processed — skip.
    """
    key = f"exec:idem:{signal_id}:{user_id}"
    # SET NX -> only sets if absent; returns True on first claim.
    return bool(await _redis().set(key, "1", nx=True, ex=ttl))
