"""Strategy Runtime v1.0 — HTTP surface (+ Auto Trading v1.0 trading modes).

Endpoints (all under /api/v1, auth-gated):
- POST   /runtime/deploy                    — deploy + start a strategy spec
                                           (live requires confirm_live=true)
- POST   /runtime/{strategy_id}/stop|pause|resume|restart|evaluate
- POST   /runtime/emergency                — user-wide emergency stop
- POST   /runtime/emergency/release        — release the emergency stop
- POST   /runtime/{strategy_id}/emergency-stop
- POST   /runtime/pause-all
- POST   /runtime/{strategy_id}/reconcile — trade reconciliation
- GET    /runtime/accounts                 — broker accounts for mode selection
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
    is_paper: bool | None = None
    broker: str = ""
    account: str = ""
    confirm_live: bool = False  # explicit confirmation required for LIVE
    trigger: str = "CANDLE_CLOSE"
    cron_expression: str = ""
    warmup: bool = True
    quantity: int = 75
    max_positions: int = 0
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
    """Deploy + start a strategy. LIVE requires explicit ``confirm_live=true``
    (409 otherwise) and a real broker account (validated before start)."""
    from strategy_runtime.mode import ModeGuardError, assert_orders_allowed, confirm_live, normalize_mode
    from strategy_runtime.models import StrategySpec, StrategyTrigger

    trigger = req.trigger
    try:
        StrategyTrigger(trigger)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown trigger: {trigger}")

    decision = normalize_mode(req.mode, req.is_paper, broker=req.broker, account=req.account)
    if decision.rejected:
        raise HTTPException(status_code=400, detail=decision.reason)
    decision = await confirm_live(decision, current_user.id, confirm_live=req.confirm_live)
    if decision.rejected:
        if decision.code == "LIVE_CONFIRMATION_REQUIRED":
            raise HTTPException(status_code=409, detail=decision.reason)
        raise HTTPException(status_code=400, detail=decision.reason)

    try:
        await assert_orders_allowed(current_user.id)
    except ModeGuardError as e:
        raise HTTPException(status_code=423, detail=getattr(e, "message", str(e)))

    spec = StrategySpec(
        strategy_id=req.strategy_id,
        user_id=current_user.id,
        symbol=req.symbol.upper(),
        exchange=req.exchange,
        interval=req.interval,
        timeframes=req.timeframes or [req.interval],
        mode=decision.mode,
        is_paper=decision.is_paper,
        broker=decision.broker,
        account=decision.account,
        confirmed=decision.confirmed,
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
    if result.get("status") == "refused":
        code = result.get("code", "MODE_GUARD_REJECTED")
        status = 423 if "KILL" in code or "EMERGENCY" in code else 400
        raise HTTPException(status_code=status, detail=result.get("reason", "Refused"))
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


# -- Auto Trading v1.0: emergency stop / kill switch / reconcile --------------
class EmergencyStopRequest(BaseModel):
    reason: str = ""


@router.post("/emergency")
async def emergency_stop(
    req: EmergencyStopRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    """User-wide emergency stop: halt all of this user's strategies."""
    result = await _manager().emergency_stop(current_user.id, reason=req.reason or "User emergency stop")
    return result


@router.post("/emergency/release")
async def release_emergency(
    current_user: UserProfile = Depends(get_current_user),
):
    return await _manager().release_emergency_stop(current_user.id, triggered_by=current_user.id)


@router.post("/{strategy_id}/emergency-stop")
async def strategy_emergency_stop(
    strategy_id: str,
    req: EmergencyStopRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    result = await _manager().emergency_stop(current_user.id, reason=req.reason or "Strategy emergency stop", strategy_id=strategy_id)
    if result.get("status") not in ("emergency_stopped", "emergency_failed"):
        raise HTTPException(status_code=404, detail="Strategy not found")
    return result


@router.post("/pause-all")
async def pause_all(
    current_user: UserProfile = Depends(get_current_user),
    reason: str = "manual",
):
    return await _manager().pause_all(current_user.id, reason=reason)


@router.post("/{strategy_id}/reconcile")
async def reconcile_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    result = await _manager().reconcile(strategy_id, user_id=current_user.id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Strategy not found")
    if result.get("status") == "forbidden":
        raise HTTPException(status_code=403, detail="Not your strategy")
    return result


@router.get("/accounts")
async def list_broker_accounts(
    current_user: UserProfile = Depends(get_current_user),
):
    """Broker accounts available to this user for LIVE mode selection."""
    try:
        from infrastructure.repositories.broker_repository import BrokerRepository

        rows = await BrokerRepository().list_credentials(current_user.id)
    except Exception:
        rows = []
    accounts = [
        {
            "broker": r.get("broker", ""),
            "label": r.get("broker_name") or r.get("broker", ""),
            "is_active": bool(r.get("is_active", True)),
            "token_status": r.get("token_status", "unknown"),
            "token_expires_at": r.get("token_expires_at"),
        }
        for r in rows or []
        if r.get("broker")
    ]
    return {"accounts": accounts}


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
