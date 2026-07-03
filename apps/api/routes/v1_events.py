import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from core.deps import get_current_user
from core.models import UserProfile
from execution.event_bus import ExecutionEvent, execution_event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/stream")
async def event_stream(request: Request, current_user: UserProfile = Depends(get_current_user)):
    queue: asyncio.Queue = asyncio.Queue()

    async def event_handler(event: ExecutionEvent):
        if event.user_id in ("", current_user.id):
            await queue.put(event)

    execution_event_bus.subscribe("*", event_handler)

    async def generate():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    data = {
                        "type": event.event_type,
                        "execution_request_id": event.execution_request_id,
                        "user_id": event.user_id,
                        "broker": event.broker,
                        "symbol": event.symbol,
                        "side": event.side,
                        "state": event.state.value if event.state else "",
                        "message": event.message,
                        "payload": event.payload,
                        "timestamp": event.timestamp.isoformat(),
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            execution_event_bus.unsubscribe("*", event_handler)

    return StreamingResponse(generate(), media_type="text/event-stream")
