import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from builder.blocks import list_blocks, list_categories, get_block
from builder.compiler import compile_dsl
from builder.io import from_json, to_dsl_text, validate_import
from builder.logs import get_logs, record
from builder.manager import builder_manager
from builder.models import (
    DeploymentConfig,
    GraphEdge,
    GraphNode,
    StrategySettings,
    StrategyStatus,
)
from builder.score import score_strategy
from core.deps import get_current_user, require_feature
from core.models import UserProfile
from engine.graph_strategy_runner import (
    get_runtime_dashboard,
    start_graph_strategy,
    stop_graph_strategy,
)
from engine.user_strategy_backtest import run_user_strategy_backtest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/builder", tags=["builder"])


class CreateStrategyRequest(BaseModel):
    name: str = ""
    description: str = ""
    template: str = ""


class UpdateStrategyRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    nodes: list[dict] | None = None
    edges: list[dict] | None = None
    settings: dict | None = None
    tags: list[str] | None = None


@router.get("/blocks")
async def list_builder_blocks(category: str | None = None):
    blocks = list_blocks()
    result = []
    for b in blocks:
        result.append({
            "type": b.type,
            "name": b.name,
            "category": b.category.value,
            "description": b.description,
            "inputs": [{"name": i.name, "type": i.type.value, "label": i.label, "required": i.required} for i in b.inputs],
            "outputs": [{"name": o.name, "type": o.type.value, "label": o.label} for o in b.outputs],
            "params": [{"name": p.name, "type": p.type, "label": p.label, "default": p.default, "options": p.options} for p in b.params],
        })
    return {"blocks": result, "total": len(result)}


@router.get("/blocks/categories")
async def list_builder_categories():
    return {"categories": list_categories()}


@router.get("/blocks/{block_type}")
async def get_builder_block(block_type: str):
    block = get_block(block_type)
    if not block:
        raise HTTPException(status_code=404, detail=f"Block type not found: {block_type}")
    return block


# ─── CRUD ───

@router.post("/strategies")
async def create_strategy(
    req: CreateStrategyRequest,
    current_user: UserProfile = Depends(require_feature("builder")),
):
    dsl = await builder_manager.create(
        name=req.name,
        description=req.description,
        author=current_user.id,
        template=req.template,
    )
    try:
        from application.services.analytics_service import AnalyticsService
        await AnalyticsService().record_server_event(
            current_user.id, "strategy.created",
            {"strategy_id": dsl.id, "template": req.template or "", "name": req.name or ""},
        )
    except Exception:
        pass
    return dsl.model_dump(mode="json", exclude_none=True)


@router.get("/strategies")
async def list_strategies(
    status: str | None = None,
    current_user: UserProfile = Depends(get_current_user),
):
    strategies = await builder_manager.list(status=status)
    return {"strategies": strategies, "total": len(strategies)}


@router.get("/strategies/{strategy_id}")
async def get_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    dsl = await builder_manager.get(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return dsl.model_dump(mode="json", exclude_none=True)


@router.put("/strategies/{strategy_id}")
async def update_strategy(
    strategy_id: str,
    req: UpdateStrategyRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    updates = {}
    if req.name is not None:
        updates["name"] = req.name
    if req.description is not None:
        updates["description"] = req.description
    if req.nodes is not None:
        updates["nodes"] = [GraphNode(**n) for n in req.nodes]
    if req.edges is not None:
        updates["edges"] = [GraphEdge(**e) for e in req.edges]
    if req.settings is not None:
        updates["settings"] = StrategySettings(**req.settings)
    if req.tags is not None:
        updates["tags"] = req.tags

    dsl = await builder_manager.update(strategy_id, updates)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return dsl.model_dump(mode="json", exclude_none=True)


@router.delete("/strategies/{strategy_id}")
async def delete_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    success = await builder_manager.delete(strategy_id)
    if not success:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"status": "deleted"}


# ─── Compile ───

@router.post("/strategies/{strategy_id}/compile")
async def compile_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    dsl = await builder_manager.get(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")

    graph, validation = compile_dsl(dsl)
    if not graph:
        raise HTTPException(
            status_code=400,
            detail={"error": "Compilation failed", "issues": [i.model_dump() for i in validation.issues]},
        )

    return {
        "strategy_id": strategy_id,
        "compiled": True,
        "node_count": len(graph.nodes),
        "total_estimated_latency_us": graph.total_estimated_latency_us,
        "max_depth": graph.max_depth,
        "execution_order": [
            {"order": n.order, "block_type": n.block_type, "id": n.id, "latency_us": n.estimated_latency_us}
            for n in graph.nodes
        ],
        "validation": {
            "valid": validation.valid,
            "issues": [i.model_dump() for i in validation.issues],
        },
    }


# ─── Validate ───

@router.post("/strategies/{strategy_id}/validate")
async def validate_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    dsl = await builder_manager.get(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")

    _, validation = compile_dsl(dsl)
    await record(strategy_id, "validation",
                 f"Validation: {'passed' if validation.valid else 'failed'} ({len(validation.issues)} issue(s))",
                 level="info" if validation.valid else "warning",
                 user_id=current_user.id,
                 detail={"valid": validation.valid, "issues": [i.model_dump() for i in validation.issues]})
    if validation.valid and dsl.status in (StrategyStatus.DRAFT, StrategyStatus.PUBLISHED):
        await builder_manager.set_status(strategy_id, StrategyStatus.VALIDATED)
    return {
        "strategy_id": strategy_id,
        "valid": validation.valid,
        "issues": [i.model_dump() for i in validation.issues],
        "cycles": validation.cycles,
    }


@router.post("/strategies/{strategy_id}/ready")
async def mark_strategy_ready(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    dsl = await builder_manager.get(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if dsl.status not in (StrategyStatus.VALIDATED, StrategyStatus.DRAFT, StrategyStatus.PUBLISHED):
        raise HTTPException(status_code=400, detail=f"Cannot mark {dsl.status} strategy as ready")

    _, validation = compile_dsl(dsl)
    if not validation.valid:
        raise HTTPException(status_code=400, detail="Strategy must pass validation before it can be marked ready")

    dsl = await builder_manager.set_status(strategy_id, StrategyStatus.READY)
    await record(strategy_id, "lifecycle", "Strategy marked READY", level="info", user_id=current_user.id)
    return {"status": "ready", "strategy_id": strategy_id}


# ─── Preview ───

@router.get("/strategies/{strategy_id}/preview")
async def preview_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    preview = await builder_manager.preview(strategy_id)
    if "error" in preview:
        raise HTTPException(status_code=404, detail=preview["error"])
    return preview


# ─── Versioning ───

@router.post("/strategies/{strategy_id}/publish")
async def publish_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    dsl = await builder_manager.publish(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")
    await record(strategy_id, "lifecycle", "Strategy published (legacy flow)", level="info", user_id=current_user.id)
    return {"status": "published", "strategy_id": strategy_id}


class BacktestStrategyRequest(BaseModel):
    from_date: str = ""
    to_date: str = ""


class StartGraphStrategyRequest(BaseModel):
    symbol: str = "NIFTY"
    interval: str = "15m"
    mode: str = "paper"


class RiskDeployRequest(BaseModel):
    max_position_size: float = 0.0
    max_daily_loss: float = 0.0
    risk_per_trade: float = 1.0
    stop_loss_pct: float = 0.0
    target_pct: float = 0.0


class ScheduleDeployRequest(BaseModel):
    trading_days: list[str] = []
    start_time: str = "09:15"
    end_time: str = "15:30"
    timezone: str = "Asia/Kolkata"


class DeployStrategyRequest(BaseModel):
    symbol: str = "NIFTY"
    interval: str = "15m"
    mode: str = "paper"  # paper | live
    broker: str = ""
    account: str = ""
    confirm_live: bool = False  # explicit LIVE confirmation (Auto Trading v1.0)
    capital: float = 0.0
    risk: RiskDeployRequest = Field(default_factory=RiskDeployRequest)
    schedule: ScheduleDeployRequest = Field(default_factory=ScheduleDeployRequest)


def _build_runtime_spec(
    strategy_id: str,
    user_id: str,
    symbol: str,
    interval: str,
    mode: str,
    broker: str,
    capital: float,
    risk: dict,
    schedule: dict,
    account: str = "",
    confirmed: bool = False,
) -> "StrategySpec":
    """Materialize a Strategy Runtime spec from the legacy builder deploy payload.

    Execution now owns the strategy (runtime worker on the frozen engine path);
    the legacy ``graph_strategy_runner`` stays as the pre-runtime fallback.
    """
    from strategy_runtime.models import StrategySpec

    return StrategySpec(
        strategy_id=strategy_id,
        user_id=user_id,
        symbol=symbol.upper(),
        exchange="NSE",
        interval=interval or "15m",
        timeframes=[interval or "15m"],
        mode="live" if mode == "live" else "paper",
        is_paper=mode != "live",
        broker=broker,
        account=account,
        confirmed=confirmed,
        trigger="MARKET_OPEN" if (schedule and schedule.get("start_time")) else "CANDLE_CLOSE",
        warmup=True,
        quantity=int(risk.get("max_position_size") or 0) if (risk and risk.get("max_position_size")) else 0,
        max_positions=1,
        max_risk_per_trade=float((risk or {}).get("risk_per_trade") or 0.0),
        max_daily_trades=0,
        variables={"capital": capital, "schedule": schedule or {}},
    )


@router.post("/strategies/{strategy_id}/deploy")
async def deploy_builder_strategy(
    strategy_id: str,
    req: DeployStrategyRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    dsl = await builder_manager.get(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if dsl.status not in (StrategyStatus.READY, StrategyStatus.PUBLISHED, StrategyStatus.VALIDATED, StrategyStatus.DRAFT):
        raise HTTPException(status_code=400, detail=f"Strategy is {dsl.status}; validate and mark ready before deploying")

    _, validation = compile_dsl(dsl)
    if not validation.valid:
        raise HTTPException(status_code=400, detail={"error": "Cannot deploy an invalid strategy", "issues": [i.model_dump() for i in validation.issues]})

    if req.mode == "live" and not req.broker:
        raise HTTPException(status_code=400, detail="Live deployment requires a broker")
    if req.mode == "live" and not req.confirm_live:
        raise HTTPException(status_code=409, detail="Live deployment requires explicit confirmation (confirm_live=true)")

    deployment = DeploymentConfig(
        mode=req.mode,
        broker=req.broker or "paper",
        capital=req.capital,
        risk=req.risk.model_dump(),
        schedule=req.schedule.model_dump(exclude_none=True),
    )
    await builder_manager.update(strategy_id, {"deployment": deployment.model_dump()})
    await builder_manager.set_status(strategy_id, StrategyStatus.LIVE if req.mode == "live" else StrategyStatus.PAPER)
    await record(strategy_id, "lifecycle",
                 f"Deployed to {'LIVE' if req.mode == 'live' else 'PAPER'} (broker={req.broker or 'paper'}, capital={req.capital})",
                 level="warning" if req.mode == "live" else "info", user_id=current_user.id)

    spec = _build_runtime_spec(
        strategy_id=strategy_id,
        user_id=current_user.id,
        symbol=req.symbol,
        interval=req.interval,
        mode=req.mode,
        broker=req.broker,
        account=req.account,
        capital=req.capital,
        risk=req.risk.model_dump(),
        schedule=req.schedule.model_dump(exclude_none=True),
        confirmed=req.confirm_live,
    )
    result = await _runtime_start(spec)
    if result.get("status") == "refused":
        raise HTTPException(status_code=423 if "KILL" in result.get("code", "") or "EMERGENCY" in result.get("code", "") else 400, detail=result.get("reason"))
    return {"status": result["status"], "mode": req.mode, "broker": req.broker or "paper", "strategy_id": strategy_id}


async def _runtime_start(spec: "StrategySpec") -> dict:
    """Start through the Strategy Runtime; legacy runner is the fallback.

    Safety: an unconfirmed LIVE spec is NEVER routed to the legacy runner
    (it does not implement the explicit confirmation gate). No fallback.
    """
    from strategy_runtime.manager import strategy_runtime_manager
    from strategy_runtime.mode import ModeGuardError, assert_orders_allowed

    try:
        await assert_orders_allowed(spec.user_id)
    except ModeGuardError as e:
        return {"status": "refused", "strategy_id": spec.strategy_id,
                "reason": getattr(e, "message", str(e)), "code": e.code}
    if (spec.mode or "") == "live" and not spec.confirmed:
        return {"status": "refused", "strategy_id": spec.strategy_id,
                "reason": "Live deployment requires explicit confirmation", "code": "LIVE_CONFIRMATION_REQUIRED"}
    try:
        if strategy_runtime_manager._initialized:
            return await strategy_runtime_manager.start_strategy(spec)
    except Exception as e:
        logger.warning("Strategy Runtime start failed for %s (legacy fallback): %s", spec.strategy_id, e)
    return {"status": await start_graph_strategy(
        strategy_id=spec.strategy_id,
        user_id=spec.user_id,
        symbol=spec.symbol,
        interval=spec.interval,
        is_paper=spec.is_paper,
    )}


async def _runtime_stop(strategy_id: str, user_id: str) -> str:
    """Stop through the Strategy runtime; legacy fallback."""
    from strategy_runtime.manager import strategy_runtime_manager

    try:
        if strategy_runtime_manager._initialized:
            outcome = await strategy_runtime_manager.stop_strategy(strategy_id, user_id=user_id)
            if outcome.get("status") in ("stopped", "not_found"):
                return outcome["status"]
    except Exception as e:
        logger.warning("runtime stop failed (%s, legacy fallback): %s", strategy_id, e)
    await stop_graph_strategy(strategy_id, user_id=user_id)
    return "stopped"


@router.post("/strategies/{strategy_id}/start")
async def start_builder_strategy(
    strategy_id: str,
    req: StartGraphStrategyRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    dsl = await builder_manager.get(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if dsl.status not in (StrategyStatus.PUBLISHED, StrategyStatus.READY, StrategyStatus.PAPER, StrategyStatus.LIVE, StrategyStatus.STOPPED, StrategyStatus.VALIDATED):
        raise HTTPException(status_code=400, detail="Strategy must be validated and marked ready before starting")

    deployment = {}
    if isinstance(getattr(dsl, "deployment", None), DeploymentConfig):
        deployment = dsl.deployment.model_dump()
    # persist trading mode: an explicit live start, or the previously
    # deployed mode when the request did not ask for paper explicitly.
    effective_mode = "live" if (req.mode == "live" or (req.mode == "paper" and deployment.get("mode") == "live")) else "paper"
    spec = _build_runtime_spec(
        strategy_id=strategy_id,
        user_id=current_user.id,
        symbol=req.symbol,
        interval=req.interval,
        mode=effective_mode,
        broker=deployment.get("broker", ("" if effective_mode != "live" else "fyers")),
        account=deployment.get("account", ""),
        capital=float(deployment.get("capital") or 0.0),
        risk=deployment.get("risk") or {},
        schedule=deployment.get("schedule") or {},
        confirmed=deployment.get("mode") == "live",
    )
    result = await _runtime_start(spec)
    if result.get("status") == "refused":
        raise HTTPException(status_code=409, detail=result.get("reason", "Live deployment requires explicit confirmation"))
    await builder_manager.set_status(strategy_id, StrategyStatus.LIVE if effective_mode == "live" else StrategyStatus.PAPER)
    return {"status": result["status"], "strategy_id": strategy_id}


@router.post("/strategies/{strategy_id}/stop")
async def stop_builder_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    await builder_manager.set_status(strategy_id, StrategyStatus.STOPPED)
    outcome = await _runtime_stop(strategy_id, current_user.id)
    return {"status": outcome, "strategy_id": strategy_id}


@router.post("/strategies/{strategy_id}/archive")
async def archive_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    dsl = await builder_manager.archive(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")
    await record(strategy_id, "lifecycle", "Strategy archived", level="info", user_id=current_user.id)
    return {"status": "archived", "strategy_id": strategy_id}


@router.post("/strategies/{strategy_id}/clone")
async def clone_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    dsl = await builder_manager.clone(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")
    await record(dsl.id, "lifecycle", f"Cloned from {strategy_id}", level="info", user_id=current_user.id)
    return dsl.model_dump(mode="json", exclude_none=True)


@router.post("/strategies/{strategy_id}/rollback/{version}")
async def rollback_strategy(
    strategy_id: str,
    version: int,
    current_user: UserProfile = Depends(get_current_user),
):
    dsl = await builder_manager.rollback(strategy_id, version)
    if not dsl:
        raise HTTPException(status_code=404, detail="Version not found")
    await record(strategy_id, "lifecycle", f"Restored to version v{version}", level="info", user_id=current_user.id)
    return dsl.model_dump(mode="json", exclude_none=True)


@router.get("/strategies/{strategy_id}/score")
async def get_strategy_score(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    dsl = await builder_manager.get(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"strategy_id": strategy_id, "score": score_strategy(dsl).model_dump()}


@router.get("/strategies/{strategy_id}/logs")
async def get_strategy_logs(
    strategy_id: str,
    limit: int = Query(200, le=500),
    current_user: UserProfile = Depends(get_current_user),
):
    logs = await get_logs(strategy_id, limit=limit)
    return {"strategy_id": strategy_id, "logs": logs, "total": len(logs)}


@router.get("/strategies/{strategy_id}/compare")
async def compare_strategy_versions(
    strategy_id: str,
    from_version: int = Query(1),
    to_version: int = Query(2),
    current_user: UserProfile = Depends(get_current_user),
):
    result = await builder_manager.compare(strategy_id, from_version, to_version)
    if not result:
        raise HTTPException(status_code=404, detail="Version not found")
    return result


@router.get("/dashboard")
async def builder_dashboard(
    current_user: UserProfile = Depends(get_current_user),
):
    running = await get_runtime_dashboard(user_id=current_user.id)
    return {"running": running, "total_running": sum(1 for r in running if r.get("status") == "running")}


@router.get("/strategies/{strategy_id}/versions")
async def get_strategy_versions(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    versions = await builder_manager.get_versions(strategy_id)
    return {"versions": versions}


# ─── Templates ───

@router.get("/templates")
async def list_templates():
    templates = await builder_manager.list_templates()
    return {"templates": templates, "total": len(templates)}


@router.get("/templates/{template_key}")
async def get_template(template_key: str):
    dsl = await builder_manager.get_template(template_key)
    if not dsl:
        raise HTTPException(status_code=404, detail="Template not found")
    return dsl.model_dump(mode="json", exclude_none=True)


# ─── Import / Export ───

@router.post("/import")
async def import_strategy(
    data: dict,
    current_user: UserProfile = Depends(get_current_user),
):
    valid, errors = validate_import(data)
    if not valid:
        raise HTTPException(status_code=400, detail={"error": "Invalid import data", "details": errors})
    try:
        dsl = from_json(data)
        existing = await builder_manager.get(dsl.id)
        if existing:
            dsl.id = __import__("uuid").uuid4().hex[:12]
        else:
            base = await builder_manager.create(name=dsl.name, author=current_user.email)
            dsl.id = base.id
        await builder_manager.update(dsl.id, dsl.model_dump())
        return dsl.model_dump(mode="json", exclude_none=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Import failed: {str(e)}")


@router.get("/strategies/{strategy_id}/export")
async def export_strategy(
    strategy_id: str,
    format: str = "json",
    current_user: UserProfile = Depends(get_current_user),
):
    dsl = await builder_manager.get(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")

    if format == "dsl":
        return {"format": "dsl", "content": to_dsl_text(dsl)}
    return dsl.model_dump(mode="json", exclude_none=True)
