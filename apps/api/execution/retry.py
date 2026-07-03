import asyncio
import logging
import random
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_DELAY = 1.0
MAX_DELAY = 30.0

TRANSIENT_EXCEPTIONS = (
    asyncio.TimeoutError,
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    httpx.ReadTimeout,
)

TRANSIENT_ERRORS = {
    "TIMEOUT",
    "CONNECTION_RESET",
    "NETWORK_ERROR",
    "RATE_LIMITED",
    "TOKEN_EXPIRED",
    "BROKER_UNAVAILABLE",
    "SERVICE_OVERLOADED",
}

NON_TRANSIENT_ERRORS = {
    "INVALID_SYMBOL",
    "INVALID_QUANTITY",
    "INVALID_PRICE",
    "INVALID_PRODUCT",
    "INVALID_ORDER_TYPE",
    "MARGIN_INSUFFICIENT",
    "DUPLICATE_ORDER",
    "ORDER_REJECTED",
    "USER_CANCELLED",
    "INSTRUMENT_NOT_TRADABLE",
    "EXCHANGE_CLOSED",
    "VALIDATION_FAILED",
}


def is_transient(error_code: str) -> bool:
    code = error_code.upper().strip()
    if code in NON_TRANSIENT_ERRORS:
        return False
    if code in TRANSIENT_ERRORS:
        return True
    return False


async def retry_with_backoff(
    operation_name: str,
    operation,
    *args,
    max_retries: int = MAX_RETRIES,
    base_delay: float = BASE_DELAY,
    **kwargs,
) -> tuple[Any, int, float]:
    last_error = None
    total_delay = 0.0

    for attempt in range(max_retries + 1):
        try:
            start = asyncio.get_event_loop().time()
            result = await operation(*args, **kwargs)
            elapsed = (asyncio.get_event_loop().time() - start) * 1000
            return result, attempt, elapsed
        except Exception as e:
            last_error = e
            if isinstance(e, TRANSIENT_EXCEPTIONS):
                pass
            else:
                error_code = getattr(e, "code", "") or getattr(e, "message", str(e))
                if not is_transient(str(error_code)):
                    logger.warning("Non-transient error in %s: %s — not retrying", operation_name, e)
                    raise

            if attempt < max_retries:
                delay = random.uniform(0, min(base_delay * (2 ** attempt), MAX_DELAY))
                total_delay += delay
                logger.info("Retrying %s in %.1fs (attempt %d/%d)", operation_name, delay, attempt + 1, max_retries)
                await asyncio.sleep(delay)

    raise last_error
