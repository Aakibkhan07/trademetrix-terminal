import asyncio
import functools
import inspect
import logging
import time
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


class CircuitBreakerState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self._lock = asyncio.Lock()

    async def call(self, fn: Callable[..., T], *args: Any, fallback: T = None, **kwargs: Any) -> T:
        async with self._lock:
            if self.state == CircuitBreakerState.OPEN:
                if time.monotonic() - self.last_failure_time >= self.recovery_timeout:
                    self.state = CircuitBreakerState.HALF_OPEN
                    logger.info("CircuitBreaker[%s] half-open, allowing trial", self.name)
                else:
                    logger.warning("CircuitBreaker[%s] open, using fallback", self.name)
                    if fallback is not None:
                        return fallback
                    raise Exception(f"CircuitBreaker[{self.name}] is open")

        try:
            if inspect.iscoroutinefunction(fn):
                result = await fn(*args, **kwargs)
            else:
                result = fn(*args, **kwargs)

            async with self._lock:
                if self.state == CircuitBreakerState.HALF_OPEN:
                    self.state = CircuitBreakerState.CLOSED
                    self.failure_count = 0
                    logger.info("CircuitBreaker[%s] closed (trial succeeded)", self.name)
                else:
                    self.failure_count = 0
            return result

        except Exception:
            async with self._lock:
                self.failure_count += 1
                self.last_failure_time = time.monotonic()
                if self.failure_count >= self.failure_threshold:
                    self.state = CircuitBreakerState.OPEN
                    logger.error("CircuitBreaker[%s] opened (failures=%d)", self.name, self.failure_count)
            if fallback is not None:
                return fallback
            raise


def retry(max_attempts: int = 3, base_delay: float = 0.5, max_delay: float = 10.0,
          retryable_exceptions: tuple = (Exception,)):
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    if inspect.iscoroutinefunction(fn):
                        return await fn(*args, **kwargs)
                    return fn(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exc = e
                    if attempt < max_attempts:
                        delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                        logger.warning("Retry %d/%d for %s after %.2fs: %s", attempt, max_attempts, fn.__name__, delay, e)
                        await asyncio.sleep(delay)
            raise last_exc
        return wrapper
    return decorator


async def safe_external_call[T](fn: Callable[..., T], *args: Any,
                                  fallback: T = None,
                                  retries: int = 2, cb_name: str = "default",
                                  **kwargs: Any) -> T:
    breaker = _get_breaker(cb_name)

    @retry(max_attempts=retries + 1)
    async def with_retry():
        return await breaker.call(fn, fallback=fallback, *args, **kwargs)

    return await with_retry()


_breakers: dict[str, CircuitBreaker] = {}

def _get_breaker(name: str) -> CircuitBreaker:
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name=name)
    return _breakers[name]


def get_circuit_breaker_stats() -> dict:
    return {
        name: {"state": cb.state, "failures": cb.failure_count}
        for name, cb in _breakers.items()
    }
