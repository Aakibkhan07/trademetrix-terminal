from unittest.mock import MagicMock, patch

from core.audit import _do_insert
from core.models import AuditLogEntry


def _inserted_payload():
    table = MagicMock()
    supabase = MagicMock()
    supabase.table.return_value = table
    table.insert.return_value.execute.return_value = MagicMock()
    return supabase, table


def test_empty_user_id_coerced_to_none():
    supabase, table = _inserted_payload()
    entry = AuditLogEntry(
        user_id="",
        action="login_locked",
        resource="auth",
        details={"email": "x@y.z", "ip": "1.2.3.4", "attempts": 6},
    )
    with patch("core.audit.get_supabase", return_value=supabase):
        _do_insert(entry)
    payload = table.insert.call_args[0][0]
    assert payload["user_id"] is None
    assert payload["action"] == "login_locked"


def test_non_empty_user_id_preserved():
    supabase, table = _inserted_payload()
    entry = AuditLogEntry(
        user_id="18b0cce7-33d9-465d-94cf-900148b57555",
        action="signin",
        resource="auth",
    )
    with patch("core.audit.get_supabase", return_value=supabase):
        _do_insert(entry)
    payload = table.insert.call_args[0][0]
    assert payload["user_id"] == "18b0cce7-33d9-465d-94cf-900148b57555"