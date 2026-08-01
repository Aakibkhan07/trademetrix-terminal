import asyncio
import hashlib
import logging
import re
import time
from datetime import UTC, datetime, date

from core.constants import STRIKE_INTERVALS
from core.db import async_supabase, get_supabase
from core.models import NormalizedOrder, OptionType, OrderResult, OrderStatus
from core.safe_query import async_safe_execute, async_safe_single
from execution.models import ExecutionRequest
from market.symbol_master import symbol_master
from risk.riskguard import RiskGuard

logger = logging.getLogger(__name__)

_OPTION_SYMBOL_RE = re.compile(r"^(.*?)(\d{2})([A-Z]{3})(\d{2})(\d+)(CE|PE)$")
_MONTH_NUM = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

_order_locks: dict[str, asyncio.Lock] = {}
_order_lock_lock = asyncio.Lock()


async def _get_order_lock(client_order_id: str) -> asyncio.Lock:
    async with _order_lock_lock:
        if client_order_id not in _order_locks:
            _order_locks[client_order_id] = asyncio.Lock()
        return _order_locks[client_order_id]


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
    return hashlib.sha256(f"{user_id}:{symbol}:{side}:{time.time_ns()}".encode()).hexdigest()[:32]


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
    return creds.get("broker") if creds else None


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
        is_paper=order.is_paper,
    )


def _oms_to_order_result(oms_order, order: NormalizedOrder) -> OrderResult:
    success = oms_order.state.value in ("FILLED", "PARTIAL", "PENDING")
    return OrderResult(
        success=success,
        broker_order_id=oms_order.broker_order_id or "",
        order=order,
        message=oms_order.message,
        status=oms_order.state.value.lower(),
        filled_qty=order.filled_quantity if success else 0,
        avg_price=order.average_price if success else 0.0,
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
        .is_("strategy_id", "null")
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


def _parse_option_symbol(symbol: str) -> tuple[str, date, float, str] | None:
    """Parse 'NSE:NIFTY26AUG25000CE' → (underlying, expiry, strike, option_type)."""
    m = _OPTION_SYMBOL_RE.match(symbol)
    if not m:
        return None
    underlying, dd, mon, yy, strike, opt_type = m.groups()
    try:
        expiry = date(int("20" + yy), _MONTH_NUM[mon], int(dd))
        return underlying, expiry, float(strike), opt_type
    except Exception:
        return None


async def _snap_to_itm_strike(user_id: str, order: NormalizedOrder) -> bool:
    """Rewrite an option order to the nearest in-the-money strike.

    CE → nearest strike at or below spot; PE → nearest strike at or above spot.
    Only applies to user-facing engine trades (source != 'strategy').
    Returns True when the symbol was rewritten.
    """
    if not order.symbol or not order.strike_price:
        return False
    parsed = _parse_option_symbol(order.symbol)
    if not parsed:
        return False
    underlying, expiry, cur_strike, opt_type = parsed
    if order.option_type not in (OptionType.CE, OptionType.PE):
        return False

    try:
        from brokers.token_manager import TokenManager
        from brokers.fyers_adapter import FyersAdapter
        from core.constants import MONTH_CODES

        session = await TokenManager(user_id, "fyers").get_session()
        if not session:
            return False
        adapter = FyersAdapter()
        await adapter.authenticate({
            "client_id": session.get("client_id", ""),
            "access_token": session.get("access_token", ""),
        })
        # Fyers has no index spot quotes — use the same-month index future as
        # a spot proxy (basis is a few points; plenty for strike grid snapping).
        fut_sym = f"NSE:{underlying.split(':')[-1]}{str(expiry.year)[-2:]}{MONTH_CODES[expiry.month]}FUT"
        quotes = await adapter.get_quotes([fut_sym])
        if not quotes or getattr(quotes[0], "last_price", 0) <= 0:
            logger.warning("ITM snap skipped for %s: no future quote (%s)", order.symbol, fut_sym)
            return False
        spot = quotes[0].last_price
    except Exception as e:
        logger.warning("ITM snap skipped for %s: %s", order.symbol, e)
        return False

    interval = STRIKE_INTERVALS.get(underlying.split(":")[-1].upper(), 50)
    if opt_type == "CE":
        itm_strike = int(spot // interval) * interval
    else:
        itm_strike = -(-int(spot) // interval) * interval
    if itm_strike <= 0 or int(itm_strike) == int(cur_strike):
        return False

    from core.constants import format_fyers_option_symbol

    new_symbol = format_fyers_option_symbol(underlying.split(":")[-1], itm_strike, opt_type, expiry)
    logger.info(
        "ITM snap: %s (spot %.2f, strike %.0f) → %s",
        order.symbol, spot, cur_strike, new_symbol,
    )
    order.symbol = new_symbol
    order.strike_price = float(itm_strike)
    order.expiry_date = expiry.isoformat()
    return True


async def execute_order(
    user_id: str,
    order: NormalizedOrder,
    *,
    source: str = "manual",
    idempotency_key: str | None = None,
) -> OrderResult:
    order.user_id = user_id
    order.source = source

    if idempotency_key:
        order.client_order_id = idempotency_key
    elif not order.client_order_id:
        order.client_order_id = generate_client_order_id(
            user_id,
            order.symbol,
            order.side.value if order.side else "",
            source=source,
            strategy_id=order.strategy_id,
        )

    lock = await _get_order_lock(order.client_order_id)
    async with lock:
        try:
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

            if order.is_paper:
                broker = "paper"
            else:
                broker = await _resolve_broker(user_id)
                if not broker:
                    order.status = OrderStatus.REJECTED
                    order.message = "NO_ACTIVE_BROKER"
                    await _write_audit(user_id, "rejected", order, source=source, reason="NO_ACTIVE_BROKER")
                    return OrderResult(success=False, message="No active broker configured. Connect a broker first.", status="rejected")
            order.broker = broker
            order.is_paper = order.is_paper or broker == "paper"

            if source != "strategy" and order.option_type:
                await _snap_to_itm_strike(user_id, order)

            riskguard = RiskGuard(user_id)
            risk_check = await riskguard.check_order(order)
            order.risk_checked_at = datetime.now(UTC)

            if not risk_check:
                reason_code = "RISK_CHECK_FAILED"
                order.status = OrderStatus.REJECTED
                order.message = reason_code
                await _write_audit(user_id, "rejected", order, source=source, reason=reason_code)
                return OrderResult(success=False, message=reason_code, status="rejected")

            if not risk_check.get("allowed"):
                reason_code = _classify_rejection(risk_check.get("reason", ""))
                order.status = OrderStatus.REJECTED
                order.message = reason_code
                await _write_audit(user_id, "rejected", order, source=source, reason=reason_code)
                return OrderResult(success=False, message=reason_code, status="rejected")

            broker_symbol = await symbol_master.resolve_symbol(order.symbol, broker)
            order.symbol = broker_symbol or order.symbol

            req = _normalized_to_execution_request(user_id, order, order.broker, source)
            from oms.manager import order_manager
            from oms.models import OMSOrderState

            try:
                oms_order = await order_manager.place_and_wait(req, timeout=20.0)
            except Exception as e:
                logger.error("place_and_wait raised for user=%s broker=%s: %s", user_id, order.broker, e)
                order.status = OrderStatus.REJECTED
                order.message = f"EXECUTION_ERROR: {e}"
                return OrderResult(success=False, message=str(e), status="error")

            success = oms_order.state in (
                OMSOrderState.FILLED, OMSOrderState.PARTIAL, OMSOrderState.PENDING,
            )
            order.broker_order_id = oms_order.broker_order_id or ""
            order.filled_quantity = oms_order.filled_quantity or 0
            order.average_price = oms_order.average_price or 0.0
            order.latency_ms = oms_order.latency_ms or 0.0
            if success:
                if oms_order.state == OMSOrderState.FILLED:
                    order.status = OrderStatus.FILLED
                    order.filled_at = oms_order.filled_at or datetime.now(UTC)
                elif oms_order.state == OMSOrderState.PARTIAL:
                    order.status = OrderStatus.PARTIALLY_FILLED
                    order.filled_at = oms_order.filled_at or datetime.now(UTC)
                else:
                    order.status = OrderStatus.PENDING
                order.message = oms_order.message or "Order placed successfully"
            else:
                order.status = OrderStatus.REJECTED
                order.message = oms_order.message or "PLACEMENT_FAILED"

            await _write_audit(
                user_id,
                "placed" if success else "failed",
                order,
                source=source,
                reason="" if success else (oms_order.message or "PLACEMENT_FAILED"),
                broker=order.broker,
            )
        finally:
            _order_locks.pop(order.client_order_id, None)
    return _oms_to_order_result(oms_order, order)
