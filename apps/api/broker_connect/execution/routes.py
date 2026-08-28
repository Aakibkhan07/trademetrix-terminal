"""
FastAPI routes for the execution engine (mount under /api/exec).

  POST /dispatch              -> admin/strategy pushes a Signal; engine fans out
  POST /killswitch/global     -> { on: bool } panic button
  POST /killswitch/user       -> { user_id, on: bool }
  GET  /killswitch            -> current global state

IMPORTANT: /dispatch and kill-switch routes are ADMIN-ONLY. Wire them behind
your admin auth (require_admin) — never expose to customer sessions.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .models import Signal
from .engine import get_engine
from . import killswitch as ks

# Wired to the platform's real admin guard (core.deps.require_admin), which
# checks profiles.is_admin / role and raises 403. Adapted to return the
# admin user id string the engine expects.
from core.deps import require_admin as _core_require_admin
from core.models import UserProfile


async def require_admin(admin: UserProfile = Depends(_core_require_admin)) -> str:
    return str(admin.id)


router = APIRouter(prefix="/api/exec", tags=["execution"])


@router.post("/dispatch")
async def dispatch(signal: Signal, _admin: str = Depends(require_admin)) -> dict:
    batch = await get_engine().dispatch_signal(signal)
    return {
        "signal_id": batch.signal_id,
        "strategy_id": batch.strategy_id,
        "dispatched": batch.dispatched,
        "placed": batch.placed,
        "skipped": batch.skipped,
        "blocked": batch.blocked,
        "errors": batch.errors,
        "results": [
            {"user_id": r.user_id, "broker": r.broker, "status": r.status.value,
             "order_id": r.broker_order_id, "qty": r.qty, "reason": r.reason}
            for r in batch.results
        ],
    }


class GlobalKill(BaseModel):
    on: bool
    reason: str | None = None


class UserKill(BaseModel):
    user_id: str
    on: bool
    reason: str | None = None


@router.post("/killswitch/global")
async def killswitch_global(body: GlobalKill, _admin: str = Depends(require_admin)) -> dict:
    if body.on:
        await ks.trip_global(body.reason or "admin")
    else:
        await ks.reset_global()
    return {"global_kill": body.on}


@router.post("/killswitch/user")
async def killswitch_user(body: UserKill, _admin: str = Depends(require_admin)) -> dict:
    if body.on:
        await ks.trip_user(body.user_id, body.reason or "admin")
    else:
        await ks.reset_user(body.user_id)
    return {"user_id": body.user_id, "kill": body.on}


@router.get("/killswitch")
async def killswitch_state(_admin: str = Depends(require_admin)) -> dict:
    return {"global_kill": await ks.is_global_tripped()}
