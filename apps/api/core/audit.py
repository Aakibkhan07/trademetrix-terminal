from core.db import get_supabase
from core.models import AuditLogEntry


def record_audit(entry: AuditLogEntry) -> None:
    supabase = get_supabase()
    try:
        supabase.table("audit_log").insert(entry.model_dump(mode="json")).execute()
    except Exception:
        pass
