import asyncio
import logging

from core.events import EventType
from infrastructure.queue import subscribe

logger = logging.getLogger(__name__)


_handlers: dict[str, list] = {}
_running = False


def register(event_type: EventType | str, handler) -> None:
    key = str(event_type)
    if key not in _handlers:
        _handlers[key] = []
    _handlers[key].append(handler)


async def start():
    global _running
    if _running:
        return
    _running = True
    asyncio.create_task(_run_loop())
    logger.info("Background worker started with %d handler types", len(_handlers))


async def stop():
    global _running
    _running = False


async def _run_loop():
    while _running:
        try:
            events = await subscribe(timeout=3)
            for event in events:
                await _dispatch(event)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Worker loop error: %s", e)
            await asyncio.sleep(1)


async def _dispatch(event: dict):
    event_type = event.get("type", "")
    payload = event.get("payload", {})
    handlers = _handlers.get(event_type, []) + _handlers.get("*", [])
    for handler in handlers:
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(payload)
            else:
                handler(payload)
        except Exception as e:
            logger.error("Handler %s failed for %s: %s", handler.__name__, event_type, e)
