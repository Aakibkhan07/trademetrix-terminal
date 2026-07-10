import logging

from core.audit import record_audit
from core.events import EventType
from core.models import AuditLogEntry
from infrastructure.worker import register

logger = logging.getLogger(__name__)


async def handle_audit_event(payload: dict) -> None:
    try:
        entry = AuditLogEntry(
            user_id=payload.get("user_id", ""),
            action=payload.get("action", ""),
            resource=payload.get("resource", ""),
            resource_id=payload.get("resource_id"),
            details=payload.get("details"),
        )
        record_audit(entry)
    except Exception as e:
        logger.warning("Async audit handler failed: %s", e)


async def handle_notification(payload: dict) -> None:
    try:
        from core.notifications import send_notification
        await send_notification(payload)
    except Exception as e:
        logger.warning("Async notification handler failed: %s", e)


def register_handlers():
    register(EventType.AUDIT_LOG, handle_audit_event)
    register(EventType.NOTIFICATION, handle_notification)
    logger.info("Registered %d event handlers", 2)
