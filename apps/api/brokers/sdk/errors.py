"""Typed broker error taxonomy + error translator.

Every broker adapter must raise a BrokerError subclass (never a bare Exception) so
callers can branch on `error.code` / `error.retryable` instead of string-matching.

Classification contract:
- BrokerRateLimitError / BrokerAuthError / BrokerConnectionError / BrokerTimeoutError
  are retryable (the transport decides whether a retry is safe for the operation).
- BrokerWAFError / BrokerValidationError / OrderRejectedError / UnsupportedFeatureError
  are never retried.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BrokerErrorInfo:
    """Structured error payload attached to every BrokerError."""

    code: str
    broker: str = ""
    retryable: bool = False
    http_status: int = 0
    retry_after: float | None = None
    detail: str = ""
    correlation_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "broker": self.broker,
            "retryable": self.retryable,
            "http_status": self.http_status,
            "retry_after": self.retry_after,
            "detail": self.detail,
            "correlation_id": self.correlation_id,
        }


class BrokerError(Exception):
    """Base class for every broker error. Never raise bare BrokerError from adapters."""

    code = "broker_error"
    retryable = False
    http_status = 0

    def __init__(
        self,
        message: str = "",
        *,
        broker: str = "",
        http_status: int = 0,
        retry_after: float | None = None,
        detail: str = "",
        correlation_id: str = "",
    ) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code
        self.broker = broker
        self.http_status = http_status or self.http_status
        self.retry_after = retry_after
        self.detail = detail
        self.correlation_id = correlation_id

    def info(self) -> BrokerErrorInfo:
        return BrokerErrorInfo(
            code=self.code,
            broker=self.broker,
            retryable=self.retryable,
            http_status=self.http_status,
            retry_after=self.retry_after,
            detail=self.detail or self.message,
            correlation_id=self.correlation_id,
        )

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.code}]{f' {self.broker}' if self.broker else ''}: {self.message}"


class UnsupportedFeatureError(BrokerError):
    """Raised when the caller requests a feature the broker does not support.

    This is the SDK's explicit contract: capability-unknown features surface as this
    typed error, never as AttributeError / unpredictable failures.
    """

    code = "unsupported_feature"
    retryable = False

    def __init__(self, feature: str, *, broker: str = "", detail: str = "") -> None:
        super().__init__(
            f"Broker{f' {broker}' if broker else ''} does not support: {feature}",
            broker=broker,
            detail=detail or f"Capability not declared: {feature}",
        )
        self.feature = feature


class BrokerAuthError(BrokerError):
    """Authentication / token failure (401, invalid session, token expired)."""

    code = "auth_error"
    retryable = True
    http_status = 401

    def __init__(
        self,
        message: str = "Broker authentication failed",
        *,
        http_status: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, http_status=http_status, **kwargs)


class BrokerRateLimitError(BrokerError):
    """HTTP 429 or Cloudflare 1015. Honours Retry-After when provided."""

    code = "rate_limited"
    retryable = True
    http_status = 429

    def __init__(
        self,
        message: str = "Broker rate limit exceeded",
        *,
        http_status: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, http_status=http_status, **kwargs)


class BrokerWAFError(BrokerError):
    """Cloudflare 403 WAF block. NEVER retried — retrying a WAF block escalates IP blocks."""

    code = "waf_blocked"
    retryable = False
    http_status = 403

    def __init__(
        self,
        message: str = "Broker endpoint blocked by Cloudflare WAF",
        *,
        http_status: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, http_status=http_status, **kwargs)


class BrokerConnectionError(BrokerError):
    """Network-level failure (connect refused, DNS, TLS, remote protocol error)."""

    code = "connection_error"
    retryable = True

    def __init__(self, message: str = "Broker connection failed", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class BrokerTimeoutError(BrokerError):
    """Request timed out. Retryable for reads; never for order writes."""

    code = "timeout"
    retryable = True

    def __init__(self, message: str = "Broker request timed out", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class BrokerDisconnectedError(BrokerError):
    """Adapter is not connected (no session). Caller should reconnect first."""

    code = "not_connected"
    retryable = True

    def __init__(self, message: str = "Broker adapter is not connected", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class BrokerValidationError(BrokerError):
    """4xx payload rejection that is not a WAF/auth/rate-limit (invalid symbol, bad product, etc.)."""

    code = "validation_error"
    retryable = False

    def __init__(self, message: str = "Broker rejected the request payload", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class OrderRejectedError(BrokerError):
    """Broker explicitly rejected an order (insufficient margin, invalid order, etc.)."""

    code = "order_rejected"
    retryable = False

    def __init__(self, message: str = "Order rejected by broker", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class MarginInsufficientError(OrderRejectedError):
    """Broker rejected the order because required margin is not available."""

    code = "insufficient_margin"

    def __init__(self, message: str = "Insufficient margin for order", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class BrokerServerError(BrokerError):
    """5xx upstream. Retryable (transport may cap attempts)."""

    code = "server_error"
    retryable = True
    http_status = 500

    def __init__(self, message: str = "Broker server error", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


def parse_retry_after(value: str | int | None) -> float | None:
    """Parse a Retry-After header: integer seconds or HTTP-date."""

    if value is None:
        return None
    if isinstance(value, (int, float)):
        return max(float(value), 0.0)
    try:
        return max(float(str(value).strip()), 0.0)
    except ValueError:
        return None


def translate_broker_error(
    *,
    status_code: int,
    body: Any = None,
    broker: str = "",
    headers: dict[str, str] | None = None,
    message: str = "",
    detail: str = "",
    correlation_id: str = "",
) -> BrokerError:
    """Translate an HTTP response into the typed broker error.

    Called by the transport after a wire call. Mapping:
    - 429, 1015  -> BrokerRateLimitError (Retry-After honoured)
    - 403        -> BrokerWAFError (Cloudflare) — never retried
    - 401, 400 with token keywords -> BrokerAuthError
    - 4xx        -> BrokerValidationError (order paths: OrderRejectedError)
    - 5xx        -> BrokerServerError
    """

    text = message or (str(body)[:500] if body is not None else "")
    lowered = (text + detail).lower()
    retry_after = parse_retry_after((headers or {}).get("Retry-After"))

    kwargs: dict[str, Any] = dict(
        broker=broker,
        http_status=status_code,
        retry_after=retry_after,
        detail=detail or text,
        correlation_id=correlation_id,
    )

    if status_code in (429, 1015):
        return BrokerRateLimitError(text or "rate limited", **kwargs)

    if status_code == 403:
        return BrokerWAFError(text or "WAF block", **kwargs)

    if status_code == 401 or any(kw in lowered for kw in ("token", "unauthorized", "expired", "auth")):
        return BrokerAuthError(text or "authentication failed", **kwargs)

    if status_code >= 500:
        return BrokerServerError(text or "server error", **kwargs)

    if status_code >= 400:
        return BrokerValidationError(text or f"http {status_code}", **kwargs)

    return BrokerError(f"unexpected status {status_code}: {text}", **kwargs)


def translate_exception(exc: Exception, *, broker: str = "") -> BrokerError:
    """Translate a raw exception (timeouts, connection errors) into typed errors."""

    import asyncio

    if isinstance(exc, BrokerError):
        if broker and not exc.broker:
            exc.broker = broker
        return exc

    if isinstance(exc, asyncio.TimeoutError):
        return BrokerTimeoutError(str(exc), broker=broker)

    if isinstance(exc, (ConnectionError, OSError)):
        return BrokerConnectionError(str(exc), broker=broker)

    return BrokerConnectionError(str(exc), broker=broker)
