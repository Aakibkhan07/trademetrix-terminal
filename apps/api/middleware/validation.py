import json
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


MAX_REQUEST_SIZE = 1024 * 100
ALLOWED_CONTENT_TYPES = {"application/json", "multipart/form-data", "application/x-www-form-urlencoded", ""}


class InputValidationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, max_size: int = MAX_REQUEST_SIZE):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        content_type = request.headers.get("content-type", "").split(";")[0].strip()

        if request.method in ("POST", "PUT", "PATCH"):
            if content_type and content_type not in ALLOWED_CONTENT_TYPES:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=415, content={"detail": f"Unsupported content type: {content_type}"})

            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.max_size:
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Request too large. Max {self.max_size} bytes"},
                )

        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Cache-Control"] = "no-store"

        return response
