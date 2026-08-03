"""Paper Trading — read-only views over Execution Engine state (Paper Trading UI).

Every response is scoped to the authenticated user. Data comes from the
in-memory Execution Engine managers (Trade Manager ledger, Position Manager,
P&L Engine, Portfolio Engine) — the canonical chain that is fed by the frozen
Broker SDK through the legacy bridge. No writes, no new infrastructure.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from core.deps import get_current_user
from core.models import UserProfile

router = APIRouter(prefix="/paper", tags=["paper"])

_BROKER = "paper"


def _account_for(user_id: str) -> dict:
    from execution_engine import pnl_engine

    account = pnl_engine.get_account(user_id, _BROKER)
    return {
        "broker": account.broker,
        "initial_capital": account.initial_capital,
        "realised_pnl": account.realised_pnl,
        "unrealised_pnl": account.unrealised_pnl,
        "daily_pnl": account.daily_pnl,
        "current_equity": account.current_equity,
        "day_start_equity": account.day_start_equity,
        "peak_equity": account.peak_equity,
        "drawdown_pct": account.drawdown_pct,
        "day_date": account.day_date,
        "updated_at": account.updated_at.isoformat(),
    }


@router.get("/status")
async def paper_status(current_user: UserProfile = Depends(get_current_user)):
    from execution_engine import execution_bus
    from execution_engine.events import _ENGINE_BRIDGE_WIRED, _LEGACY_BRIDGE_WIRED

    try:
        from execution.event_bus import execution_event_bus
        legacy_star = len(execution_event_bus._subscribers.get("*", []))
    except Exception:
        legacy_star = 0

    return {
        "engine": {
            "wired": _LEGACY_BRIDGE_WIRED,
            "engine_bridge": _ENGINE_BRIDGE_WIRED,
            "bus_running": execution_bus.running,
            "subscribers": execution_bus.subscriber_count(),
            "legacy_star_subscribers": legacy_star,
        },
        "user_id": current_user.id,
    }


@router.get("/account")
async def paper_account(current_user: UserProfile = Depends(get_current_user)):
    try:
        return _account_for(current_user.id)
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Engine account unavailable: {e}")


@router.get("/positions")
async def paper_positions(current_user: UserProfile = Depends(get_current_user)):
    from execution_engine import position_manager

    positions = position_manager.get_positions(current_user.id, broker=_BROKER)
    positions = [p for p in positions if p.is_open]
    return {
        "positions": [p.model_dump(mode="json") for p in positions],
        "count": len(positions),
    }


@router.get("/trades")
async def paper_trades(
    current_user: UserProfile = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=500),
):
    from execution_engine import trade_manager

    trades = trade_manager.list_trades(current_user.id, broker=_BROKER, limit=limit)
    return {
        "trades": [t.model_dump(mode="json") for t in trades],
        "count": len(trades),
    }


@router.get("/portfolio")
async def paper_portfolio(current_user: UserProfile = Depends(get_current_user)):
    from execution_engine import portfolio_engine

    snap = portfolio_engine.snapshot(current_user.id)
    if snap is None:
        return {
            "brokers": [],
            "open_positions": 0,
            "total_positions": 0,
            "realised_pnl": 0.0,
            "unrealised_pnl": 0.0,
            "daily_pnl": 0.0,
            "current_equity": 0.0,
            "peak_equity": 0.0,
            "drawdown_pct": 0.0,
        }
    return {
        "brokers": snap.brokers,
        "open_positions": snap.open_positions,
        "total_positions": snap.total_positions,
        "realised_pnl": snap.realised_pnl,
        "unrealised_pnl": snap.unrealised_pnl,
        "daily_pnl": snap.daily_pnl,
        "current_equity": snap.current_equity,
        "peak_equity": snap.peak_equity,
        "drawdown_pct": snap.drawdown_pct,
    }
