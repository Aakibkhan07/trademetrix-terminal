from supabase import Client, create_client
from core.config import settings

_supabase: Client | None = None


def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(settings.supabase_url, settings.supabase_service_key)
    return _supabase


def get_supabase_anon() -> Client:
    return create_client(settings.supabase_url, settings.supabase_anon_key)
