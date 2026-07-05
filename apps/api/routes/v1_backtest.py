import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backtest.manager import backtest_manager
from backtest.models import BacktestConfig, BacktestStatus, ReplaySpeed
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
        )

        result = await engine.run(candles)
        return {
            "symbol": req.symbol,
            "strategy": req.strategy_type,
            "interval": req.interval,
            "days": req.days,
            "initial_capital": req.initial_capital,
            "candles_analyzed": len(candles),
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
        )

        result = await engine.run(candles)
        return {
            "symbol": req.symbol,
            "strategy": req.strategy_type,
            "interval": req.interval,
            "days": req.days,
            "initial_capital": req.initial_capital,
            "candles_analyzed": len(candles),
            "results": result.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Backtest failed")
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")


@router.get("/{run_id}")
async def get_backtest(
    run_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    run = backtest_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest run not found")
    return run
