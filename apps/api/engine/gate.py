import hashlib
import logging
import time
from datetime import UTC, datetime

from core.db import async_supabase, get_supabase
from core.models import NormalizedOrder, OrderResult, OrderStatus
from core.safe_query import async_safe_execute, async_safe_single, safe_execute, safe_single
from execution.broker_adapter import BrokerExecutionAdapter
from execution.models import ExecutionRequest
from market.symbol_master import symbol_master
from risk.riskguard import RiskGuard

logger = logging.getLogger(__name__)


def generate_client_order_id(
    user_id: str,
    symbol: str,
    side: str,
    *,
    source: str = "manual",
    strategy_id: str | None = None,
    signal_id: str | None = None,
) -> str:
    if source == "mirror" or signal_id:
        if signal_id:
            return hashlib.sha256(f"{user_id}:{signal_id}".encode()).hexdigest()[:32]
        return hashlib.sha256(f"{user_id}:{strategy_id or ''}:{symbol}:{side}".encode()).hexdigest()[:32]
    return hashlib.sha256(f"{user_id}:{symbol}:{side}:{int(time.time())}".encode()).hexdigest()[:32]


def _classify_rejection(reason: str) -> str:
    r = reason.lower()
    if "kill switch" in r:
        return "KILL_SWITCH"
    if "daily loss" in r:
        return "DAILY_LOSS_CAP"
    if "max position size" in r:
        return "MAX_POSITION_SIZE"
    if "max capital" in r:
        return "MAX_CAPITAL"
    if "drawdown" in r:
        return "MAX_DRAWDOWN"
    if "open positions" in r:
        return "MAX_OPEN_POSITIONS"
    return "RISK_REJECTED"


async def _write_audit(
    user_id: str,
    action: str,
    order: NormalizedOrder,
    *,
    source: str = "manual",
    reason: str = "",
    broker: str = "",
):
    try:
        supabase = get_supabase()
        await async_supabase(lambda: supabase.table("audit_log").insert({
            "user_id": user_id,
            "action": action,
            "resource": "order",
            "source": source,
            "client_order_id": order.client_order_id or "",
            "reason": reason,
            "broker": broker or order.broker or "",
            "symbol": order.symbol,
            "side": order.side.value if order.side else "",
            "quantity": order.quantity,
            "intended_price": order.price or 0.0,
            "signal_id": "",
            "strategy_id": order.strategy_id or "",
            "details": {
                "price": order.price,
                "trigger_price": order.trigger_price,
                "order_type": order.order_type.value if order.order_type else "",
                "product": order.product.value if order.product else "",
                "instrument_type": order.instrument_type.value if order.instrument_type else "",
            },
        }).execute())
    except Exception:
        logger.exception("Failed to write audit log for user=%s", user_id)


async def _log_order(user_id: str, order: NormalizedOrder) -> None:
    try:
        supabase = get_supabase()
        data = order.model_dump(mode="json")
        for field in ("id", "run_id", "validity", "disclosed_quantity"):
            if field in data and not data[field]:
                del data[field]
        data.pop("strategy_id", None)
        await async_supabase(lambda: supabase.table("orders").insert(data).execute())
    except Exception as e:
        logger.error("Failed to log order: %s", e)


async def _resolve_broker(user_id: str) -> str | None:
    supabase = get_supabase()
    creds = await async_safe_single(
        supabase.table("broker_credentials")
        .select("broker")
        .eq("user_id", user_id)
        .eq("is_active", True)
    )
    return creds["broker"] if creds else None


def _normalized_to_execution_request(user_id: str, order: NormalizedOrder, broker: str, source: str) -> ExecutionRequest:
    return ExecutionRequest(
        user_id=user_id,
        broker=broker,
        symbol=order.symbol,
        exchange=order.exchange.value if hasattr(order.exchange, "value") else "NSE",
        side=order.side.value if hasattr(order.side, "value") else "",
        order_type=order.order_type.value if hasattr(order.order_type, "value") else "MARKET",
        product=order.product.value if hasattr(order.product, "value") else "INTRADAY",
        quantity=order.quantity,
        price=order.price or 0.0,
        trigger_price=order.trigger_price,
        disclosed_quantity=order.disclosed_quantity,
        validity=order.validity,
        instrument_type=order.instrument_type.value if hasattr(order.instrument_type, "value") else "EQ",
        strike_price=order.strike_price,
        expiry_date=order.expiry_date,
        option_type=order.option_type.value if order.option_type and hasattr(order.option_type, "value") else None,
        strategy_id=order.strategy_id,
        source=source,
        execution_request_id=order.client_order_id or "",
    )


def _execution_result_to_order_result(exec_result, order: NormalizedOrder) -> OrderResult:
    return OrderResult(
        success=exec_result.success,
        broker_order_id=exec_result.broker_order_id or "",
        order=order,
        message=exec_result.message,
        status=exec_result.state.value if hasattr(exec_result.state, "value") else "",
        filled_qty=order.filled_quantity if exec_result.success else 0,
        avg_price=order.average_price if exec_result.success else 0.0,
    )


async def get_mirror_recipients(strategy_key: str) -> list[dict]:
    supabase = get_supabase()
    rows = await async_safe_execute(
        supabase.table("strategy_assignments")
        .select("user_id, profiles!user_id(email, full_name)")
        .eq("strategy_key", strategy_key)
        .eq("active", True)
        .eq("mirror_enabled", True)
    ) or []
    result = []
    for r in rows:
        profile = r.get("profiles") or {}
        result.append({
            "user_id": r["user_id"],
            "email": profile.get("email", ""),
            "full_name": profile.get("full_name", ""),
        })
    return result


async def scaled_qty(
    user_id: str,
    base_qty: int,
    price: float = 0.0,
    reference_capital: float = 0.0,
    lot_multiplier: float = 1.0,
) -> int:
    settings = await async_safe_single(
        get_supabase().table("risk_settings")
        .select("max_capital, max_position_size")
        .eq("user_id", user_id)
    )
    if not settings:
        return base_qty

    max_capital = settings.get("max_capital", 0.0)
    max_position_size = settings.get("max_position_size", 0.0)

    scaled = int(base_qty * lot_multiplier)

    if reference_capital > 0 and max_capital > 0:
        ratio = max_capital / reference_capital
        scaled = int(scaled * ratio)

    if max_position_size > 0 and price > 0:
        max_qty = int(max_position_size / price)
        scaled = min(scaled, max_qty)

    return max(scaled, 1)


async def execute_order(
    user_id: str,
    order: NormalizedOrder,
    *,
    source: str = "manual",
) -> OrderResult:
    from execution import execution_manager

    order.user_id = user_id
    order.source = source

    if not order.client_order_id:
        order.client_order_id = generate_client_order_id(
            user_id,
            order.symbol,
            order.side.value if order.side else "",
            source=source,
            strategy_id=order.strategy_id,
        )

    existing = await async_safe_single(
        get_supabase().table("orders")
        .select("*")
        .eq("user_id", user_id)
        .eq("client_order_id", order.client_order_id)
    )
    if existing:
        await _write_audit(user_id, "duplicate", order, source=source, reason="DUPLICATE_ORDER")
        return OrderResult(
            success=True,
            broker_order_id=existing.get("broker_order_id", ""),
            message="DUPLICATE_ORDER",
            status="duplicate",
        )

    order.signal_at = datetime.now(UTC)

    riskguard = RiskGuard(user_id)
    risk_check = await riskguard.check_order(order)
    order.risk_checked_at = datetime.now(UTC)

    if not risk_check["allowed"]:
        reason_code = _classify_rejection(risk_check.get("reason", ""))
        order.status = OrderStatus.REJECTED
        order.message = reason_code
        await _log_order(user_id, order)
        await _write_audit(user_id, "rejected", order, source=source, reason=reason_code)
        return OrderResult(success=False, message=reason_code, status="rejected")

    if order.is_paper:
        order.broker = "paper"
    else:
        settings = await riskguard._load_settings(order.strategy_id)
        is_live = bool(settings and settings.is_live)
        if is_live:
            broker = await _resolve_broker(user_id)
            if not broker:
                order.status = OrderStatus.REJECTED
                order.message = "NO_ACTIVE_BROKER"
                await _log_order(user_id, order)
                await _write_audit(user_id, "rejected", order, source=source, reason="NO_ACTIVE_BROKER")
                return OrderResult(success=False, message="No active broker configured", status="rejected")
            order.broker = broker
            broker_symbol = await symbol_master.resolve_symbol(order.symbol, broker)
            order.symbol = broker_symbol or order.symbol
        else:
            order.broker = "paper"
            order.is_paper = True

    req = _normalized_to_execution_request(user_id, order, order.broker, source)
    exec_result = await execution_manager.place_order(req)

    if exec_result.success:
        order.broker_order_id = exec_result.broker_order_id
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.now(UTC)
        order.message = exec_result.message or "Order placed successfully"
        if order.is_paper:
            order.average_price = order.price or 0.0
            order.filled_quantity = order.quantity
            order.total_value = order.quantity * (order.price or 0.0)
    else:
        order.status = OrderStatus.REJECTED
        order.message = exec_result.message or "PLACEMENT_FAILED"

    order.latency_ms = exec_result.latency_ms
    await _log_order(user_id, order)
    await _write_audit(
        user_id,
        "placed" if exec_result.success else "failed",
        order,
        source=source,
        reason="" if exec_result.success else (exec_result.message or "PLACEMENT_FAILED"),
        broker=order.broker,
    )
    return _execution_result_to_order_result(exec_result, order)
