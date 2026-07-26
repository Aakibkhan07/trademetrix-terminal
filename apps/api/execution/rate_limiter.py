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
_RATE_BREACH_COUNT: dict[str, int] = {}
_RATE_BREACH_LOCK = asyncio.Lock()


async def _alert_if_breaching(broker: str):
    global _RATE_BREACH_COUNT
    async with _RATE_BREACH_LOCK:
        _RATE_BREACH_COUNT[broker] = _RATE_BREACH_COUNT.get(broker, 0) + 1
        count = _RATE_BREACH_COUNT[broker]
        if count in (1, 5, 10, 25, 50):
            from core.notifications import send_telegram_alert
            await send_telegram_alert(
                f"\u26a0\ufe0f <b>Rate Limit Breach</b>\n"
                f"Broker: {broker.upper()}\n"
                f"Occurrences: {count}\n"
                f"Action: Reduce broadcast frequency"
            )


async def acquire_broker_token(broker: str) -> float:
    global _buckets
    async with _lock:
        if broker not in _buckets:
            _buckets[broker] = TokenBucket(broker)
    wait = await _buckets[broker].acquire()
    if wait > 0:
        logger.info("Rate-limited broker=%s waited %.1fs", broker, wait)
        from core.prometheus import record_rate_limit_breach
        record_rate_limit_breach(broker)
        await _alert_if_breaching(broker)
    return wait
