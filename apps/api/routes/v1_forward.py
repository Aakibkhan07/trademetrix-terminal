import asyncio
import logging
from datetime import UTC, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.deps import get_current_user
from core.models import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forward-tests", tags=["forward-tests"])

_BACKTEST_RESULT_ATTR = "result"  # may not exist on all BacktestResult versions

# ── Models ──────────────────────────────────────────────────────────────────

class ForwardTestCreateRequest(BaseModel):
    backtest_run_id: str = Field(..., description="Backtest run ID to base the forward test on")
    strategy_id: str = Field(..., description="DSL strategy ID to run forward")
    symbol: str = Field(default="NIFTY", description="Live symbol to trade")
    interval: str = Field(default="5m", description="Candle interval")
    initial_capital: float = Field(default=100000, description="Virtual capital for the forward test")
    max_duration_hours: float = Field(default=24, description="Auto-stop after this many hours")
    deviation_threshold_pct: float = Field(default=15.0, description="Alert if live equity deviates from backtest expectancy by this %")


class ForwardTestResponse(BaseModel):
    id: str
    backtest_run_id: str
    strategy_id: str
    symbol: str
    interval: str
    mode: str = "forward"
    status: str  # pending | running | stopped | completed | killed
    initial_capital: float
    max_duration_hours: float
    deviation_threshold_pct: float
    current_equity: float = 0.0
    peak_equity: float = 0.0
    drawdown_pct: float = 0.0
    trades_count: int = 0
    signals_count: int = 0
    started_at: str | None = None
    stopped_at: str | None = None
    estimated_trend: str = "pending"  # pending | tracking | deviating | recovered
    backtest_stats: dict | None = None


class ForwardTestListResponse(BaseModel):
    items: list[ForwardTestResponse]


class ForwardTestStatusResponse(BaseModel):
    id: str
    status: str
    current_equity: float
    peak_equity: float
    drawdown_pct: float
    trades_count: int
    signals_count: int
    deviation_pct: float | None = None
    estimated_trend: str
    last_signal_at: str | None = None
    runtime_stats: dict | None = None


# ── In-memory store (forward tests are ephemeral) ──────────────────────────

_forward_tests: dict[str, dict[str, Any]] = {}
_running_forward_tasks: dict[str, asyncio.Task] = {}


def _new_forward_test_id() -> str:
    return f"ft_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{len(_forward_tests)}"


# ── Routes ──────────────────────────────────────────────────────────────────

@router.get("/", response_model=ForwardTestListResponse)
async def list_forward_tests(current_user: UserProfile = Depends(get_current_user)):
    out: list[ForwardTestResponse] = []
    for ft in _forward_tests.values():
        if ft.get("user_id") == current_user.id:
            out.append(_ft_to_response(ft))
    return ForwardTestListResponse(items=out)


@router.post("/", response_model=ForwardTestResponse)
async def create_forward_test(
    req: ForwardTestCreateRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    from backtest.manager import backtest_manager

    run_id = req.backtest_run_id

    if ft := _forward_tests.get(run_id):
        if ft.get("user_id") == current_user.id:
            raise HTTPException(status_code=409, detail=f"Forward test already exists for backtest run {run_id}")
        raise HTTPException(status_code=403, detail="Forward test already exists for this run (owned by another user)")

    backtest_run = await backtest_manager.get_run(run_id)
    if not backtest_run:
        raise HTTPException(status_code=404, detail=f"Backtest run {run_id} not found")

    ft_id = _new_forward_test_id()
    stats: dict[str, Any] = {"win_rate": 0, "profit_factor": 0, "total_pnl": 0}
    try:
        raw = getattr(backtest_run, _BACKTEST_RESULT_ATTR, None)
        if raw is not None:
            stats = raw.model_dump(mode="json") if hasattr(raw, "model_dump") else dict(raw)
    except Exception:
        pass

    ft: dict[str, Any] = {
        "id": ft_id,
        "backtest_run_id": run_id,
        "strategy_id": req.strategy_id,
        "symbol": req.symbol.upper(),
        "interval": req.interval,
        "mode": "forward",
        "status": "pending",
        "user_id": current_user.id,
        "initial_capital": req.initial_capital,
        "max_duration_hours": req.max_duration_hours,
        "deviation_threshold_pct": req.deviation_threshold_pct,
        "current_equity": req.initial_capital,
        "peak_equity": req.initial_capital,
        "drawdown_pct": 0.0,
        "trades_count": 0,
        "signals_count": 0,
        "started_at": None,
        "stopped_at": None,
        "estimated_trend": "pending",
        "backtest_stats": stats,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _forward_tests[ft_id] = ft
    logger.info("Forward test %s created for backtest run %s (strategy %s)", ft_id, run_id, req.strategy_id)
    return _ft_to_response(ft)


@router.get("/{ft_id}", response_model=ForwardTestStatusResponse)
async def get_forward_test_status(ft_id: str, current_user: UserProfile = Depends(get_current_user)):
    ft = _forward_tests.get(ft_id)
    if not ft:
        raise HTTPException(status_code=404, detail=f"Forward test {ft_id} not found")
    if ft.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Not your forward test")
    return _status_response(ft)


@router.post("/{ft_id}/start", response_model=ForwardTestStatusResponse)
async def start_forward_test(ft_id: str, current_user: UserProfile = Depends(get_current_user)):
    ft = _forward_tests.get(ft_id)
    if not ft:
        raise HTTPException(status_code=404, detail=f"Forward test {ft_id} not found")
    if ft.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Not your forward test")
    if ft.get("status") == "running":
        raise HTTPException(status_code=409, detail="Forward test already running")

    from engine.graph_strategy_runner import start_graph_strategy

    strategy_id = ft["strategy_id"]
    symbol = ft["symbol"]
    interval = ft["interval"]

    result = await start_graph_strategy(
        strategy_id=strategy_id,
        user_id=current_user.id,
        symbol=symbol,
        interval=interval,
        is_paper=True,
    )
    if result == "already_running":
        raise HTTPException(status_code=409, detail="Strategy already running elsewhere")

    ft["status"] = "running"
    ft["started_at"] = datetime.now(UTC).isoformat()
    ft["current_equity"] = ft["initial_capital"]
    ft["estimated_trend"] = "tracking"

    _running_forward_tasks[ft_id] = asyncio.current_task()

    asyncio.create_task(_forward_monitor(ft_id, current_user.id, ft))

    logger.info("Forward test %s started (strategy %s, symbol %s)", ft_id, strategy_id, symbol)
    return _status_response(ft)


@router.post("/{ft_id}/stop", response_model=ForwardTestStatusResponse)
async def stop_forward_test(ft_id: str, current_user: UserProfile = Depends(get_current_user)):
    ft = _forward_tests.get(ft_id)
    if not ft:
        raise HTTPException(status_code=404, detail=f"Forward test {ft_id} not found")
    if ft.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Not your forward test")
    if ft.get("status") != "running":
        raise HTTPException(status_code=409, detail="Forward test not running")

    from engine.graph_strategy_runner import stop_graph_strategy

    strategy_id = ft["strategy_id"]
    await stop_graph_strategy(strategy_id)

    ft["status"] = "stopped"
    ft["stopped_at"] = datetime.now(UTC).isoformat()
    ft["estimated_trend"] = "stopped"

    _running_forward_tasks.pop(ft_id, None)

    logger.info("Forward test %s stopped by user", ft_id)
    return _status_response(ft)


@router.get("/{ft_id}/compare")
async def compare_forward_vs_backtest(ft_id: str, current_user: UserProfile = Depends(get_current_user)):
    ft = _forward_tests.get(ft_id)
    if not ft:
        raise HTTPException(status_code=404, detail=f"Forward test {ft_id} not found")
    if ft.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Not your forward test")

    bt_stats = ft.get("backtest_stats") or {}
    current = ft.get("current_equity", ft["initial_capital"])
    initial = ft["initial_capital"]
    live_pnl_pct = ((current - initial) / initial) * 100 if initial > 0 else 0

    bt_pnl = bt_stats.get("total_pnl", 0)
    bt_pnl_pct = bt_pnl / (ft["initial_capital"] or 1) * 100

    bt_win_rate = bt_stats.get("win_rate", 0) * 100
    bt_profit_factor = bt_stats.get("profit_factor", 0)

    return {
        "forward_test_id": ft_id,
        "backtest_run_id": ft["backtest_run_id"],
        "symbol": ft["symbol"],
        "interval": ft["interval"],
        "initial_capital": ft["initial_capital"],
        "backtest": {
            "total_pnl": bt_pnl,
            "pnl_pct": round(bt_pnl_pct, 2),
            "win_rate": round(bt_win_rate, 1),
            "profit_factor": round(bt_profit_factor, 2),
            "trades": bt_stats.get("total_trades", 0),
        },
        "forward": {
            "current_equity": round(current, 2),
            "pnl_pct": round(live_pnl_pct, 2),
            "trades_count": ft.get("trades_count", 0),
            "signals_count": ft.get("signals_count", 0),
            "drawdown_pct": round(ft.get("drawdown_pct", 0), 2),
            "estimated_trend": ft.get("estimated_trend", "pending"),
            "deviation_threshold_pct": ft.get("deviation_threshold_pct", 15),
        },
        "deviation_alert": abs(live_pnl_pct - bt_pnl_pct) > ft.get("deviation_threshold_pct", 15),
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ft_to_response(ft: dict[str, Any]) -> ForwardTestResponse:
    return ForwardTestResponse(
        id=ft["id"],
        backtest_run_id=ft["backtest_run_id"],
        strategy_id=ft["strategy_id"],
        symbol=ft["symbol"],
        interval=ft["interval"],
        mode=ft.get("mode", "forward"),
        status=ft["status"],
        initial_capital=ft["initial_capital"],
        max_duration_hours=ft["max_duration_hours"],
        deviation_threshold_pct=ft["deviation_threshold_pct"],
        current_equity=ft.get("current_equity", ft["initial_capital"]),
        peak_equity=ft.get("peak_equity", ft["initial_capital"]),
        drawdown_pct=ft.get("drawdown_pct", 0),
        trades_count=ft.get("trades_count", 0),
        signals_count=ft.get("signals_count", 0),
        started_at=ft.get("started_at"),
        stopped_at=ft.get("stopped_at"),
        estimated_trend=ft.get("estimated_trend", "pending"),
        backtest_stats=ft.get("backtest_stats"),
    )


def _status_response(ft: dict[str, Any]) -> ForwardTestStatusResponse:
    equity = ft.get("current_equity", ft["initial_capital"])
    peak = ft.get("peak_equity", ft["initial_capital"])
    draw = ft.get("drawdown_pct", 0)
    dev = None
    if ft.get("backtest_stats") and ft["backtest_stats"].get("total_pnl"):
        bt_pnl_pct = ft["backtest_stats"]["total_pnl"] / (ft["initial_capital"] or 1) * 100
        dev = round(((equity - ft["initial_capital"]) / (ft["initial_capital"] or 1) * 100) - bt_pnl_pct, 2)

    return ForwardTestStatusResponse(
        id=ft["id"],
        status=ft["status"],
        current_equity=round(equity, 2),
        peak_equity=round(peak, 2),
        drawdown_pct=round(draw, 2),
        trades_count=ft.get("trades_count", 0),
        signals_count=ft.get("signals_count", 0),
        deviation_pct=dev,
        estimated_trend=ft.get("estimated_trend", "pending"),
        last_signal_at=ft.get("last_activity"),
        runtime_stats=ft.get("runtime_stats"),
    )


async def _forward_monitor(ft_id: str, user_id: str, ft: dict[str, Any]) -> None:
    from engine.graph_strategy_runner import _runtime_stats

    start_time = datetime.now(UTC)
    max_duration = ft["max_duration_hours"] * 3600
    threshold = ft["deviation_threshold_pct"]
    initial = ft["initial_capital"]

    try:
        while ft["status"] == "running":
            await asyncio.sleep(10)

            stats = _runtime_stats(ft["strategy_id"])
            if stats.get("status") == "stopped":
                ft["status"] = "stopped"
                ft["stopped_at"] = datetime.now(UTC).isoformat()
                ft["estimated_trend"] = "stopped"
                break

            elapsed = (datetime.now(UTC) - start_time).total_seconds()
            if elapsed > max_duration:
                ft["status"] = "completed"
                ft["stopped_at"] = datetime.now(UTC).isoformat()
                ft["estimated_trend"] = "completed"
                logger.info("Forward test %s auto-stopped (max duration reached)", ft_id)
                break

            equity = ft.get("current_equity", initial)
            peak = max(peak, equity)
            ft["peak_equity"] = peak
            if initial > 0:
                dd = max(0, ((peak - equity) / peak) * 100)
                ft["drawdown_pct"] = round(dd, 2)

            if ft["backtest_stats"] and ft["backtest_stats"].get("total_pnl"):
                bt_pnl_pct = ft["backtest_stats"]["total_pnl"] / initial * 100
                live_pct = ((equity - initial) / initial) * 100
                deviation = abs(live_pct - bt_pnl_pct)
                if deviation > threshold and ft["estimated_trend"] == "tracking":
                    ft["estimated_trend"] = "deviating"
                    logger.warning("Forward test %s deviating from backtest (%.1f%% vs %.1f%%, threshold %.1f%%)",
                                   ft_id, live_pct, bt_pnl_pct, threshold)
                elif deviation < threshold * 0.5 and ft["estimated_trend"] == "deviating":
                    ft["estimated_trend"] = "recovered"
                    logger.info("Forward test %s recovered to tracking range", ft_id)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.exception("Forward monitor error for %s: %s", ft_id, e)
        ft["estimated_trend"] = "error"
