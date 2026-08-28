"""
OrderStore — the engine↔OMS bridge.

Writes every real order attempt (placed / rejected) into your existing `orders`
table, using YOUR vocab (MARKET/LIMIT/SL, INTRADAY/NRML, FILLED/REJECTED). This
closes the gap where orders had signal_id = NULL and no fan-out source.

Traceability:
  - source          = 'mirror_engine'   (distinguishes fan-out from admin/manual)
  - client_order_id = "{signal_id}:{user_id}"  (links order back to the signal +
                       doubles as an idempotency key)
  - signal_id       = set only when the engine's signal_id is a real UUID (your
                       orders.signal_id is a uuid FK); else NULL and preserved in
                       client_order_id / message.
  - message         = "strategy={strategy_key} algo={algo_id}"

Skips (no_conn / expired / killed / sized_zero / risk_blocked) are NOT written
here — they live in audit_log. This table stays = actual order attempts.
"""

from __future__ import annotations

import uuid as _uuid
from functools import lru_cache

from supabase import create_client, Client

from ..config import get_settings
from .models import Signal, OrderIntent, ExecutionResult, ResultStatus, Mode, OrderType, Product, Segment

TABLE = "orders"

# --- map engine enums -> your existing orders vocab ------------------------
_OTYPE = {
    OrderType.MKT: "MARKET",
    OrderType.LMT: "LIMIT",
    OrderType.SL: "SL",
    OrderType.SL_M: "SL",       # your table shows 'SL'; change to 'SL-M' if your OMS uses it
}
_PROD = {
    Product.INTRADAY: "INTRADAY",
    Product.MARGIN: "NRML",     # your table uses NRML
    Product.CNC: "CNC",
}
_INSTR = {
    Segment.INDEX: "OPTION",
    Segment.EQUITY: "EQUITY",
    Segment.COMMODITY: "FUTURE",
    Segment.CURRENCY: "FUTURE",
    Segment.CRYPTO: "SPOT",
}


def _is_uuid(v: str | None) -> bool:
    if not v:
        return False
    try:
        _uuid.UUID(str(v))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _order_status(result: ExecutionResult, mode: Mode) -> str:
    if result.status == ResultStatus.PLACED:
        # paper fills instantly; live is accepted and awaits fill
        return "FILLED" if mode == Mode.PAPER else "PLACED"
    if result.status == ResultStatus.REJECTED:
        return "REJECTED"
    return result.status.value.upper()


@lru_cache(maxsize=1)
def _sb() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_key)


class SupabaseOrderStore:
    def record(self, signal: Signal, intent: OrderIntent, result: ExecutionResult, mode: Mode) -> None:
        om = signal.option_meta or {}
        row = {
            "user_id": intent.user_id,
            "broker": intent.broker,
            "broker_order_id": result.broker_order_id,
            "symbol": intent.broker_symbol,
            "exchange": signal.exchange,
            "side": intent.side.value,                       # BUY / SELL
            "order_type": _OTYPE.get(intent.order_type, "MARKET"),
            "product": _PROD.get(intent.product, "INTRADAY"),
            "quantity": intent.qty,
            "price": intent.limit_price or intent.est_price or None,
            "trigger_price": intent.trigger_price,
            "status": _order_status(result, mode),           # NOT NULL
            "is_paper": (mode == Mode.PAPER),
            "source": "mirror_engine",
            "client_order_id": f"{signal.signal_id}:{intent.user_id}",
            "message": f"strategy={signal.strategy_id} algo={signal.algo_id or '-'}",
            "reason": result.reason,
            "instrument_type": _INSTR.get(signal.segment),
            "strike_price": om.get("strike"),
            "option_type": om.get("opt_type"),
            "expiry_date": om.get("expiry"),
        }
        # signal_id / strategy_id are uuid FKs — only set if we truly have a uuid
        if _is_uuid(signal.signal_id):
            row["signal_id"] = signal.signal_id

        try:
            _sb().table(TABLE).insert(row).execute()
        except Exception:
            pass  # order-row write must never break the batch; audit_log still has it
