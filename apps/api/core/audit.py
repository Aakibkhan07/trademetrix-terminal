import logging

from core.db import get_supabase
from core.models import AuditLogEntry

logger = logging.getLogger(__name__)


def record_audit(entry: AuditLogEntry) -> None:
    supabase = get_supabase()
    try:
        supabase.table("audit_log").insert(entry.model_dump(mode="json")).execute()
    except Exception as e:
        logger.warning("Failed to record audit entry: %s", e)
