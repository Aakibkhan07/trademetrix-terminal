import logging
from typing import Any

logger = logging.getLogger(__name__)


class AppException(Exception):
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status: int = 500, details: dict | None = None):
        self.message = message
        self.code = code
        self.status = status
        self.details = details or {}
        super().__init__(self.message)


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found", details: dict | None = None):
        super().__init__(message=message, code="NOT_FOUND", status=404, details=details)


class InvalidRequestException(AppException):
    def __init__(self, message: str = "Invalid request", details: dict | None = None):
        super().__init__(message=message, code="INVALID_REQUEST", status=400, details=details)


class AuthFailedException(AppException):
    def __init__(self, message: str = "Authentication failed", details: dict | None = None):
        super().__init__(message=message, code="AUTH_FAILED", status=401, details=details)


class ForbiddenException(AppException):
    def __init__(self, message: str = "Forbidden", details: dict | None = None):
        super().__init__(message=message, code="FORBIDDEN", status=403, details=details)


class RateLimitException(AppException):
    def __init__(self, message: str = "Rate limit exceeded", details: dict | None = None):
        super().__init__(message=message, code="RATE_LIMITED", status=429, details=details)


class BrokerException(AppException):
    def __init__(self, message: str = "Broker error", code: str = "BROKER_ERROR", status: int = 502, details: dict | None = None):
        super().__init__(message=message, code=code, status=status, details=details)


class ServiceUnavailableException(AppException):
    def __init__(self, message: str = "Service unavailable", details: dict | None = None):
        super().__init__(message=message, code="SERVICE_UNAVAILABLE", status=503, details=details)
