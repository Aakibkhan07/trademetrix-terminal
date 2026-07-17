import logging
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from core.cache import cache
from core.db import get_supabase

logger = logging.getLogger(__name__)

ADMIN_PATHS = ("/api/v1/admin/",)
WHITELIST_CACHE_TTL = 60


class AdminIPWhitelistMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def _get_whitelist(self) -> set[str]:
        cached = await cache.get("admin_ip_whitelist")
        if cached:
            return set(cached)
        try:
            supabase = get_supabase()
            rows = supabase.table("admin_ip_whitelist").select("ip_address").execute()
            ips = {r["ip_address"] for r in (rows.data or [])}
            await cache.set("admin_ip_whitelist", list(ips), ttl=WHITELIST_CACHE_TTL)
            return ips
        except Exception as e:
            logger.warning("Failed to load IP whitelist: %s", e)
            return set()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if path.startswith(ADMIN_PATHS):
            whitelist = await self._get_whitelist()
            if whitelist and "*" not in whitelist:
                client_ip = request.client.host if request.client else ""
                forwarded = request.headers.get("X-Forwarded-For", "")
                if forwarded:
                    client_ip = forwarded.split(",")[0].strip()
                if client_ip not in whitelist:
                    logger.warning("Blocked admin access from IP: %s", client_ip)
                    return Response(status_code=403, content="Forbidden: IP not whitelisted")
        return await call_next(request)
