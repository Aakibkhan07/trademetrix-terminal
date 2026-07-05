import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from core.middleware.timeout import TimeoutMiddleware
from fastapi.responses import JSONResponse

from core.cache import cache
from core.config import settings
from core.exceptions import AppException
from core.logging import record_request_duration, setup_logging
from core.middleware.request_id import RequestIDMiddleware
from core.middleware.request_logging import RequestLoggingMiddleware
from core.middleware.security import SecurityHeadersMiddleware
from core.prometheus import record_metrics
from core.prometheus import router as prometheus_router
from core.ratelimit import RateLimitMiddleware
from core.response import error_response
from core.sentry import init_sentry
from core.vault import init_vault
from market.simulator import market_simulator
from middleware.validation import InputValidationMiddleware
from middleware.csrf import CSRFProtectMiddleware
from routes.v1_ai import router as ai_router
from routes.v1_auth import router as auth_router
from routes.v1_backtest import router as backtest_router
from routes.v1_brokers import router as brokers_router
from routes.v1_engine import router as engine_router
from routes.v1_health import router as health_router
from routes.v1_market import router as market_router
from routes.v1_marketdata import router as marketdata_router
from routes.v1_risk import router as risk_router
from routes.v1_strategies import router as strategies_router
from routes.v1_admin import router as admin_router
from routes.v1_alerts import router as alerts_router
from routes.v1_otp import router as otp_router
from routes.v1_tradingview import router as tradingview_router
from routes.v1_user_strategies import router as user_strategies_router
from routes.v1_builder import router as builder_router
from routes.v1_events import router as events_router
from routes.v1_analytics import router as analytics_router
from routes.v1_feedback import router as feedback_router
from routes.v1_margin_estimate import router as margin_estimate_router
from routes.v1_subscriptions import router as subscriptions_router

logger = logging.getLogger(__name__)

_PROD = os.getenv("ENV", "").lower() == "production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_sentry()
    init_vault()
    await cache.init()
    from engine.user_strategy_runner import user_strategy_runner
    await user_strategy_runner.start()
    yield
    await user_strategy_runner.stop()
    await market_simulator.stop()
    await cache.close()
    from core.db import close_supabase
    await close_supabase()
    from core.http_client import shared_http
    await shared_http.close()
    from oms.manager import order_manager
    await order_manager.stop()
    from runtime.manager import runtime_manager
    await runtime_manager.shutdown()
    from execution.event_bus import _pending_tasks
    for task in list(_pending_tasks):
        task.cancel()
    _pending_tasks.clear()
    logger.info("Graceful shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url=None if _PROD else "/docs",
    redoc_url=None if _PROD else "/redoc",
    openapi_url=None if _PROD else "/openapi.json",
)

# ── Middleware (order matters: outermost first) ──
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=120)
app.add_middleware(InputValidationMiddleware)
app.add_middleware(CSRFProtectMiddleware)
app.add_middleware(TimeoutMiddleware, timeout_seconds=settings.request_timeout_seconds)


@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000
    duration_s = duration_ms / 1000
    record_request_duration(request.url.path, duration_ms)
    record_metrics(request.method, request.url.path, response.status_code, duration_s)
    return response


app.include_router(health_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(brokers_router, prefix="/api/v1")
app.include_router(risk_router, prefix="/api/v1")
app.include_router(strategies_router, prefix="/api/v1")
app.include_router(engine_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")
app.include_router(market_router, prefix="/api/v1")
app.include_router(marketdata_router, prefix="/api/v1")
app.include_router(backtest_router, prefix="/api/v1")
app.include_router(otp_router, prefix="/api/v1")
app.include_router(tradingview_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(builder_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(analytics_router)
app.include_router(feedback_router)
app.include_router(prometheus_router)
app.include_router(user_strategies_router, prefix="/api/v1")
app.include_router(margin_estimate_router, prefix="/api/v1")
app.include_router(subscriptions_router, prefix="/api/v1")


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return error_response(
        message=exc.message,
        code=exc.code,
        status=exc.status,
        details=exc.details,
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return error_response(
        message="Internal server error",
        code="INTERNAL_ERROR",
        status=500,
        details={"path": str(request.url)},
    )
