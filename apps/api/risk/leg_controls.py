"""Trailing stop-loss, re-entry state machine, and time-based square-off.

Every generated order flows through gate → RiskGuard → execute_order.
Kill switch or daily loss cap breach stops the strategy and cancels
pending re-entries, logged to audit trail.
"""

import logging
import time
from datetime import UTC, datetime

from core.cache import cache
from core.capabilities import resolve_capabilities_by_id
from core.models import (
    AuditLogEntry, NormalizedOrder, OrderSide, OrderStatus, OrderType,
    ProductType, SLTargetType, UserStrategyLeg,
)
from risk.riskguard import RiskGuard

logger = logging.getLogger(__name__)

REENTRY_STATE_KEY = "leg_reentry:{user_id}:{strategy_id}:leg_{leg_order}"
SQUARED_OFF_KEY = "leg_squared_off:{user_id}:{strategy_id}:leg_{leg_order}"
MAX_REENTRIES = 3

class ReentryMode:
    RE_ASAP = "RE_ASAP"
    RE_COST = "RE_COST"

async def compute_trailing_stop(
    leg: UserStrategyLeg,
    entry_price: float,
    current_price: float,
    side: str,
) -> tuple[float | None, float | None, bool]:
    """Compute the current trailed stop price.

    Returns:
        (current_trail_activation_level, current_stop_price, is_activated)
    """
    if leg.trailing_sl_type is None or leg.trailing_sl_value is None:
        return None, None, False

    side_is_long = side.lower() == "buy"
    trail_type = leg.trailing_sl_type.value if hasattr(leg.trailing_sl_type, 'value') else str(leg.trailing_sl_type)
    trail_by = float(leg.trailing_sl_value)
    activation = float(leg.trailing_activation) if leg.trailing_activation else 0.0

    raw_pnl = current_price - entry_price if side_is_long else entry_price - current_price
    pnl_pct = (raw_pnl / entry_price * 100) if entry_price > 0 else 0

    if pnl_pct < activation:
        return None, None, False

    if trail_type == "percent":
        trail_distance = entry_price * trail_by / 100
    elif trail_type == "points":
        trail_distance = trail_by
    elif trail_type == "premium":
        trail_distance = trail_by
    else:
        return None, None, False

    if side_is_long:
        new_stop = current_price - trail_distance
    else:
        new_stop = current_price + trail_distance

    return activation, new_stop, True

async def check_trailing_sl_trigger(
    leg: UserStrategyLeg,
    entry_price: float,
    current_stop: float | None,
    current_price: float,
    side: str,
) -> bool:
    """Check if trailing stop-loss is hit."""
    if current_stop is None:
        return False
    side_is_long = side.lower() == "buy"
    if side_is_long and current_price <= current_stop:
        return True
    if not side_is_long and current_price >= current_stop:
        return True
    return False

def build_square_off_order(
    strategy_id: str,
    user_id: str,
    symbol: str,
    side: str,
    quantity: int,
    leg_order: int,
    reason: str = "square_off",
) -> NormalizedOrder:
    opposite = OrderSide.SELL if side.lower() == "buy" else OrderSide.BUY
    return NormalizedOrder(
        symbol=symbol,
        exchange="NFO",
        side=opposite,
        order_type=OrderType.MARKET,
        product=ProductType.INTRADAY,
        quantity=quantity,
        price=0.0,
        strategy_id=strategy_id,
        user_id=user_id,
        source="leg_control",
        is_paper=False,
    )

async def _get_reentry_count(user_id: str, strategy_id: str, leg_order: int) -> int:
    key = REENTRY_STATE_KEY.format(user_id=user_id, strategy_id=strategy_id, leg_order=leg_order)
    val = await cache.get(key, 0)
    return int(val) if val else 0

async def _set_reentry_count(user_id: str, strategy_id: str, leg_order: int, count: int):
    key = REENTRY_STATE_KEY.format(user_id=user_id, strategy_id=strategy_id, leg_order=leg_order)
    await cache.set(key, count, ttl=86400)

async def _clear_reentry_count(user_id: str, strategy_id: str, leg_order: int):
    key = REENTRY_STATE_KEY.format(user_id=user_id, strategy_id=strategy_id, leg_order=leg_order)
    await cache.delete(key)

async def _is_squared_off(user_id: str, strategy_id: str, leg_order: int) -> bool:
    key = SQUARED_OFF_KEY.format(user_id=user_id, strategy_id=strategy_id, leg_order=leg_order)
    val = await cache.get(key, False)
    return bool(val)

async def _mark_squared_off(user_id: str, strategy_id: str, leg_order: int):
    key = SQUARED_OFF_KEY.format(user_id=user_id, strategy_id=strategy_id, leg_order=leg_order)
    await cache.set(key, True, ttl=86400)

async def _record_audit(user_id: str, action: str, resource: str, details: dict | None = None):
    try:
        from core.audit import record_audit
        entry = AuditLogEntry(
            user_id=user_id,
            action=action,
            resource=resource,
            details=details,
        )
        record_audit(entry)
    except Exception as e:
        logger.warning("Audit record failed: %s", e)

async def execute_leg_control(
    user_id: str,
    strategy_id: str,
    order: NormalizedOrder,
    source: str,
) -> dict:
    """Execute a leg control order through gate with RiskGuard.

    Returns: {"success": bool, "reason": str, "order_result": ...}
    """
    from engine.gate import execute_order
    riskguard = RiskGuard(user_id)
    risk_check = await riskguard.check_order(order)
    if not risk_check["allowed"]:
        await _record_audit(user_id, "leg_control_blocked", f"strategy/{strategy_id}", {
            "leg_source": source,
            "reason": risk_check.get("reason", ""),
            "symbol": order.symbol,
            "side": str(order.side.value) if hasattr(order.side, "value") else str(order.side),
            "quantity": order.quantity,
        })
        logger.warning("Leg control blocked by RiskGuard: %s", risk_check["reason"])
        return {"success": False, "reason": risk_check["reason"]}
    try:
        result = await execute_order(user_id, order, source=source)
        return {"success": result.success, "reason": result.message, "order_result": result}
    except Exception as e:
        logger.exception("Leg control order failed: %s", e)
        return {"success": False, "reason": str(e)}

async def handle_trailing_sl(
    user_id: str,
    strategy_id: str,
    leg: UserStrategyLeg,
    entry_price: float,
    current_price: float,
    side: str,
    symbol: str,
    quantity: int,
) -> dict | None:
    """Evaluate and execute trailing stop-loss for one leg.

    Returns: {"action": "trailed" | "triggered" | "none", "details": ...}
    """
    caps = await resolve_capabilities_by_id(user_id)
    if not caps.trailing_sl_allowed:
        return {"action": "none", "details": "trailing_sl_not_in_plan"}
    _, current_stop, is_active = await compute_trailing_stop(leg, entry_price, current_price, side)
    if current_stop is None:
        return {"action": "none", "details": "no_trailing_sl"}

    if not is_active:
        return {"action": "none", "details": "not_activated"}

    triggered = await check_trailing_sl_trigger(leg, entry_price, current_stop, current_price, side)
    if triggered:
        order = build_square_off_order(strategy_id, user_id, symbol, side, quantity, leg.leg_order, reason="trailing_sl")
        result = await execute_leg_control(user_id, strategy_id, order, "trailing_sl")
        await _record_audit(user_id, "trailing_sl_hit", f"strategy/{strategy_id}", {
            "leg_order": leg.leg_order,
            "entry_price": entry_price,
            "stop_price": current_stop,
            "current_price": current_price,
            "symbol": symbol,
            "side": side,
        })
        return {"action": "triggered", "details": {"stop_price": current_stop, "order_result": result}}
    return {"action": "trailed", "details": {"current_stop": current_stop}}

async def handle_square_off(
    user_id: str,
    strategy_id: str,
    legs: list[dict],
    exit_time: str,
) -> list[dict]:
    """Square off all open legs at exit_time. Called from the server runner."""
    results = []
    for leg_info in legs:
        leg_order = leg_info.get("leg_order")
        if await _is_squared_off(user_id, strategy_id, leg_order):
            continue
        order = build_square_off_order(
            strategy_id, user_id,
            leg_info.get("symbol", ""),
            leg_info.get("side", "buy"),
            leg_info.get("quantity", 0),
            leg_order,
            reason="time_square_off",
        )
        result = await execute_leg_control(user_id, strategy_id, order, "time_square_off")
        await _mark_squared_off(user_id, strategy_id, leg_order)
        await _record_audit(user_id, "time_square_off", f"strategy/{strategy_id}", {
            "leg_order": leg_order,
            "symbol": leg_info.get("symbol"),
            "side": leg_info.get("side"),
            "result": "success" if result["success"] else "failed",
        })
        results.append({"leg_order": leg_order, "result": result})
    return results

async def handle_reentry(
    user_id: str,
    strategy_id: str,
    leg: UserStrategyLeg,
    reentry_mode: str,
    entry_price: float,
    current_price: float,
    side: str,
    symbol: str,
    quantity: int,
    max_reentries: int = MAX_REENTRIES,
) -> dict | None:
    """Check and execute re-entry for a leg after SL hit.

    Returns: {"action": "re_entered" | "skipped" | "blocked", ...}
    """
    caps = await resolve_capabilities_by_id(user_id)
    if not caps.reentry_squareoff_allowed:
        return {"action": "blocked", "details": "reentry_not_in_plan"}
    reentry_count = await _get_reentry_count(user_id, strategy_id, leg.leg_order)
    if reentry_count >= max_reentries:
        return {"action": "skipped", "details": "max_reentries_reached"}
    if reentry_count >= MAX_REENTRIES:
        return {"action": "skipped", "details": "hard_cap_reached"}

    should_reenter = False
    if reentry_mode == ReentryMode.RE_ASAP:
        should_reenter = True
    elif reentry_mode == ReentryMode.RE_COST:
        side_is_long = side.lower() == "buy"
        if side_is_long and current_price <= entry_price:
            should_reenter = True
        if not side_is_long and current_price >= entry_price:
            should_reenter = True
    else:
        return {"action": "skipped", "details": "unknown_mode"}

    if not should_reenter:
        return {"action": "skipped", "details": "condition_not_met"}

    order = NormalizedOrder(
        symbol=symbol,
        exchange="NFO",
        side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
        order_type=OrderType.MARKET,
        product=ProductType.INTRADAY,
        quantity=quantity,
        price=0.0,
        strategy_id=strategy_id,
        user_id=user_id,
        source="re_entry",
        is_paper=False,
    )
    result = await execute_leg_control(user_id, strategy_id, order, "re_entry")
    new_count = reentry_count + 1
    await _set_reentry_count(user_id, strategy_id, leg.leg_order, new_count)
    await _record_audit(user_id, "re_entry", f"strategy/{strategy_id}", {
        "leg_order": leg.leg_order,
        "reentry_count": new_count,
        "mode": reentry_mode,
        "symbol": symbol,
        "side": side,
        "result": "success" if result["success"] else "failed",
    })
    return {"action": "re_entered", "details": {"count": new_count, "order_result": result}}

async def cancel_pending_reentries(user_id: str, strategy_id: str, reason: str = ""):
    """Cancel all pending re-entries for a strategy (e.g., on kill switch)."""
    for leg_order in range(1, 7):
        key = REENTRY_STATE_KEY.format(user_id=user_id, strategy_id=strategy_id, leg_order=leg_order)
        await cache.delete(key)
        sq_key = SQUARED_OFF_KEY.format(user_id=user_id, strategy_id=strategy_id, leg_order=leg_order)
        await cache.delete(sq_key)
    await _record_audit(user_id, "reentries_cancelled", f"strategy/{strategy_id}", {"reason": reason})
    logger.warning("Pending re-entries cancelled for strategy=%s reason=%s", strategy_id, reason)
