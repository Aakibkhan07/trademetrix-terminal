import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.deps import get_current_user
from core.models import NormalizedOrder, OrderSide, OrderType, ProductType, Exchange, InstrumentType, OptionType, UserProfile
from execution.manager import ExecutionManager
from execution.models import ExecutionRequest
from execution.validation import validate_order
from oms.manager import order_manager
from oms.models import OmniOrder
from risk.helpers import get_active_broker
from risk.manager import RiskManager

router = APIRouter(prefix="/orders", tags=["orders"])
logger = logging.getLogger(__name__)


class PlaceOrderRequest(BaseModel):
    symbol: str = Field(..., description="Trading symbol (e.g. NIFTY, RELIANCE)")
    exchange: str = Field(default="NSE", description="Exchange (NSE, BSE, NFO)")
    side: str = Field(..., description="BUY or SELL")
    order_type: str = Field(default="MARKET", description="MARKET, LIMIT, SL, SLM")
    product: str = Field(default="INTRADAY", description="INTRADAY, DELIVERY, MIS, NRML")
    quantity: int = Field(..., gt=0, description="Number of units/shares/lots")
    price: float | None = Field(None, ge=0, description="Price for LIMIT/SL orders")
    trigger_price: float | None = Field(None, ge=0, description="Trigger price for SL orders")
    disclosed_quantity: int | None = Field(None, ge=0, description="Disclosed quantity")
    validity: str | None = Field(None, description="DAY or IOC")
    instrument_type: str | None = Field(None, description="EQ, FUT, OPT")
    strike_price: float | None = Field(None, description="Strike price for options")
    expiry_date: str | None = Field(None, description="Expiry date for F&O")
    option_type: str | None = Field(None, description="CE or PE for options")
    strategy_id: str | None = Field(None, description="Associated strategy ID")
    source: str = Field(default="api", description="Order source")
    broker: str | None = Field(None, description="Broker to route through (auto-detected if not set)")
    is_paper: bool = Field(default=False, description="Paper trade (simulated, no real broker)")


class ModifyOrderRequest(BaseModel):
    quantity: int | None = Field(None, gt=0)
    price: float | None = Field(None, ge=0)
    trigger_price: float | None = Field(None, ge=0)


def _to_normalized(req: PlaceOrderRequest, user_id: str, broker: str) -> NormalizedOrder:
    return NormalizedOrder(
        symbol=req.symbol,
        exchange=Exchange(req.exchange.upper()),
        side=OrderSide(req.side.upper()),
        order_type=OrderType(req.order_type.upper()),
        product=ProductType(req.product.upper()),
        quantity=req.quantity,
        price=req.price or 0.0,
        trigger_price=req.trigger_price or 0.0,
        disclosed_quantity=req.disclosed_quantity or 0,
        validity=req.validity or "DAY",
        user_id=user_id,
        broker=broker,
        instrument_type=InstrumentType(req.instrument_type.upper()) if req.instrument_type else InstrumentType.EQ,
        strike_price=req.strike_price,
        expiry_date=req.expiry_date,
        option_type=OptionType(req.option_type.upper()) if req.option_type else None,
        strategy_id=req.strategy_id or "",
        source=req.source,
        is_paper=req.is_paper or (broker == "paper"),
    )


def _oms_to_dict(order: OmniOrder) -> dict:
    def _val(v):
        return v.value if hasattr(v, "value") else v
    return {
        "oms_order_id": order.oms_order_id,
        "client_order_id": order.client_order_id,
        "broker_order_id": order.broker_order_id,
        "user_id": order.user_id,
        "broker": order.broker,
        "symbol": order.symbol,
        "exchange": _val(order.exchange),
        "side": _val(order.side),
        "order_type": _val(order.order_type),
        "product": _val(order.product),
        "quantity": order.quantity,
        "filled_quantity": order.filled_quantity,
        "average_price": order.average_price,
        "price": order.price,
        "trigger_price": order.trigger_price,
        "state": _val(order.state),
        "strategy_id": order.strategy_id,
        "is_paper": order.is_paper,
        "error_code": order.error_code,
        "message": order.message,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        "filled_at": order.filled_at.isoformat() if order.filled_at else None,
        "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
    }


@router.get("/")
async def list_orders(
    current_user: UserProfile = Depends(get_current_user),
    active_only: bool = False,
):
    if active_only:
        orders = await order_manager.get_active_orders(current_user.id)
    else:
        orders = await order_manager.get_orders_by_user(current_user.id)
    return {"orders": [_oms_to_dict(o) for o in orders]}


@router.post("/", status_code=201)
async def place_order(
    req: PlaceOrderRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    broker = req.broker or await get_active_broker(current_user.id)
    if not broker:
        raise HTTPException(status_code=400, detail="No active broker found. Save broker credentials first or specify broker.")

    normalized = _to_normalized(req, current_user.id, broker)

    validation = await validate_order(normalized, current_user.id)
    if not validation.valid:
        raise HTTPException(status_code=422, detail={"errors": validation.errors, "warnings": validation.warnings})

    exec_req = ExecutionRequest(
        user_id=current_user.id,
        broker=broker,
        symbol=req.symbol,
        exchange=req.exchange.upper(),
        side=req.side.upper(),
        order_type=req.order_type.upper(),
        product=req.product.upper(),
        quantity=req.quantity,
        price=req.price or 0.0,
        trigger_price=req.trigger_price or 0.0,
        disclosed_quantity=req.disclosed_quantity or 0,
        validity=req.validity or "DAY",
        strategy_id=req.strategy_id or "",
        source=req.source,
        is_paper=req.is_paper,
    )

    risk_mgr = RiskManager()
    risk_result = await risk_mgr.evaluate(exec_req, dry_run=True)
    if risk_result.decision.value == "REJECTED":
        reasons = [r.reason for r in risk_result.results if r.reason]
        raise HTTPException(status_code=400, detail=f"Risk check failed: {'; '.join(reasons)}")

    try:
        order = await order_manager.place_order(exec_req)
        logger.info("Order placed: %s for user=%s symbol=%s qty=%s", order.oms_order_id, current_user.id, req.symbol, req.quantity)
        return _oms_to_dict(order)
    except Exception as e:
        logger.error("Order placement failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Order placement failed: {e}")


@router.put("/{order_id}")
async def modify_order(
    order_id: str,
    changes: ModifyOrderRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    order = await order_manager.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this order")

    change_dict = {k: v for k, v in changes.model_dump().items() if v is not None}
    if not change_dict:
        raise HTTPException(status_code=422, detail="No changes provided")

    try:
        updated = await order_manager.modify_order(order_id, change_dict)
        if not updated:
            raise HTTPException(status_code=404, detail="Order not found")
        if updated.message and ("failed" in updated.message.lower() or "cannot" in updated.message.lower()):
            raise HTTPException(status_code=400, detail=updated.message)
        return _oms_to_dict(updated)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Order modification failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Order modification failed: {e}")


@router.delete("/{order_id}")
async def cancel_order(
    order_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    order = await order_manager.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this order")

    try:
        cancelled = await order_manager.cancel_order(order_id)
        if not cancelled:
            raise HTTPException(status_code=404, detail="Order not found")
        if cancelled.message and ("failed" in cancelled.message.lower() or "cannot" in cancelled.message.lower()):
            raise HTTPException(status_code=400, detail=cancelled.message)
        return _oms_to_dict(cancelled)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Order cancellation failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Order cancellation failed: {e}")
