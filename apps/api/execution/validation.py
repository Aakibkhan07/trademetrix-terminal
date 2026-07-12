import logging

from core.db import get_supabase
from core.models import NormalizedOrder, OrderType
from core.safe_query import async_safe_single
from execution.broker_adapter import BrokerExecutionAdapter
from execution.models import ValidationResult
from market.status import market_status_service

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["symbol", "exchange", "side", "order_type", "product", "quantity"]
VALID_SIDES = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"MARKET", "LIMIT", "SL", "SLM"}
VALID_PRODUCTS = {"INTRADAY", "DELIVERY", "MIS", "NRML"}
VALID_EXCHANGES = {"NSE", "BSE", "NFO", "CDS", "MCX"}


async def validate_order(order: NormalizedOrder, user_id: str, adapter: BrokerExecutionAdapter | None = None) -> ValidationResult:
    errors = []
    warnings = []

    for field in REQUIRED_FIELDS:
        value = getattr(order, field, None)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append({"field": field, "message": f"{field} is required"})

    if order.side and order.side.value not in VALID_SIDES:
        errors.append({"field": "side", "message": f"Invalid side: {order.side.value}"})

    if order.order_type and order.order_type.value not in VALID_ORDER_TYPES:
        errors.append({"field": "order_type", "message": f"Invalid order type: {order.order_type.value}"})

    if order.product and order.product.value not in VALID_PRODUCTS:
        errors.append({"field": "product", "message": f"Invalid product: {order.product.value}"})

    if order.exchange and order.exchange.value not in VALID_EXCHANGES:
        errors.append({"field": "exchange", "message": f"Invalid exchange: {order.exchange.value}"})

    if order.quantity <= 0:
        errors.append({"field": "quantity", "message": "Quantity must be positive"})

    if order.order_type in (OrderType.LIMIT, OrderType.SL, OrderType.SLM) and order.price <= 0:
        errors.append({"field": "price", "message": "Price is required for LIMIT/SL/SLM orders"})

    if order.order_type == OrderType.SL and (not order.trigger_price or order.trigger_price <= 0):
        errors.append({"field": "trigger_price", "message": "Trigger price is required for SL orders"})

    if order.disclosed_quantity > order.quantity:
        errors.append({"field": "disclosed_quantity", "message": "Disclosed quantity cannot exceed total quantity"})

    if adapter:
        caps = adapter.capabilities()
        if order.product in ("MIS",) and not caps.supports_bracket:
            warnings.append(f"Broker {adapter.broker} may not support MIS products")

    session_valid = await _validate_trading_session()
    if not session_valid:
        errors.append({"field": "session", "message": "Market is closed"})

    duplicate = await _check_duplicate(user_id, order)
    if duplicate:
        errors.append({"field": "duplicate", "message": "Duplicate order detected", "existing_id": duplicate})

    margin_ok = await _check_margin(user_id, order)
    if not margin_ok:
        errors.append({"field": "margin", "message": "Insufficient margin"})

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


async def _validate_trading_session() -> bool:
    try:
        return market_status_service.is_market_open()
    except Exception:
        logger.warning("Market status check failed — blocking trade (fail-closed)")
        return False


async def _check_duplicate(user_id: str, order: NormalizedOrder) -> str | None:
    try:
        supabase = get_supabase()
        client_id = order.client_order_id or ""
        if client_id:
            existing = await async_safe_single(
                supabase.table("orders")
                .select("id")
                .eq("user_id", user_id)
                .eq("client_order_id", client_id)
            )
            if existing:
                return existing.get("id", "")
    except Exception as e:
        logger.warning("Duplicate check failed: %s", e)
    return None


async def _check_margin(user_id: str, order: NormalizedOrder) -> bool:
    try:
        supabase = get_supabase()
        margin = await async_safe_single(
            supabase.table("margin_snapshot")
            .select("available_margin")
            .eq("user_id", user_id)
            .eq("broker", order.broker)
            .limit(1)
        )
        if not margin:
            return True
        available = float(margin.get("available_margin", 0))
        order_value = order.quantity * (order.price or 0)
        return available >= order_value
    except Exception:
        logger.warning("Margin check failed — blocking trade (fail-closed)")
        return False
