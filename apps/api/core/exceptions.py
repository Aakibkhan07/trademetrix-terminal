import logging

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status: int = 500, details: dict | None = None):
        self.message = message
        self.code = code
        self.status = status
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found", details: dict | None = None):
        super().__init__(message=message, code="NOT_FOUND", status=404, details=details)


class InvalidRequestError(AppError):
    def __init__(self, message: str = "Invalid request", details: dict | None = None):
        super().__init__(message=message, code="INVALID_REQUEST", status=400, details=details)


class AuthFailedError(AppError):
    def __init__(self, message: str = "Authentication failed", details: dict | None = None):
        super().__init__(message=message, code="AUTH_FAILED", status=401, details=details)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Forbidden", details: dict | None = None):
        super().__init__(message=message, code="FORBIDDEN", status=403, details=details)


class RateLimitError(AppError):
    def __init__(self, message: str = "Rate limit exceeded", details: dict | None = None):
        super().__init__(message=message, code="RATE_LIMITED", status=429, details=details)


class BrokerTokenExpiredError(AppError):
    """The broker access token is expired/unusable and needs re-auth.

    Surfaced as HTTP 401 with a structured ``BROKER_TOKEN_EXPIRED`` code so the
    web app can prompt the user to re-authenticate instead of showing a raw 500.
    """

    def __init__(self, message: str = "Broker access token expired — re-authenticate", details: dict | None = None):
        super().__init__(message=message, code="BROKER_TOKEN_EXPIRED", status=401, details=details)


class BrokerError(AppError):
    def __init__(self, message: str = "Broker error", code: str = "BROKER_ERROR", status: int = 502, details: dict | None = None):
        super().__init__(message=message, code=code, status=status, details=details)


class ServiceUnavailableError(AppError):
    def __init__(self, message: str = "Service unavailable", details: dict | None = None):
        super().__init__(message=message, code="SERVICE_UNAVAILABLE", status=503, details=details)
