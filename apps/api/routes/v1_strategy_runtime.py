"""Strategy Runtime v1.0 — HTTP surface.

Endpoints (all under /api/v1, auth-gated):
- POST   /runtime/deploy                    — deploy + start a strategy spec
- POST   /runtime/{strategy_id}/stop|pause|resume|restart
- POST   /runtime/{strategy_id}/evaluate   — manual dry-run evaluation
- GET    /runtime/{strategy_id}/status
- GET    /runtime/strategies               — per-user running strategies
- GET    /runtime/health                   — runtime + per-strategy health
- POST   /runtime/event                    — inject session/manual events
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.deps import get_current_user
from core.models import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runtime", tags=["strategy-runtime"])


class DeployRuntimeRequest(BaseModel):
    strategy_id: str
    symbol: str = "NIFTY"
    exchange: str = "NSE"
    interval: str = "15m"
    timeframes: list[str] = Field(default_factory=lambda: ["15m"])
    mode: str = "paper"
    is_paper: bool = True
    broker: str = ""
    account: str = ""
    trigger: str = "CANDLE_CLOSE"
    cron_expression: str = ""
    warmup: bool = True
    quantity: int = 75
    max_positions: int = 1
    max_risk_per_trade: float = 0.0
    max_daily_trades: int = 0
    variables: dict[str, Any] = Field(default_factory=dict)


class RuntimeEventRequest(BaseModel):
    kind: str
    strategy_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


def _manager():
    from strategy_runtime.manager import strategy_runtime_manager

    return strategy_runtime_manager


@router.post("/deploy")
async def deploy_strategy(
    req: DeployRuntimeRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    from strategy_runtime.models import StrategySpec, StrategyTrigger

    trigger = req.trigger
    try:
        StrategyTrigger(trigger)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown trigger: {trigger}")

    spec = StrategySpec(
        strategy_id=req.strategy_id,
        user_id=current_user.id,
        symbol=req.symbol.upper(),
        exchange=req.exchange,
        interval=req.interval,
        timeframes=req.timeframes or [req.interval],
        mode=req.mode,
        is_paper=req.is_paper,
        broker=req.broker,
        account=req.account,
        trigger=trigger,
        cron_expression=req.cron_expression,
        warmup=req.warmup,
        quantity=req.quantity,
        max_positions=req.max_positions,
        max_risk_per_trade=req.max_risk_per_trade,
        max_daily_trades=req.max_daily_trades,
        variables=req.variables,
    )
    result = await _manager().start_strategy(spec)
    return {"strategy_id": req.strategy_id, **result}


@router.post("/{strategy_id}/stop")
async def stop_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    result = await _manager().stop_strategy(strategy_id, user_id=current_user.id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Strategy not found")
    if result.get("status") == "forbidden":
        raise HTTPException(status_code=403, detail="Not your strategy")
    return result


@router.post("/{strategy_id}/pause")
async def pause_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
    reason: str = "manual",
):
    result = await _manager().pause_strategy(strategy_id, user_id=current_user.id, reason=reason)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Strategy not found")
    if result.get("status") == "forbidden":
        raise HTTPException(status_code=403, detail="Not your strategy")
    return result


@router.post("/{strategy_id}/resume")
async def resume_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    result = await _manager().resume_strategy(strategy_id, user_id=current_user.id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Strategy not found")
    if result.get("status") == "forbidden":
        raise HTTPException(status_code=403, detail="Not your strategy")
    return result


@router.post("/{strategy_id}/restart")
async def restart_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    result = await _manager().restart_strategy(strategy_id, user_id=current_user.id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Strategy not found")
    if result.get("status") == "forbidden":
        raise HTTPException(status_code=403, detail="Not your strategy")
    return result


@router.post("/{strategy_id}/evaluate")
async def evaluate_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    """Manual dry-run evaluation (no order execution)."""
    result = await _manager().manual_evaluate(strategy_id, user_id=current_user.id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Strategy not found")
    return result


@router.get("/{strategy_id}/status")
async def strategy_status(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    status = await _manager().get_status(strategy_id, user_id=current_user.id)
    if status is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return status


@router.get("/strategies")
async def list_strategies(
    current_user: UserProfile = Depends(get_current_user),
):
    return {"strategies": await _manager().list_strategies(user_id=current_user.id)}


@router.get("/health")
async def runtime_health(
    current_user: UserProfile = Depends(get_current_user),
):
    health = await _manager().health()
    health["user_id"] = current_user.id
    return health


@router.post("/event")
async def emit_runtime_event(
    req: RuntimeEventRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    """Inject a runtime event (session_open / session_close / manual) — admin/ops."""
    from core.deps import require_admin

    await require_admin(current_user)
    await _manager().emit_event(req.kind, payload=req.payload)
    return {"routed": req.kind, "strategy_id": req.strategy_id}
