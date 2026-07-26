import asyncio
import logging
import time

logger = logging.getLogger(__name__)

BROKER_RATE_LIMITS: dict[str, dict] = {
    "fyers": {"calls": 50, "window": 60},
    "zerodha": {"calls": 50, "window": 60},
    "dhan": {"calls": 100, "window": 60},
    "angelone": {"calls": 50, "window": 60},
    "upstox": {"calls": 100, "window": 60},
    "fivepaisa": {"calls": 30, "window": 60},
    "aliceblue": {"calls": 30, "window": 60},
    "finvasia": {"calls": 50, "window": 60},
    "flattrade": {"calls": 50, "window": 60},
    "kotakneo": {"calls": 50, "window": 60},
    "paper": {"calls": 1000, "window": 60},
}

class TokenBucket:
    def __init__(self, broker: str):
        limits = BROKER_RATE_LIMITS.get(broker, {"calls": 30, "window": 60})
        self.max_tokens = limits["calls"]
        self.window = limits["window"]
        self.tokens = self.max_tokens
        self.refill_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.refill_at
            if elapsed >= self.window:
                self.tokens = self.max_tokens
                self.refill_at = now
            if self.tokens > 0:
                self.tokens -= 1
                return 0.0
            wait = self.window - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
            self.tokens = self.max_tokens - 1
            self.refill_at = time.monotonic()
            return wait

_buckets: dict[str, TokenBucket] = {}
_lock = asyncio.Lock()

async def acquire_broker_token(broker: str) -> float:
    global _buckets
    async with _lock:
        if broker not in _buckets:
            _buckets[broker] = TokenBucket(broker)
    wait = await _buckets[broker].acquire()
    if wait > 0:
        logger.info("Rate-limited broker=%s waited %.1fs", broker, wait)
    return wait
