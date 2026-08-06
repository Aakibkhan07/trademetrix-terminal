import asyncio
import logging

from core.db import get_supabase
from core.models import AuditLogEntry

logger = logging.getLogger(__name__)


def _do_insert(entry: AuditLogEntry) -> None:
    try:
        supabase = get_supabase()
        data = entry.model_dump(mode="json")
        # Unauthenticated/system events (e.g. login throttling) have no actor;
        # user_id is a nullable UUID column — PostgREST rejects "" (22P02).
        if not data.get("user_id"):
            data["user_id"] = None
        supabase.table("audit_log").insert(data).execute()
    except Exception as e:
        logger.warning("Failed to record audit entry: %s", e)


def record_audit(entry: AuditLogEntry) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _do_insert(entry)
        return

    try:
        loop.run_in_executor(None, _do_insert, entry)
    except RuntimeError:
        _do_insert(entry)
