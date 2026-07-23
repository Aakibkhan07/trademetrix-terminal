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
        self._last_cleanup = time.monotonic()

    def _cleanup_stale(self):
        now = time.monotonic()
        cutoff = now - 60.0
        stale_ips = [ip for ip, window in self._windows.items() if not window or window[-1] < cutoff]
        for ip in stale_ips:
            del self._windows[ip]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path.startswith(("/api/v1",)):
            now = time.monotonic()

            if now - self._last_cleanup > 60.0:
                self._cleanup_stale()
                self._last_cleanup = now

            client_ip = request.client.host if request.client else "unknown"
            window = self._windows[client_ip]
            cutoff = now - 60.0

            while window and window[0] < cutoff:
                window.pop(0)

            remaining = max(0, self.rpm - len(window))

            if len(window) >= self.rpm:
                from fastapi.responses import JSONResponse
                resp = JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Try again in 60 seconds."},
                    headers={
                        "Retry-After": "60",
                        "X-RateLimit-Limit": str(self.rpm),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(cutoff + 60)),
                    },
                )
                return resp

            window.append(now)

        response = await call_next(request)
        if request.url.path.startswith(("/api/v1",)):
            response.headers["X-RateLimit-Limit"] = str(self.rpm)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
