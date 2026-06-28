from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from core.logging import setup_logging
from routes.v1_health import router as health_router
from routes.v1_auth import router as auth_router
from routes.v1_brokers import router as brokers_router
from routes.v1_risk import router as risk_router
from routes.v1_strategies import router as strategies_router
from routes.v1_engine import router as engine_router
from routes.v1_ai import router as ai_router
from routes.v1_marketdata import router as marketdata_router
from routes.v1_backtest import router as backtest_router
from market.simulator import market_simulator


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await market_simulator.start()
    yield
    await market_simulator.stop()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(brokers_router, prefix="/api/v1")
app.include_router(risk_router, prefix="/api/v1")
app.include_router(strategies_router, prefix="/api/v1")
app.include_router(engine_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")
app.include_router(marketdata_router, prefix="/api/v1")
app.include_router(backtest_router, prefix="/api/v1")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "path": str(request.url)},
    )
