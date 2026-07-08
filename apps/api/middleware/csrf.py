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
    "/api/v1/admin/assignments",
    "/api/v1/admin/broadcast",
    "/api/v1/admin/broadcast/recipients",
    "/api/v1/alerts",
    "/api/v1/brokers/fyers/callback",
    "/api/v1/brokers/dhan/callback",
    "/api/v1/brokers/upstox/callback",
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

        response = await call_next(request)

        if request.url.path in SAFE_PATHS and request.method == "POST":
            token = secrets.token_hex(32)
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=token,
                httponly=False,
                secure=True,
                samesite="lax",
                path="/",
                domain=settings.cookie_domain or None,
            )

        return response
