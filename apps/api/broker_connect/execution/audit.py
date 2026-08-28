"""
Audit writer — ALIGNED to your existing `audit_log` table (671 rows already).

We do NOT create broker_order_audit. Every fan-out attempt is written into
audit_log with action='algo_execute'. algo_id (SEBI) rides in details jsonb
until/unless you add a dedicated column.
"""

from __future__ import annotations

from functools import lru_cache

from supabase import create_client, Client

from ..config import get_settings
from .models import Signal, OrderIntent, ExecutionResult

TABLE = "audit_log"


@lru_cache(maxsize=1)
def _sb() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_key)


def write(
    signal: Signal,
    subscriber_broker: str,
    broker_user_id: str | None,
    result: ExecutionResult,
    intent: OrderIntent | None = None,
) -> None:
    row = {
        "user_id": result.user_id,
        "action": "algo_execute",
        "source": "execution_engine",
        "broker": subscriber_broker,
        "symbol": intent.broker_symbol if intent else signal.symbol,
        "side": (intent.side.value if intent else signal.side.value),
        "quantity": result.qty or (intent.qty if intent else 0),
        "signal_id": signal.signal_id,
        "strategy_id": signal.strategy_id,
        "broker_order_id": result.broker_order_id,
        "status": result.status.value,
        "reason": result.reason,
        # everything without a dedicated column goes here
        "details": {
            "algo_id": signal.algo_id,           # SEBI traceability
            "broker_user_id": broker_user_id,
            "order_type": (intent.order_type.value if intent else signal.order_type.value),
            "product": (intent.product.value if intent else signal.product.value),
        },
    }
    try:
        _sb().table(TABLE).insert(row).execute()
    except Exception:
        pass  # audit must never break execution
