import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from core.middleware.timeout import TimeoutMiddleware

from core.cache import cache
from core.config import settings
from core.exceptions import AppError
from core.logging import record_request_duration, setup_logging
from core.middleware.request_id import RequestIDMiddleware
from core.middleware.request_logging import RequestLoggingMiddleware
from core.middleware.ip_whitelist import AdminIPWhitelistMiddleware
from core.middleware.security import SecurityHeadersMiddleware
from core.prometheus import on_breaker_state_change as _on_breaker_state_change, record_metrics
from core.prometheus import router as prometheus_router
from core.ratelimit import RateLimitMiddleware
from core.response import error_response
from core.sentry import init_sentry
from core.vault import init_vault
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
from routes.v1_buyer_strategies import router as buyer_strategies_router
from routes.v1_squareoff import router as squareoff_router
from routes.v1_squareoff import service as squareoff_service
from routes.v1_multileg import router as multileg_router
from application.services.cleanup_service import CleanupService
from routes.v1_referrals import router as referrals_router
from routes.v1_broker_webhook import router as broker_webhook_router
from routes.v1_orders import router as orders_router
from routes.v1_portfolio import router as portfolio_router

logger = logging.getLogger(__name__)

_PROD = os.getenv("ENV", "").lower() == "production"


def _prewarm_lazy_routes(app: "FastAPI") -> None:
    """Force FastAPI's lazy included-router caches to expand at import time.

    Newer FastAPI versions defer route expansion until first request. A request
    racing the first expansion of a given router can receive an intermittent
    405 (with `allow` echoing the request method) for perfectly valid routes,
    in the minutes after process start. Expanding every lazy router here —
    serially, single-threaded, before uvicorn binds the port — removes the race.
    """
    try:
        seen = set()

        def expand(route) -> None:
            rid = id(route)
            if rid in seen:
                return
            seen.add(rid)
            for method in ("effective_candidates", "effective_low_priority_routes"):
                fn = getattr(route, method, None)
                if callable(fn):
                    try:
                        for child in fn():
                            if type(child).__name__ == "_IncludedRouter":
                                expand(child)
                    except Exception:
                        pass

        for route in app.routes:
            if type(route).__name__ == "_IncludedRouter":
                expand(route)
        logger.info("Lazy route warm-up complete (%d routers expanded)", len(seen))
    except Exception as e:  # warm-up is best-effort; never block startup
        logger.warning("Lazy route warm-up failed: %s", e)


async def _startup_recovery():
    try:
        await asyncio.sleep(10)
        from execution.recovery import reconcile_pending_orders
        result = await reconcile_pending_orders()
        if result.get("reconciled", 0) > 0:
            logger.info("Startup recovery reconciled %d pending orders", result["reconciled"])
    except Exception as e:
        logger.warning("Startup recovery skipped: %s", e)


async def _start_watchdog():
    from execution.token_watchdog import token_watchdog_loop
    asyncio.ensure_future(token_watchdog_loop())
    logger.info("Token watchdog started")


async def _start_webhook_retry():
    from execution.webhook_retry import retry_webhook_worker
    asyncio.ensure_future(retry_webhook_worker())
    logger.info("Webhook retry worker started")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_sentry()
    init_vault()
    from core.resilience import set_breaker_state_callback
    set_breaker_state_callback(_on_breaker_state_change)
    try:
        from brokers.sdk.observability import wire_default_observability

        wire_default_observability()
        logger.info("Broker SDK observability wired (event bus -> health -> metrics)")
    except Exception as e:
        logger.warning("Broker SDK observability wiring failed (non-fatal): %s", e)
    await cache.init()
    from infrastructure.database import init_db, close_db
    try:
        await init_db()
    except Exception as e:
        logger.warning("Database init failed (will retry on first query): %s", e)
    from market.cache import market_cache
    await market_cache.start_sweeper()
    from market.data_socket import shared_socket
    await shared_socket.start()
    from engine.user_strategy_runner import user_strategy_runner
    from engine.buyer_strategy_runner import buyer_strategy_runner
    await user_strategy_runner.start()
    await buyer_strategy_runner.start()
    from infrastructure.handlers import register_handlers
    from infrastructure.worker import start as start_worker, stop as stop_worker
    register_handlers()
    await start_worker()
    squareoff_service.start_scheduler()
    cleanup_service = CleanupService()
    cleanup_service.start_scheduler()
    from execution.recovery import reconcile_pending_orders
    _background_tasks = []
    _background_tasks.append(asyncio.ensure_future(_startup_recovery()))
    _background_tasks.append(asyncio.ensure_future(_start_watchdog()))
    _background_tasks.append(asyncio.ensure_future(_start_webhook_retry()))
    from market.symbol_master import symbol_master
    await symbol_master.start_auto_sync()
    from oms.manager import order_manager
    await order_manager.start()
    yield
    for task in _background_tasks:
        task.cancel()
    cleanup_service.stop_scheduler()
    squareoff_service.stop_scheduler()
    await stop_worker()
    await buyer_strategy_runner.stop()
    await user_strategy_runner.stop()
    from market.data_socket import shared_socket
    await shared_socket.stop()
    await cache.close()
    from core.db import close_supabase
    await close_supabase()
    await close_db()
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

# ── Middleware (order matters: first added = innermost, last added = outermost) ──
app.add_middleware(GZipMiddleware, minimum_size=1000)

cors_origins = settings.cors_origin_list
if "*" in cors_origins:
    cors_origins = ["*"]
    cors_creds = False
elif not cors_origins:
    cors_origins = ["*"]
    cors_creds = False
else:
    cors_creds = True

app.add_middleware(RequestIDMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=600)
app.add_middleware(InputValidationMiddleware)
app.add_middleware(CSRFProtectMiddleware)
app.add_middleware(TimeoutMiddleware, timeout_seconds=settings.request_timeout_seconds)
app.add_middleware(AdminIPWhitelistMiddleware)

# CORS must be outermost so headers are added even to error responses (e.g. CSRF 403)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000
    duration_s = duration_ms / 1000
    record_request_duration(request.url.path, duration_ms)
    record_metrics(request.method, request.url.path, response.status_code, duration_s)
    if response.status_code >= 500:
        try:
            from application.services.analytics_service import AnalyticsService
            path = request.url.path
            if path not in ("/health", "/health/live", "/health/ready", "/metrics"):
                user_id = getattr(request.state, "user_id", "") or ""
                await AnalyticsService().record_server_event(
                    user_id,
                    "api_error",
                    {"path": path, "status": response.status_code, "method": request.method},
                )
        except Exception:
            pass
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
app.include_router(buyer_strategies_router, prefix="/api/v1")
app.include_router(squareoff_router, prefix="/api/v1")
app.include_router(multileg_router, prefix="/api/v1")
app.include_router(orders_router, prefix="/api/v1")
app.include_router(portfolio_router)
app.include_router(subscriptions_router, prefix="/api/v1")
app.include_router(referrals_router, prefix="/api/v1")
app.include_router(broker_webhook_router, prefix="/api/v1")

_prewarm_lazy_routes(app)


@app.exception_handler(AppError)
async def app_exception_handler(request: Request, exc: AppError):
    return error_response(
        message=exc.message,
        code=exc.code,
        status=exc.status,
        details=exc.details,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    from core.prometheus import exceptions_total
    exceptions_total.labels(type=type(exc).__name__).inc()
    return error_response(
        message="Internal server error",
        code="INTERNAL_ERROR",
        status=500,
        details={"path": str(request.url)},
    )
