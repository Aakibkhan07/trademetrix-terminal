"""Compiles user-created visual strategies into ExecutionPlan for the existing pipeline."""

import logging
from datetime import UTC, datetime, time, timedelta

from core.models import (
    Exchange, ExecutionPlan, InstrumentType, LegExpiry, LegOptionType,
    LegPosition, LegSegment, NormalizedOrder, OptionType, OrderSide,
    OrderType, ProductType, StrikeCriteria, UserStrategy,
    UserStrategyLeg,
)

logger = logging.getLogger(__name__)

# Known intervals and lot sizes (from marketdata)
STRIKE_INTERVALS: dict[str, int] = {
    "NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50, "SENSEX": 100,
}
LOT_SIZES: dict[str, int] = {
    "NIFTY": 65, "BANKNIFTY": 30, "FINNIFTY": 60, "SENSEX": 20,
}
WEEKDAY_EXPIRY: dict[str, int] = {
    "NIFTY": 1, "BANKNIFTY": 1, "FINNIFTY": 1, "SENSEX": 3,
}

MAX_LOTS: int = 10
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


# ── Validation ──

class ValidationError(Exception):
    def __init__(self, message: str, field: str = ""):
        self.message = message
        self.field = field
        super().__init__(message)


def validate_user_strategy(strategy: UserStrategy) -> None:
    if not strategy.name or len(strategy.name.strip()) == 0:
        raise ValidationError("Strategy name is required", "name")

    if not strategy.legs:
        raise ValidationError("At least one leg is required", "legs")

    if len(strategy.legs) > 6:
        raise ValidationError("Maximum 6 legs allowed", "legs")

    for leg in strategy.legs:
        if leg.lots < 1:
            raise ValidationError(f"Leg {leg.leg_order}: lots must be >= 1", f"legs.{leg.leg_order}.lots")
        if leg.lots > MAX_LOTS:
            raise ValidationError(f"Leg {leg.leg_order}: lots cannot exceed {MAX_LOTS}", f"legs.{leg.leg_order}.lots")

        if leg.segment == LegSegment.options and not leg.option_type:
            raise ValidationError(f"Leg {leg.leg_order}: option_type is required for options segment", f"legs.{leg.leg_order}.option_type")

        if leg.segment == LegSegment.futures and leg.option_type:
            raise ValidationError(f"Leg {leg.leg_order}: option_type must be null for futures segment", f"legs.{leg.leg_order}.option_type")

        _validate_strike_criteria(leg)

    # Parse and validate entry/exit times
    try:
        entry = time.fromisoformat(strategy.entry_time)
    except (ValueError, TypeError):
        raise ValidationError("entry_time must be in HH:MM format (24h)", "entry_time")

    try:
        exit_ = time.fromisoformat(strategy.exit_time)
    except (ValueError, TypeError):
        raise ValidationError("exit_time must be in HH:MM format (24h)", "exit_time")

    if entry >= exit_:
        raise ValidationError("entry_time must be before exit_time", "exit_time")

    if entry < MARKET_OPEN or entry > MARKET_CLOSE:
        raise ValidationError("entry_time must be between 09:15 and 15:30 IST", "entry_time")

    if exit_ < MARKET_OPEN or exit_ > MARKET_CLOSE:
        raise ValidationError("exit_time must be between 09:15 and 15:30 IST", "exit_time")

    if not strategy.days_of_week:
        raise ValidationError("At least one trading day must be selected", "days_of_week")

    for d in strategy.days_of_week:
        if d < 0 or d > 6:
            raise ValidationError("days_of_week values must be 0 (Mon) to 6 (Sun)", "days_of_week")


def _validate_strike_criteria(leg: UserStrategyLeg) -> None:
    if leg.segment == LegSegment.futures:
        return

    val = leg.strike_value
    criteria = leg.strike_criteria

    if criteria == StrikeCriteria.atm_offset:
        if val < -20 or val > 20:
            raise ValidationError(f"Leg {leg.leg_order}: atm_offset must be between -20 and +20", f"legs.{leg.leg_order}.strike_value")

    elif criteria == StrikeCriteria.premium_closest:
        if val < 0.05:
            raise ValidationError(f"Leg {leg.leg_order}: premium_closest value must be >= 0.05", f"legs.{leg.leg_order}.strike_value")

    elif criteria == StrikeCriteria.premium_range:
        if val < 0:
            raise ValidationError(f"Leg {leg.leg_order}: premium_range min must be >= 0", f"legs.{leg.leg_order}.strike_value")

    elif criteria == StrikeCriteria.delta:
        if val < 0 or val > 1:
            raise ValidationError(f"Leg {leg.leg_order}: delta must be between 0 and 1", f"legs.{leg.leg_order}.strike_value")


# ── Strike Resolution ──

def resolve_strikes(legs: list[UserStrategyLeg], symbol: str, spot_price: float, option_chain: dict | None = None) -> dict[int, float]:
    """Resolves each leg's strike_criteria into an actual strike price.

    Returns dict mapping leg_order -> strike_price.
    If option_chain is None or empty, simulated values are returned with a warning.
    """
    interval = STRIKE_INTERVALS.get(symbol, 50)
    lot_size = LOT_SIZES.get(symbol, 65)
    result: dict[int, float] = {}

    ce_premia = {}
    pe_premia = {}
    ce_deltas = {}
    pe_deltas = {}

    if option_chain:
        strikes_data = option_chain.get("strikes", []) if isinstance(option_chain, dict) else []
        for s in strikes_data:
            strike = s.get("strike", 0)
            ce = s.get("CE", {}) or {}
            pe = s.get("PE", {}) or {}
            ce_premia[strike] = ce.get("ltp", 0) or ce.get("premium", 0)
            pe_premia[strike] = pe.get("ltp", 0) or pe.get("premium", 0)
            ce_deltas[strike] = ce.get("delta", 0) or 0
            pe_deltas[strike] = pe.get("delta", 0) or 0

    is_simulated = False

    for leg in legs:
        if leg.segment == LegSegment.futures:
            result[leg.leg_order] = spot_price
            continue

        criteria = leg.strike_criteria
        val = leg.strike_value

        if criteria == StrikeCriteria.atm_offset:
            atm = _round_to_strike(spot_price, interval)
            result[leg.leg_order] = atm + int(val) * interval

        elif criteria == StrikeCriteria.premium_closest:
            premia = ce_premia if leg.option_type == LegOptionType.ce else pe_premia
            if premia:
                result[leg.leg_order] = min(premia.keys(), key=lambda s: abs(premia[s] - val))
            else:
                is_simulated = True
                atm = _round_to_strike(spot_price, interval)
                result[leg.leg_order] = atm + (1 if leg.option_type == LegOptionType.ce else -1) * interval

        elif criteria == StrikeCriteria.premium_range:
            premia = ce_premia if leg.option_type == LegOptionType.ce else pe_premia
            if premia:
                sorted_strikes = sorted(premia.keys())
                in_range = [s for s in sorted_strikes if premia[s] >= val]
                result[leg.leg_order] = in_range[0] if in_range else sorted_strikes[-1]
            else:
                is_simulated = True
                atm = _round_to_strike(spot_price, interval)
                result[leg.leg_order] = atm + (1 if leg.option_type == LegOptionType.ce else -1) * interval

        elif criteria == StrikeCriteria.delta:
            deltas = ce_deltas if leg.option_type == LegOptionType.ce else pe_deltas
            if deltas:
                result[leg.leg_order] = min(deltas.keys(), key=lambda s: abs(deltas[s] - val))
            else:
                is_simulated = True
                atm = _round_to_strike(spot_price, interval)
                result[leg.leg_order] = atm + (2 if leg.option_type == LegOptionType.ce else -2) * interval

    return result


def _round_to_strike(price: float, interval: int) -> int:
    return round(price / interval) * interval


# ── Expiry Resolution ──

def resolve_expiry(leg: UserStrategyLeg, symbol: str) -> str:
    """Resolves the expiry enum to an actual expiry date string (DDMMMYYYY)."""
    today = datetime.now(UTC).date()
    target_wday = WEEKDAY_EXPIRY.get(symbol, 1)  # default Thursday

    if leg.expiry == LegExpiry.weekly:
        days_ahead = (target_wday - today.weekday()) % 7
        if days_ahead <= 0:
            days_ahead += 7
        expiry = today + timedelta(days=days_ahead)

    elif leg.expiry == LegExpiry.next_weekly:
        days_ahead = (target_wday - today.weekday()) % 7
        expiry = today + timedelta(days=days_ahead + 7)

    elif leg.expiry == LegExpiry.monthly:
        if today.day < 20:
            expiry = today.replace(day=20)
        else:
            next_month = today.replace(month=today.month + 1, day=1) if today.month < 12 else today.replace(year=today.year + 1, month=1, day=1)
            expiry = next_month.replace(day=20)
    else:
        expiry = today + timedelta(days=7)

    return expiry.strftime("%d%b%Y").upper()


# ── Compilation ──

def compile_user_strategy(
    strategy: UserStrategy,
    spot_price: float | None = None,
    option_chain: dict | None = None,
) -> ExecutionPlan:
    """Compiles a UserStrategy into an ExecutionPlan with resolved strikes and NormalizedOrders.

    Args:
        strategy: The validated user strategy with legs.
        spot_price: Current spot price for the index. If None, estimated.
        option_chain: Option chain data for strike resolution. If None, simulated.
        is_simulated: Override simulation flag. Auto-detected if None.

    Returns:
        ExecutionPlan containing NormalizedOrders ready for the pipeline.
    """
    if spot_price is None:
        raise ValueError(f"Cannot compile strategy: spot price required for {strategy.index_symbol}")

    symbol = strategy.index_symbol
    interval = STRIKE_INTERVALS.get(symbol, 50)
    lot_size = LOT_SIZES.get(symbol, 65)

    if not option_chain:
        raise ValueError(f"Cannot compile strategy: option chain required for {symbol}")

    resolved_strikes = resolve_strikes(strategy.legs, symbol, spot_price, option_chain)

    orders: list[NormalizedOrder] = []
    for leg in strategy.legs:
        strike_price = resolved_strikes.get(leg.leg_order, spot_price)
        qty = leg.lots * lot_size
        is_ce = leg.option_type == LegOptionType.ce
        expiry_str = resolve_expiry(leg, symbol)

        order = NormalizedOrder(
            symbol=f"{symbol}{expiry_str}{strike_price}{'CE' if is_ce else 'PE'}" if leg.segment == LegSegment.options else symbol,
            exchange=Exchange.NFO if leg.segment == LegSegment.options else Exchange.NSE,
            side=OrderSide.BUY if leg.position == LegPosition.buy else OrderSide.SELL,
            order_type=OrderType.MARKET,
            product=ProductType.INTRADAY,
            quantity=qty,
            price=0.0,
            strategy_id=strategy.id,
            source="user_strategy",
            instrument_type=InstrumentType.OPT if leg.segment == LegSegment.options else InstrumentType.FUT,
            strike_price=strike_price if leg.segment == LegSegment.options else None,
            expiry_date=expiry_str if leg.segment == LegSegment.options else None,
            option_type=OptionType.CE if is_ce else (OptionType.PE if leg.option_type == LegOptionType.pe else None),
        )
        orders.append(order)

    return ExecutionPlan(
        orders=orders,
        legs=list(strategy.legs),
        strategy_id=strategy.id,
        total_lots=sum(leg.lots for leg in strategy.legs),
    )



