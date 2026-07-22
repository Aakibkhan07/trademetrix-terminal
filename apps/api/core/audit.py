import asyncio
import logging

from core.db import get_supabase
from core.models import AuditLogEntry

logger = logging.getLogger(__name__)


def _do_insert(entry: AuditLogEntry) -> None:
    try:
        supabase = get_supabase()
        supabase.table("audit_log").insert(entry.model_dump(mode="json")).execute()
    except Exception as e:
        logger.warning("Failed to record audit entry: %s", e)


def record_audit(entry: AuditLogEntry) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _do_insert(entry)
        return

    loop.run_in_executor(None, _do_insert, entry)
