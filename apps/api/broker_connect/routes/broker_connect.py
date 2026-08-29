"""
FastAPI router: self-serve broker connect.

Endpoints (mount under /api/broker):
  GET  /available          -> which brokers are wired up
  POST /connect            -> { broker } -> { authorization_url }   (user taps -> broker login)
  GET  /callback           -> broker redirects here; we store the token; bounce to portal
  GET  /status             -> current user's connection status (no ciphertext)
  POST /disconnect         -> { broker } -> revoke

Security model:
  - /connect and /status and /disconnect require an authenticated portal session
    (Depends(get_current_user) -> user_id).
  - /callback is hit by the BROKER's redirect. It authenticates via the one-time
    `state` we minted in /connect (stored in Redis with the user_id). No session
    cookie is trusted here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..config import get_settings
from ..brokers.registry import (
    get_connector,
    _REGISTRY,
    COMING_SOON_BROKERS,
    UnknownBrokerError,
    BrokerNotConfiguredError,
)
from ..db import connections as db

# ---------------------------------------------------------------------------
# Auth dependency.
# Wired to the platform's real session dependency (core.deps.get_current_user)
# which decodes the httpOnly cookie and returns a UserProfile. The engine
# expects a plain user_id string, so we adapt it into a FastAPI dependency.
# ---------------------------------------------------------------------------
from core.deps import get_current_user as _core_current_user
from core.models import UserProfile


async def get_current_user(user: UserProfile = Depends(_core_current_user)) -> str:
    return str(user.id)


router = APIRouter(prefix="/api/broker", tags=["broker-connect"])


class ConnectBody(BaseModel):
    broker: str


class DisconnectBody(BaseModel):
    broker: str


@router.get("/available")
async def available() -> dict:
    """All registered brokers (so the portal can list every one), each flagged
    with whether the operator has set this broker's app credentials (`configured`)
    and whether the connect flow is still a scaffold (`coming_soon`)."""
    s = get_settings()
    brokers = []
    for key, (attr, _cls) in _REGISTRY.items():
        brokers.append({
            "key": key,
            "configured": bool(getattr(s, attr)),
            "coming_soon": key in COMING_SOON_BROKERS,
        })
    return {"brokers": brokers}


@router.post("/connect")
async def connect(body: ConnectBody, user_id: str = Depends(get_current_user)) -> dict:
    try:
        connector = get_connector(body.broker)
    except UnknownBrokerError:
        raise HTTPException(status_code=400, detail=f"Unsupported broker: {body.broker}")
    except BrokerNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e))

    state = await db.issue_state(user_id, connector.broker_key)
    try:
        url = await connector.authorization_url(state)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Broker rejected connect init: {e}")
    return {"authorization_url": url}


@router.get("/callback")
async def callback(request: Request) -> RedirectResponse:
    params = dict(request.query_params)
    state = params.get("state")
    portal = get_settings().portal_return_url

    if not state:
        return RedirectResponse(f"{portal}?broker=error&reason=missing_state")

    ctx = await db.consume_state(state)
    if not ctx:
        return RedirectResponse(f"{portal}?broker=error&reason=invalid_or_expired_state")

    user_id, broker = ctx["user_id"], ctx["broker"]

    try:
        connector = get_connector(broker)
        token = await connector.exchange(params)
        db.upsert_connection(user_id, broker, token)
    except Exception as e:
        # best-effort mark; connection may not exist yet
        try:
            db.mark_status(user_id, broker, "error", str(e))
        except Exception:
            pass
        return RedirectResponse(f"{portal}?broker={broker}&status=error")

    return RedirectResponse(f"{portal}?broker={broker}&status=connected")


@router.get("/status")
async def status(user_id: str = Depends(get_current_user)) -> dict:
    return {"connections": db.list_status(user_id)}


@router.post("/disconnect")
async def disconnect(body: DisconnectBody, user_id: str = Depends(get_current_user)) -> dict:
    db.disconnect(user_id, body.broker)
    return {"ok": True, "broker": body.broker}
