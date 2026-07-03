"""
Distributed tracing context — propagates trace/span IDs through async tasks.

Usage:
    from core.tracing import get_trace_ctx, set_trace_ctx, TraceContext

    # In middleware: create context at request entry
    ctx = TraceContext(request_id=..., span_id=...)
    set_trace_ctx(ctx)

    # In downstream code: retrieve context
    ctx = get_trace_ctx()
    logger.info("operation", extra={"trace_id": ctx.trace_id})

Rollback: Delete this file and revert core/middleware/request_id.py.
"""

import contextvars
import uuid

from pydantic import BaseModel


class TraceContext(BaseModel):
    request_id: str = ""
    trace_id: str = ""
    parent_span_id: str = ""
    span_id: str = ""

    @classmethod
    def new(cls) -> "TraceContext":
        trace_id = str(uuid.uuid4())
        return cls(
            request_id=trace_id,
            trace_id=trace_id,
            span_id=str(uuid.uuid4()),
        )

    def new_child(self) -> "TraceContext":
        return TraceContext(
            request_id=self.request_id,
            trace_id=self.trace_id,
            parent_span_id=self.span_id,
            span_id=str(uuid.uuid4()),
        )


_trace_ctx: contextvars.ContextVar[TraceContext | None] = contextvars.ContextVar("trace_ctx", default=None)


def get_trace_ctx() -> TraceContext | None:
    return _trace_ctx.get()


def set_trace_ctx(ctx: TraceContext | None) -> None:
    if ctx is None:
        _trace_ctx.set(None)
    else:
        _trace_ctx.set(ctx)
