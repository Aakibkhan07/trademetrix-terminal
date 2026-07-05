"""
Paper trading routes for crypto and forex.
SAFETY: These routes ONLY operate on virtual accounts. NO real orders are ever placed.
No broker credentials are accessed. No exchange APIs are called.
Paper-only boundary is enforced here and in crypto_forex_engine.py.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from core.capabilities import Capabilities
from core.deps import get_current_user, get_capabilities
from core.models import UserProfile
from paper.crypto_forex_engine import crypto_forex_engine
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

crypto_router = APIRouter(prefix="/api/v1/crypto", tags=["crypto"])
forex_router = APIRouter(prefix="/api/v1/forex", tags=["forex"])


class PlaceOrderRequest(BaseModel):
    symbol: str
    side: str
    quantity: float = Field(gt=0)
    order_type: str = "market"
    price: float | None = None


class ResetAccountRequest(BaseModel):
    initial_balance: float = 10000.0


def _check_tier(caps: Capabilities, user: UserProfile):
    if user.role == "super_admin":
        return True
    if not getattr(caps, "paper_crypto_forex_allowed", False):
        raise HTTPException(
            status_code=403,
            detail=f"Your plan ({caps.tier}) does not include Paper Crypto/Forex trading. Please upgrade.",
        )
    return True


# ── Crypto Routes ──


@crypto_router.get("/pairs")
async def crypto_pairs(user: UserProfile = Depends(get_current_user), caps: Capabilities = Depends(get_capabilities)):
    _check_tier(caps, user)
    return {"pairs": await crypto_forex_engine.pairs("crypto")}


@crypto_router.post("/order")
async def crypto_order(req: PlaceOrderRequest, user: UserProfile = Depends(get_current_user), caps: Capabilities = Depends(get_capabilities)):
    _check_tier(caps, user)
    result = await crypto_forex_engine.place_order(
        user_id=user.id,
        asset_class="crypto",
        symbol=req.symbol,
        side=req.side.lower(),
        quantity=req.quantity,
        order_type=req.order_type.lower(),
        price=req.price,
    )
    return result


@crypto_router.get("/account")
async def crypto_account(user: UserProfile = Depends(get_current_user), caps: Capabilities = Depends(get_capabilities)):
    _check_tier(caps, user)
    acct = crypto_forex_engine.get_account_summary(user.id)
    if not acct:
        acct = crypto_forex_engine.get_or_create_account(user.id).to_dict()
    return {"account": acct}


@crypto_router.get("/positions")
async def crypto_positions(user: UserProfile = Depends(get_current_user), caps: Capabilities = Depends(get_capabilities)):
    _check_tier(caps, user)
    return {"positions": crypto_forex_engine.get_positions(user.id)}


@crypto_router.get("/orders")
async def crypto_orders(user: UserProfile = Depends(get_current_user), caps: Capabilities = Depends(get_capabilities)):
    _check_tier(caps, user)
    return {"orders": crypto_forex_engine.get_orders(user.id)}


@crypto_router.post("/account/reset")
async def crypto_reset(req: ResetAccountRequest, user: UserProfile = Depends(get_current_user), caps: Capabilities = Depends(get_capabilities)):
    _check_tier(caps, user)
    crypto_forex_engine.reset_account(user.id, req.initial_balance)
    return {"success": True, "message": f"Account reset with ${req.initial_balance:.2f}"}


# ── Forex Routes ──


@forex_router.get("/pairs")
async def forex_pairs(user: UserProfile = Depends(get_current_user), caps: Capabilities = Depends(get_capabilities)):
    _check_tier(caps, user)
    return {"pairs": await crypto_forex_engine.pairs("forex")}


@forex_router.post("/order")
async def forex_order(req: PlaceOrderRequest, user: UserProfile = Depends(get_current_user), caps: Capabilities = Depends(get_capabilities)):
    _check_tier(caps, user)
    result = await crypto_forex_engine.place_order(
        user_id=user.id,
        asset_class="forex",
        symbol=req.symbol,
        side=req.side.lower(),
        quantity=req.quantity,
        order_type=req.order_type.lower(),
        price=req.price,
    )
    return result


@forex_router.get("/account")
async def forex_account(user: UserProfile = Depends(get_current_user), caps: Capabilities = Depends(get_capabilities)):
    _check_tier(caps, user)
    acct = crypto_forex_engine.get_account_summary(user.id)
    if not acct:
        acct = crypto_forex_engine.get_or_create_account(user.id).to_dict()
    return {"account": acct}


@forex_router.get("/positions")
async def forex_positions(user: UserProfile = Depends(get_current_user), caps: Capabilities = Depends(get_capabilities)):
    _check_tier(caps, user)
    return {"positions": crypto_forex_engine.get_positions(user.id)}


@forex_router.get("/orders")
async def forex_orders(user: UserProfile = Depends(get_current_user), caps: Capabilities = Depends(get_capabilities)):
    _check_tier(caps, user)
    return {"orders": crypto_forex_engine.get_orders(user.id)}


@forex_router.post("/account/reset")
async def forex_reset(req: ResetAccountRequest, user: UserProfile = Depends(get_current_user), caps: Capabilities = Depends(get_capabilities)):
    _check_tier(caps, user)
    crypto_forex_engine.reset_account(user.id, req.initial_balance)
    return {"success": True, "message": f"Account reset with ${req.initial_balance:.2f}"}
