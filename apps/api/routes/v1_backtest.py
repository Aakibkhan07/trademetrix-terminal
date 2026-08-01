import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backtest.manager import backtest_manager
from backtest.models import BacktestConfig, ReplaySpeed
from backtest.optimizer import OptimizationSpec, backtest_optimizer
from core.deps import get_current_user, require_feature
from core.models import UserProfile
from engine.backtest import BacktestEngine, fetch_historical_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtests", tags=["backtests"])


class BacktestRequest(BaseModel):
    strategy_type: str
    symbol: str = "NIFTY"
    exchange: str = "NSE"
    interval: str = "15m"
    days: int = 60
    initial_capital: float = 100000
    config: dict = {}
    slippage_pct: float = 0.05
    brokerage_pct: float = 0.03
    stt_pct: float = 0.025
    exchange_pct: float = 0.003


# ─── Static routes (must precede /{run_id}) ───


@router.get("/strategies")
async def list_backtest_strategies():
    from strategies import list_strategies
    return {"strategies": list_strategies()}


@router.post("/run")
async def run_backtest_legacy(
    req: BacktestRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    try:
        candles = await fetch_historical_data(
            symbol=req.symbol,
            exchange=req.exchange,
            interval=req.interval,
            days=req.days,
            user_id=current_user.id,
        )

        engine = BacktestEngine(
            strategy_type=req.strategy_type,
            config=req.config,
            initial_capital=req.initial_capital,
            slippage_pct=req.slippage_pct,
            brokerage_pct=req.brokerage_pct,
            stt_pct=req.stt_pct,
            exchange_pct=req.exchange_pct,
        )

        result = await engine.run(candles)
        return {
            "symbol": req.symbol,
            "strategy": req.strategy_type,
            "interval": req.interval,
            "days": req.days,
            "initial_capital": req.initial_capital,
            "candles_analyzed": len(candles),
            "slippage_pct": req.slippage_pct,
            "brokerage_pct": req.brokerage_pct,
            "stt_pct": req.stt_pct,
            "exchange_pct": req.exchange_pct,
            "results": result.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Backtest failed")
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")


# ─── V2 Backtest Engine ───


class BacktestV2Request(BaseModel):
    strategy_type: str
    symbol: str = "NIFTY"
    exchange: str = "NSE"
    interval: str = "15m"
    days: int = 60
    initial_capital: float = 100000.0
    strategy_params: dict = {}
    speed: str = "MAX"
    data_source: str = "auto"
    file_path: str = ""
    risk_enabled: bool = True
    close_positions_on_end: bool = True


@router.post("/run-v2")
async def run_backtest_v2(
    req: BacktestV2Request,
    current_user: UserProfile = Depends(get_current_user),
):
    try:
        speed = ReplaySpeed(req.speed.upper()) if req.speed.upper() in {s.value for s in ReplaySpeed} else ReplaySpeed.MAX

        config = BacktestConfig(
            strategy_type=req.strategy_type,
            strategy_params=req.strategy_params,
            symbol=req.symbol,
            exchange=req.exchange,
            interval=req.interval,
            days=req.days,
            initial_capital=req.initial_capital,
            speed=speed,
            data_source=req.data_source,
            file_path=req.file_path,
            risk_enabled=req.risk_enabled,
            close_positions_on_end=req.close_positions_on_end,
        )

        result = await backtest_manager.run(config)

        return {
            "run_id": result.run_id,
            "status": result.status.value,
            "config": {
                "strategy_type": result.config.strategy_type,
                "symbol": result.config.symbol,
                "interval": result.config.interval,
                "days": result.config.days,
                "initial_capital": result.config.initial_capital,
            },
            "summary": {
                "total_trades": result.total_trades,
                "winning_trades": result.winning_trades,
                "losing_trades": result.losing_trades,
                "win_rate": result.win_rate,
                "net_pnl": result.net_pnl,
                "profit_factor": result.profit_factor,
                "max_drawdown_pct": result.max_drawdown_pct,
                "sharpe_ratio": result.sharpe_ratio,
                "sortino_ratio": result.sortino_ratio,
                "calmar_ratio": result.calmar_ratio,
                "return_pct": result.return_pct,
                "candles_analyzed": result.candles_analyzed,
                "start_equity": result.start_equity,
                "end_equity": result.end_equity,
            },
            "trades": [
                {
                    "symbol": t.symbol,
                    "side": t.side,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "quantity": t.quantity,
                    "pnl": t.pnl,
                    "entry_time": t.entry_time,
                    "exit_time": t.exit_time,
                }
                for t in result.trades
            ],
            "equity_curve": [
                {
                    "timestamp": e.timestamp,
                    "equity": e.equity,
                    "drawdown": e.drawdown,
                    "drawdown_pct": e.drawdown_pct,
                }
                for e in result.equity_curve
            ],
            "monthly_returns": result.monthly_returns,
            "duration_seconds": result.duration_seconds,
            "error": result.error,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Backtest V2 failed")
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")


@router.get("/v2/status")
async def backtest_v2_status():
    return backtest_manager.get_status()


@router.post("/v2/pause")
async def backtest_v2_pause():
    success = await backtest_manager.pause()
    if not success:
        raise HTTPException(status_code=400, detail="No running backtest to pause")
    return {"status": "paused"}


@router.post("/v2/resume")
async def backtest_v2_resume():
    success = await backtest_manager.resume()
    if not success:
        raise HTTPException(status_code=400, detail="No paused backtest to resume")
    return {"status": "resumed"}


@router.post("/v2/stop")
async def backtest_v2_stop():
    success = await backtest_manager.stop()
    if not success:
        raise HTTPException(status_code=400, detail="No running backtest to stop")
    return {"status": "stopped"}


@router.post("/optimize")
async def optimize_strategy(
    req: OptimizationSpec,
    current_user: UserProfile = Depends(get_current_user),
):
    """Parameter optimization (grid / walk_forward / monte_carlo / sensitivity)."""
    try:
        result = await backtest_optimizer.run(req)
        if result.status == "FAILED":
            raise HTTPException(status_code=400, detail=result.error or "Optimization failed")
        return result.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Optimization route failed")
        raise HTTPException(status_code=500, detail=f"Optimization failed: {str(e)}")


@router.get("/optimize/{run_id}")
async def optimize_status(
    run_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    result = backtest_optimizer.get(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Optimization run not found")
    return result.model_dump()


# ─── New CRUD routes (auth-protected) ───


@router.get("/")
async def list_backtests(
    strategy_id: str | None = None,
    current_user: UserProfile = Depends(get_current_user),
):
    return {"backtests": backtest_manager.list_runs(strategy_id=strategy_id)}


@router.post("/", status_code=201)
async def create_backtest(
    req: BacktestRequest,
    current_user: UserProfile = Depends(require_feature("backtest")),
):
    try:
        candles = await fetch_historical_data(
            symbol=req.symbol,
            exchange=req.exchange,
            interval=req.interval,
            days=req.days,
            user_id=current_user.id,
        )

        engine = BacktestEngine(
            strategy_type=req.strategy_type,
            config=req.config,
            initial_capital=req.initial_capital,
            slippage_pct=req.slippage_pct,
            brokerage_pct=req.brokerage_pct,
            stt_pct=req.stt_pct,
            exchange_pct=req.exchange_pct,
        )

        result = await engine.run(candles)
        return {
            "symbol": req.symbol,
            "strategy": req.strategy_type,
            "interval": req.interval,
            "days": req.days,
            "initial_capital": req.initial_capital,
            "candles_analyzed": len(candles),
            "slippage_pct": req.slippage_pct,
            "brokerage_pct": req.brokerage_pct,
            "stt_pct": req.stt_pct,
            "exchange_pct": req.exchange_pct,
            "results": result.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Backtest failed")
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")


@router.get("/candles/{symbol}/{interval}")
async def get_backtest_candles(
    symbol: str,
    interval: str,
    days: int = 60,
    start: str = "",
    end: str = "",
    force_refresh: bool = False,
    current_user: UserProfile = Depends(get_current_user),
):
    from backtest.historical import backtest_historical

    candles = await backtest_historical.load(
        symbol=symbol,
        exchange="NSE",
        interval=interval,
        days=days,
        start=start,
        end=end,
        user_id=current_user.id,
        force_refresh=force_refresh,
    )
    return {"symbol": symbol, "interval": interval, "candles": candles}


@router.get("/corporate-actions")
async def list_corporate_actions(
    symbol: str = "",
    current_user: UserProfile = Depends(get_current_user),
):
    from core.db import async_supabase, get_supabase

    try:
        supabase = get_supabase()
        query = supabase.table("corporate_actions").select("*")
        if symbol:
            query = query.eq("symbol", symbol.upper())
        result = await async_supabase(lambda: query.order("ex_date", desc=True).limit(500).execute())
        return {"actions": result.data or []}
    except Exception as e:
        logger.warning("Corporate actions read failed: %s", e)
        return {"actions": []}


@router.get("/{run_id}")
async def get_backtest(
    run_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    run = await backtest_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest run not found")
    return run


# ─── Phase 5: run-v3, compare, exports, deploy-to-paper, data endpoints ───


class BacktestV3Request(BaseModel):
    strategy_id: str
    symbol: str = "NIFTY"
    exchange: str = "NSE"
    interval: str = "15m"
    days: int = 60
    initial_capital: float = 100000.0
    speed: str = "MAX"
    risk_enabled: bool = True
    close_positions_on_end: bool = True
    slippage_pct: float = 0.0
    latency_candles: int = 0
    partial_fill_probability: float = 0.0
    seed: int | None = None
    cost: dict = {}


def _result_payload(result) -> dict:
    return {
        "run_id": result.run_id,
        "status": result.status.value,
        "strategy_id": result.config.strategy_id if result.config else "",
        "config": {
            "strategy_type": result.config.strategy_type if result.config else "",
            "symbol": result.config.symbol if result.config else "",
            "interval": result.config.interval if result.config else "",
            "days": result.config.days if result.config else 0,
            "initial_capital": result.config.initial_capital if result.config else 0,
        },
        "summary": {
            "total_trades": result.total_trades,
            "winning_trades": result.winning_trades,
            "losing_trades": result.losing_trades,
            "win_rate": result.win_rate,
            "net_pnl": result.net_pnl,
            "profit_factor": result.profit_factor,
            "max_drawdown_pct": result.max_drawdown_pct,
            "sharpe_ratio": result.sharpe_ratio,
            "sortino_ratio": result.sortino_ratio,
            "calmar_ratio": result.calmar_ratio,
            "return_pct": result.return_pct,
            "expectancy": result.expectancy,
            "expectancy_per_r": result.expectancy_per_r,
            "avg_risk_reward_ratio": result.avg_risk_reward_ratio,
            "median_risk_reward_ratio": result.median_risk_reward_ratio,
            "alpha": result.alpha,
            "beta": result.beta,
            "benchmark_return_pct": result.benchmark_return_pct,
            "excess_return_pct": result.excess_return_pct,
            "candles_analyzed": result.candles_analyzed,
            "start_equity": result.start_equity,
            "end_equity": result.end_equity,
        },
        "trades": [t.model_dump(mode="json") for t in result.trades],
        "equity_curve": [
            e.model_dump(mode="json") if hasattr(e, "model_dump") else e
            for e in result.equity_curve
        ],
        "weekday_distribution": result.weekday_distribution,
        "hour_distribution": result.hour_distribution,
        "month_distribution": result.month_distribution,
        "monthly_returns": result.monthly_returns,
        "duration_seconds": result.duration_seconds,
        "error": result.error,
    }


@router.post("/run-v3")
async def run_backtest_v3(
    req: BacktestV3Request,
    current_user: UserProfile = Depends(get_current_user),
):
    """Run a backtest for a builder (DSL) strategy by strategy_id."""
    from builder.manager import builder_manager
    from builder.compiler import compile_dsl

    try:
        from application.services.analytics_service import AnalyticsService
        await AnalyticsService().record_server_event(
            current_user.id, "backtest.run",
            {"strategy_id": req.strategy_id, "symbol": req.symbol, "interval": req.interval, "days": req.days},
        )
    except Exception:
        pass

    try:
        dsl = await builder_manager.get(req.strategy_id)
        if not dsl:
            raise HTTPException(status_code=404, detail="Strategy not found")

        graph, validation = compile_dsl(dsl)
        if not graph or not validation.valid:
            raise HTTPException(
                status_code=400,
                detail="Strategy is invalid: "
                + "; ".join(i.message for i in validation.issues if i.severity == "error"),
            )

        speed = ReplaySpeed(req.speed.upper()) if req.speed.upper() in {s.value for s in ReplaySpeed} else ReplaySpeed.MAX

        config = BacktestConfig(
            strategy_type="graph_strategy",
            strategy_params={"_dsl": dsl.model_dump(mode="json")},
            strategy_id=req.strategy_id,
            user_id=current_user.id,
            symbol=req.symbol,
            exchange=req.exchange,
            interval=req.interval,
            days=req.days,
            initial_capital=req.initial_capital,
            speed=speed,
            risk_enabled=req.risk_enabled,
            close_positions_on_end=req.close_positions_on_end,
            slippage_pct=req.slippage_pct,
            latency_candles=req.latency_candles,
            partial_fill_probability=req.partial_fill_probability,
            seed=req.seed,
            cost=req.cost,
        )
        result = await backtest_manager.run(config)
        return _result_payload(result)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Backtest V3 failed")
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")


@router.post("/compare")
async def compare_backtests(
    req: dict,
    current_user: UserProfile = Depends(get_current_user),
):
    run_ids = req.get("run_ids") or []
    if not isinstance(run_ids, list) or not run_ids:
        raise HTTPException(status_code=400, detail="run_ids is required")
    if len(run_ids) > 10:
        raise HTTPException(status_code=400, detail="Compare at most 10 runs")

    comparison = {}
    for run_id in run_ids:
        run = await backtest_manager.get_run(str(run_id))
        if not run:
            continue
        comparison[str(run_id)] = {
            "strategy_type": run.config.strategy_type if run.config else "",
            "symbol": run.config.symbol if run.config else "",
            "total_trades": run.total_trades,
            "net_pnl": run.net_pnl,
            "win_rate": run.win_rate,
            "return_pct": run.return_pct,
            "profit_factor": run.profit_factor,
            "max_drawdown_pct": run.max_drawdown_pct,
            "sharpe_ratio": run.sharpe_ratio,
            "sortino_ratio": run.sortino_ratio,
            "expectancy": run.expectancy,
            "alpha": run.alpha,
            "beta": run.beta,
            "started_at": run.started_at,
            "status": run.status.value,
        }
    return {"comparison": comparison}


@router.get("/{run_id}/export")
async def export_backtest(
    run_id: str,
    format: str = "json",
    current_user: UserProfile = Depends(get_current_user),
):
    from backtest.exports import export_csv, export_json, export_pdf

    run = await backtest_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Backtest run not found")

    fmt = format.lower()
    from fastapi.responses import Response

    if fmt == "json":
        return Response(content=export_json(run), media_type="application/json")
    if fmt == "csv":
        return Response(content=export_csv(run), media_type="text/csv; charset=utf-8")
    if fmt == "pdf":
        try:
            content = export_pdf(run)
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))
        from fastapi.responses import Response

        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="backtest-{run_id}.pdf"'},
        )
    raise HTTPException(status_code=400, detail="format must be json, csv, or pdf")


@router.post("/{run_id}/deploy-to-paper")
async def deploy_backtest_to_paper(
    run_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    from builder.manager import builder_manager
    from builder.models import StrategyStatus
    from engine.graph_strategy_runner import start_graph_strategy

    run = await backtest_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    strategy_id = run.config.strategy_id if run.config else ""
    if not strategy_id:
        raise HTTPException(
            status_code=400,
            detail="Only builder (DSL) strategy backtests can be deployed to paper",
        )

    dsl = await builder_manager.get(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if dsl.status not in (StrategyStatus.READY, StrategyStatus.PUBLISHED, StrategyStatus.VALIDATED, StrategyStatus.DRAFT, StrategyStatus.PAPER):
        raise HTTPException(status_code=400, detail=f"Strategy is {dsl.status}; validate and mark ready before deploying")

    result = await start_graph_strategy(
        strategy_id=strategy_id,
        user_id=current_user.id,
        symbol=(run.config.symbol if run.config else "NIFTY").upper(),
        interval=run.config.interval if run.config else "15m",
        is_paper=True,
    )
    await builder_manager.set_status(strategy_id, StrategyStatus.PAPER)
    return {"status": result, "mode": "paper", "strategy_id": strategy_id}


class CorporateActionRequest(BaseModel):
    symbol: str
    ex_date: str
    action: str = "SPLIT"   # SPLIT | BONUS | DIVIDEND
    ratio: str = ""
    dividend_amount: float = 0.0
    record_date: str | None = None


@router.post("/corporate-actions")
async def ingest_corporate_action(
    req: CorporateActionRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    from core.db import async_supabase, get_supabase
    import uuid

    try:
        supabase = get_supabase()
        row = {
            "id": uuid.uuid4().hex[:12],
            "symbol": req.symbol.upper(),
            "ex_date": req.ex_date,
            "action": req.action.upper(),
            "ratio": req.ratio,
            "dividend_amount": req.dividend_amount,
            "record_date": req.record_date,
        }
        result = await async_supabase(
            lambda: supabase.table("corporate_actions").insert(row).execute(),
        )
        if not (result.data or []):
            raise HTTPException(status_code=500, detail="Corporate action insert failed")
        return {"ingested": result.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Corporate action ingest failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Corporate action ingest failed: {str(e)}")
