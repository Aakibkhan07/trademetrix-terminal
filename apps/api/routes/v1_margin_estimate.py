import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from brokers import get_broker
from brokers.token_manager import TokenManager
from core.deps import get_current_user
from core.models import (
    LegExpiry,
    LegOptionType,
    LegPosition,
    LegSegment,
    StrikeCriteria,
    UserProfile,
    UserStrategy,
    UserStrategyLeg,
)
from engine.strategy_compiler import compile_user_strategy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/margin-estimate", tags=["margin-estimate"])


class EstimateLeg(BaseModel):
    segment: str = "options"
    position: str = "buy"
    lots: int = 1
    option_type: str | None = "CE"
    expiry: str = "weekly"
    strike_criteria: str = "atm_offset"
    strike_value: float = 0


class MarginEstimateRequest(BaseModel):
    index_symbol: str = "NIFTY"
    legs: list[EstimateLeg]
    broker: str = ""


class MarginEstimateResponse(BaseModel):
    supported: bool
    broker: str
    total_margin: float = 0
    span_margin: float = 0
    exposure_margin: float = 0
    currency: str = "INR"
    error: str | None = None


@router.post("/", response_model=MarginEstimateResponse)
async def margin_estimate(
    req: MarginEstimateRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    if not req.legs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one leg required")

    broker = req.broker or "fyers"

    try:
        token_mgr = TokenManager(current_user.id, broker)
        session = await token_mgr.get_session()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Broker connection failed for {broker}: {e}",
        )

    try:
        adapter_cls = get_broker(broker)
        adapter = adapter_cls()
        await adapter.authenticate(session)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Broker auth failed for {broker}: {e}",
        )

    # Convert raw legs to UserStrategyLeg, compile, then extract NormalizedOrders
    strategy_legs = []
    for i, leg in enumerate(req.legs):
        strategy_legs.append(UserStrategyLeg(
            leg_order=i + 1,
            segment=LegSegment(leg.segment),
            position=LegPosition(leg.position),
            lots=leg.lots,
            option_type=LegOptionType(leg.option_type) if leg.option_type and leg.segment == "options" else None,
            expiry=LegExpiry(leg.expiry),
            strike_criteria=StrikeCriteria(leg.strike_criteria),
            strike_value=leg.strike_value,
        ))

    strategy = UserStrategy(
        index_symbol=req.index_symbol,
        legs=strategy_legs,
        entry_time="09:15",
        exit_time="15:15",
        days_of_week=[1, 2, 3, 4, 5],
    )

    plan = compile_user_strategy(strategy)

    leg_dicts = []
    for order in plan.orders:
        leg_dicts.append({
            "symbol": order.symbol,
            "quantity": order.quantity,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "product": order.product.value,
        })

    result = await adapter.get_margin_estimate(leg_dicts)

    if not result.get("supported"):
        return MarginEstimateResponse(
            supported=False,
            broker=broker,
            error=result.get("error"),
        )

    return MarginEstimateResponse(
        supported=True,
        broker=broker,
        total_margin=result.get("total_margin", 0),
        span_margin=result.get("span_margin", 0),
        exposure_margin=result.get("exposure_margin", 0),
        currency=result.get("currency", "INR"),
    )
