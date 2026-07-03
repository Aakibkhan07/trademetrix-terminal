import logging
import time
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger("api.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.monotonic()
        rid = getattr(request.state, "request_id", "-")
        method = request.method
        path = request.url.path

        response = await call_next(request)

        duration_ms = (time.monotonic() - start) * 1000
        status = response.status_code

        logger.info(
            "%s %s %d %.1fms [%s]",
            method, path, status, duration_ms, rid,
            extra={"request_id": rid, "method": method, "path": path, "status": status, "duration_ms": round(duration_ms, 1)},
        )
        response.headers["X-Request-Time-MS"] = str(round(duration_ms, 1))
        return response
