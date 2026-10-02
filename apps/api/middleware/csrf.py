import secrets
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from core.config import settings

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SAFE_PATHS = {
    "/api/v1/auth/signin",
    "/api/v1/auth/signup",
    "/api/v1/auth/signout",
    "/api/v1/auth/profile",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/send-otp",
    "/api/v1/auth/register-with-otp",
    "/api/v1/auth/verify-otp",
    "/api/v1/tradingview/webhook",
    "/api/v1/subscriptions/webhook",
    "/api/v1/subscriptions/webhook/",
    "/api/v1/marketdata/feed/start",
    "/api/v1/marketdata/feed/stop",
    "/api/v1/marketdata/quote",
    "/api/v1/marketdata/historical",
    "/api/v1/marketdata/option-chain",
    "/api/v1/marketdata/simulator/start",
    "/api/v1/marketdata/simulator/stop",
    "/api/v1/admin/assignments",
    "/api/v1/admin/broadcast",
    "/api/v1/admin/broadcast/recipients",
    "/api/v1/alerts",
    "/api/v1/brokers/fyers/callback",
    "/api/v1/brokers/dhan/callback",
    "/api/v1/brokers/upstox/callback",
    "/api/v1/broker/connect",
    "/api/v1/broker/connect-credentials",
    "/api/v1/broker/status",
    "/api/v1/broker/available",
    "/api/v1/broker/disconnect",
    "/api/v1/broker/callback",
}

CSRF_COOKIE_NAME = "csrf_token"


class CSRFProtectMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method in MUTATING_METHODS and request.url.path not in SAFE_PATHS:
            csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
            csrf_header = request.headers.get("x-csrf-token", "")
            if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF validation failed"},
                )

        # `SameSite=None` exists so the cookie survives the cross-site hop between the web origin
        # and this API in production (ai.trademetrix.tech -> api.ai.trademetrix.tech). But a
        # `SameSite=None` cookie **must** carry `Secure`, and every browser rejects one that does
        # not — the whole cookie is dropped, silently.
        #
        # So outside production, where `secure` is False, `SameSite=None` was not a permissive
        # choice: it made the cookie invalid. `document.cookie` came back empty, `getCSRFToken()`
        # in `apps/web/lib/api.ts` returned '', `X-CSRF-Token` was never attached, and **every
        # POST, PUT and DELETE answered 403**. Local development, staging and any non-production
        # environment had no working write path at all — only reads, which is why this went
        # unnoticed for so long and why interaction testing looked impossible.
        #
        # `lax` is the correct pairing for a non-Secure cookie: it is accepted by the browser, and
        # for same-site requests — which is what local and single-host deployments are — it is
        # functionally equivalent to `none`.
        #
        # This is the third appearance of this exact defect. AGENTS.md records INC-013 (cookie set
        # only on the first request) and then its relapse (production running older middleware than
        # local). Same root area, different symptom.
        cookie_secure = settings.env == "production"
        cookie_samesite = "none" if cookie_secure else "lax"

        response = await call_next(request)

        token = getattr(request.state, 'csrf_token', None)
        if token:
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=token,
                httponly=False,
                secure=cookie_secure,
                samesite=cookie_samesite,
                path="/",
                domain=settings.cookie_domain or None,
            )
            response.headers["X-CSRF-Token"] = token
        elif not request.cookies.get(CSRF_COOKIE_NAME):
            token = secrets.token_hex(32)
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=token,
                httponly=False,
                secure=cookie_secure,
                samesite=cookie_samesite,
                path="/",
                domain=settings.cookie_domain or None,
            )
            response.headers["X-CSRF-Token"] = token

        return response
