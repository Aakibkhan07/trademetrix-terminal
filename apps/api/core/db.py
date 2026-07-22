import asyncio
import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

import httpx
from supabase import Client, ClientOptions, create_client

from core.config import settings

logger = logging.getLogger(__name__)

_supabase: Client | None = None
_supabase_anon: Client | None = None
_supabase_lock = threading.Lock()
_supabase_available = threading.Event()
_supabase_available.set()

_db_executor = ThreadPoolExecutor(max_workers=32, thread_name_prefix="supabase")

T = TypeVar("T")


def _make_client(url: str, key: str) -> Client:
    return create_client(
        url, key,
        options=ClientOptions(
            httpx_client=httpx.Client(
                timeout=httpx.Timeout(15.0, connect=5.0),
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=20, keepalive_expiry=60),
            ),
        ),
    )


def get_supabase() -> Client:
    global _supabase
    if not _supabase_available.is_set():
        raise RuntimeError("Supabase client is closed or shutting down")
    if _supabase is None:
        with _supabase_lock:
            if _supabase is None:
                _supabase = _make_client(settings.supabase_url, settings.supabase_service_key)
    return _supabase


def get_supabase_anon() -> Client:
    global _supabase_anon
    if not _supabase_available.is_set():
        raise RuntimeError("Supabase client is closed or shutting down")
    if _supabase_anon is None:
        _supabase_anon = _make_client(settings.supabase_url, settings.supabase_anon_key)
    return _supabase_anon


async def close_supabase() -> None:
    global _supabase, _supabase_anon
    _supabase_available.clear()
    if _supabase:
        try:
            await asyncio.get_running_loop().run_in_executor(_db_executor, _supabase.auth.sign_out)
            await _supabase.postgrest.aclose()
        except Exception as e:
            logger.warning("Error closing supabase client: %s", e)
        _supabase = None
    if _supabase_anon and _supabase_anon.postgrest:
        try:
            await asyncio.get_running_loop().run_in_executor(_db_executor, _supabase_anon.auth.sign_out)
            await _supabase_anon.postgrest.aclose()
        except Exception as e:
            logger.warning("Error closing supabase anon client: %s", e)
        _supabase_anon = None


async def async_supabase(call: Callable[..., T], *args, **kwargs) -> T:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_db_executor, lambda: call(*args, **kwargs))
