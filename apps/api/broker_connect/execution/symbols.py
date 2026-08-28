"""
Symbol + lot-size resolver — ALIGNED to your existing `symbol_master` table
(symbol, exchange, broker, broker_symbol, lot_size, segment, strike, option_type,
expiry, token). No more hardcoded formatting — this is your single source of truth.

Returns (broker_symbol, lot_size). Falls back to the canonical symbol if a row
isn't found (and logs — a miss usually means symbol_master needs refreshing).
"""

from __future__ import annotations

from functools import lru_cache

from supabase import create_client, Client

from ..config import get_settings
from .models import Signal, Segment


@lru_cache(maxsize=1)
def _sb() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_key)


def resolve(broker: str, signal: Signal) -> tuple[str, int]:
    q = (
        _sb()
        .table("symbol_master")
        .select("broker_symbol, lot_size")
        .eq("broker", broker)
        .eq("symbol", signal.symbol)
    )
    if signal.exchange:
        q = q.eq("exchange", signal.exchange)
    # narrow options for INDEX/derivative strategies
    if signal.option_meta:
        m = signal.option_meta
        if m.get("strike") is not None:
            q = q.eq("strike", m["strike"])
        if m.get("opt_type"):
            q = q.eq("option_type", m["opt_type"])

    res = q.limit(1).execute()
    if res.data:
        r = res.data[0]
        return r["broker_symbol"], int(r.get("lot_size") or signal.lot_size or 1)

    # fallback — keep trading readable; flag for a symbol_master refresh
    print(f"[symbols] MISS broker={broker} symbol={signal.symbol} — using canonical")
    return f"{signal.exchange or 'NSE'}:{signal.symbol}", (signal.lot_size or 1)


def to_broker_symbol(broker: str, signal: Signal) -> str:
    """Back-compat helper used by the engine — returns just the symbol string."""
    sym, _ = resolve(broker, signal)
    return sym
