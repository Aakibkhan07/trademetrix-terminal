import time
from collections import defaultdict
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from core.cache import cache


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, requests_per_minute: int = 120):
        super().__init__(app)
        self.rpm = requests_per_minute
        self._fallback_windows: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.monotonic()

    @staticmethod
    def _is_budget_exempt(path: str) -> bool:
        """Fire-and-forget client telemetry must never starve functional
        endpoints: the 5s analytics batch alone consumes 12 of the old 60 RPM
        budget and tripped 429s for real browser sessions."""
        return path.startswith("/api/v1/analytics/track-batch")

    def _cleanup_stale_fallback(self):
        now = time.monotonic()
        cutoff = now - 60.0
        stale_ips = []
        for ip, window in list(self._fallback_windows.items()):
            while window and window[0] < cutoff:
                window.pop(0)
            if not window:
                stale_ips.append(ip)
        for ip in stale_ips:
            del self._fallback_windows[ip]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path.startswith(("/api/v1",)):
            now = time.monotonic()
            client_ip = request.client.host if request.client else "unknown"

            remaining = self.rpm
            window_size = 60
            redis_key = f"ratelimit:{client_ip}"

            if self._is_budget_exempt(request.url.path):
                response = await call_next(request)
                response.headers["X-RateLimit-Limit"] = str(self.rpm)
                response.headers["X-RateLimit-Remaining"] = str(self.rpm)
                return response

            count = await cache.increment(redis_key, ttl=window_size)
            if count > 0:
                remaining = max(0, self.rpm - count)
                if count > self.rpm:
                    from fastapi.responses import JSONResponse
                    resp = JSONResponse(
                        status_code=429,
                        content={"detail": "Rate limit exceeded. Try again in 60 seconds."},
                        headers={
                            "Retry-After": "60",
                            "X-RateLimit-Limit": str(self.rpm),
                            "X-RateLimit-Remaining": "0",
                        },
                    )
                    return resp
            else:
                if now - self._last_cleanup > 60.0:
                    self._cleanup_stale_fallback()
                    self._last_cleanup = now
                window = self._fallback_windows[client_ip]
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
                        },
                    )
                    return resp
                window.append(now)

        response = await call_next(request)
        if request.url.path.startswith(("/api/v1",)):
            response.headers["X-RateLimit-Limit"] = str(self.rpm)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
