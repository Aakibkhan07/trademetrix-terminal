from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from core.config import settings

MAX_REQUEST_SIZE = settings.max_request_size_bytes
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

        return await call_next(request)
