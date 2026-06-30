import hashlib
import logging
import time
from datetime import UTC, datetime

from brokers import get_broker
from brokers.token_manager import TokenManager
from core.db import get_supabase
from core.models import NormalizedOrder, OrderResult, OrderStatus
from core.safe_query import safe_execute, safe_single
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


def _write_audit(
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
        supabase.table("audit_log").insert({
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
        }).execute()
    except Exception:
        logger.exception("Failed to write audit log for user=%s", user_id)


def _log_order(user_id: str, order: NormalizedOrder) -> None:
    try:
        supabase = get_supabase()
        data = order.model_dump(mode="json")
        for field in ("id", "run_id", "validity", "disclosed_quantity", "is_paper"):
            if field in data and not data[field]:
                del data[field]
        # strategy_id is a string label in NormalizedOrder but UUID in the DB — omit it
        data.pop("strategy_id", None)
        supabase.table("orders").insert(data).execute()
    except Exception as e:
        logger.error("Failed to log order: %s", e)


async def _resolve_broker(user_id: str) -> str | None:
    supabase = get_supabase()
    creds = safe_single(
        supabase.table("broker_credentials")
        .select("broker")
        .eq("user_id", user_id)
        .eq("is_active", True)
    )
    return creds["broker"] if creds else None


async def get_mirror_recipients(strategy_key: str) -> list[dict]:
    supabase = get_supabase()
    rows = safe_execute(
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


def scaled_qty(
    user_id: str,
    base_qty: int,
    price: float = 0.0,
    reference_capital: float = 0.0,
    lot_multiplier: float = 1.0,
) -> int:
    settings = safe_single(
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

    existing = safe_single(
        get_supabase().table("orders")
        .select("*")
        .eq("user_id", user_id)
        .eq("client_order_id", order.client_order_id)
    )
    if existing:
        _write_audit(user_id, "duplicate", order, source=source, reason="DUPLICATE_ORDER")
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
        reason_text = risk_check["reason"]

        if "live" in reason_text.lower():
            return await _paper_execute(user_id, order, source=source)

        reason_code = _classify_rejection(reason_text)
        order.status = OrderStatus.REJECTED
        order.message = reason_code
        _log_order(user_id, order)
        _write_audit(user_id, "rejected", order, source=source, reason=reason_code)
        return OrderResult(success=False, message=reason_code, status="rejected")

    settings = await riskguard._load_settings(order.strategy_id)
    if not settings or not settings.is_live:
        return await _paper_execute(user_id, order, source=source)

    broker = await _resolve_broker(user_id)
    if not broker:
        order.status = OrderStatus.REJECTED
        order.message = "NO_ACTIVE_BROKER"
        _log_order(user_id, order)
        _write_audit(user_id, "rejected", order, source=source, reason="NO_ACTIVE_BROKER")
        return OrderResult(success=False, message="No active broker configured", status="rejected")

    order.broker = broker

    broker_symbol = await symbol_master.resolve_symbol(order.symbol, broker)
    order.symbol = broker_symbol or order.symbol

    token_mgr = TokenManager(user_id, broker)
    session = await token_mgr.get_session()
    adapter_cls = get_broker(broker)
    adapter = adapter_cls()
    await adapter.authenticate(session)

    order.sent_at = datetime.now(UTC)
    send_start = time.monotonic()

    try:
        result = await adapter.place_order(order)
    finally:
        await adapter.disconnect()

    send_end = time.monotonic()
    order.latency_ms = round((send_end - send_start) * 1000, 2)

    if result.success and result.broker_order_id:
        order.broker_order_id = result.broker_order_id
        order.status = OrderStatus.OPEN
        order.filled_at = datetime.now(UTC)
        order.message = "Order placed successfully"
    else:
        order.status = OrderStatus.REJECTED
        order.message = result.message or "PLACEMENT_FAILED"

    order.is_paper = False
    _log_order(user_id, order)
    _write_audit(
        user_id,
        "placed" if result.success else "failed",
        order,
        source=source,
        reason="" if result.success else (result.message or "PLACEMENT_FAILED"),
        broker=broker,
    )
    result.status = "placed" if result.success else "rejected"
    return result


async def _paper_execute(user_id: str, order: NormalizedOrder, *, source: str) -> OrderResult:
    order.is_paper = True
    order.status = OrderStatus.FILLED
    order.broker_order_id = f"paper_{order.client_order_id[:16]}"
    order.filled_at = datetime.now(UTC)
    order.average_price = order.price or 0.0
    order.filled_quantity = order.quantity
    order.total_value = order.quantity * (order.price or 0.0)
    order.message = "Paper trade simulated"

    broker = await _resolve_broker(user_id)
    order.broker = broker or "paper"

    _log_order(user_id, order)
    _write_audit(user_id, "paper", order, source=source, reason="PAPER_MODE", broker=order.broker)
    return OrderResult(
        success=True,
        broker_order_id=order.broker_order_id,
        order=order,
        message="Paper trade simulated",
        status="paper",
    )
