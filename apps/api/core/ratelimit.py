import time
from collections import defaultdict
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, requests_per_minute: int = 60):
        super().__init__(app)
        self.rpm = requests_per_minute
        self._windows: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path.startswith(("/api/v1",)):
            client_ip = request.client.host if request.client else "unknown"
            window = self._windows[client_ip]
            now = time.monotonic()
            cutoff = now - 60.0

            while window and window[0] < cutoff:
                window.pop(0)

            if len(window) >= self.rpm:
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Try again in 60 seconds."},
                    headers={"Retry-After": "60"},
                )

            window.append(now)

        return await call_next(next)
