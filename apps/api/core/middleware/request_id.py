import uuid
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from core.tracing import TraceContext, set_trace_ctx


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID"):
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        rid = request.headers.get(self.header_name) or str(uuid.uuid4())
        request.state.request_id = rid

        trace_id = request.headers.get("X-Trace-ID") or rid
        span_id = request.headers.get("X-Span-ID") or str(uuid.uuid4())
        parent_span_id = request.headers.get("X-Parent-Span-ID", "")

        ctx = TraceContext(
            request_id=rid,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            span_id=span_id,
        )
        set_trace_ctx(ctx)

        response = await call_next(request)
        response.headers[self.header_name] = rid
        response.headers["X-Trace-ID"] = trace_id

        set_trace_ctx(None)
        return response
