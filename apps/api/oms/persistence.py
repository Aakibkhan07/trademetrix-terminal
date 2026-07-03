"""
OMS State Persistence

Stores active OmniOrder state in the `oms_orders` table so it survives restarts.
Recovers active orders on startup. Gracefully handles missing tables.

Expected schema (run in Supabase SQL Editor):
    CREATE TABLE public.oms_orders (
        oms_order_id TEXT PRIMARY KEY,
        -- all OmniOrder fields from model_dump(mode="json")
        state TEXT NOT NULL DEFAULT 'NEW',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE public.oms_bracket_orders (
        oms_order_id TEXT PRIMARY KEY,
        parent_order_id TEXT NOT NULL,
        active BOOLEAN DEFAULT TRUE
    );
    CREATE TABLE public.oms_oco_orders (
        oms_order_id TEXT PRIMARY KEY,
        active BOOLEAN DEFAULT TRUE
    );

Rollback: Delete this file and reset oms/manager.py to previous version.
"""

import logging
from typing import Any

from core.db import async_supabase, get_supabase
from core.safe_query import async_safe_execute, safe_execute

logger = logging.getLogger(__name__)

TABLE = "oms_orders"
BRACKET_TABLE = "oms_bracket_orders"
OCO_TABLE = "oms_oco_orders"


async def save_order(order) -> None:
    """Persist OmniOrder to DB (upsert by oms_order_id)."""
    try:
        data = order.model_dump(mode="json")
        supabase = get_supabase()
        await async_supabase(lambda: supabase.table(TABLE).upsert(data, on_conflict=["oms_order_id"]).execute())
    except Exception as e:
        logger.warning("Failed to persist OMS order %s: %s", order.oms_order_id, e)


async def remove_order(oms_order_id: str) -> None:
    """Remove persisted order (order completed/cancelled)."""
    try:
        supabase = get_supabase()
        await async_supabase(lambda: supabase.table(TABLE).delete().eq("oms_order_id", oms_order_id).execute())
    except Exception as e:
        logger.warning("Failed to remove OMS order %s: %s", oms_order_id, e)


async def load_active_orders() -> list[dict[str, Any]]:
    """Load all active (non-terminal) orders from DB for recovery."""
    try:
        supabase = get_supabase()
        rows = await async_safe_execute(
            supabase.table(TABLE)
            .select("*")
            .in_("state", ["NEW", "VALIDATED", "QUEUED", "SENT", "PENDING", "PARTIAL"])
        )
        return rows or []
    except Exception as e:
        logger.warning("Failed to load active OMS orders: %s", e)
        return []


async def save_bracket_order(bracket) -> None:
    """Persist BracketOrder."""
    try:
        data = bracket.model_dump(mode="json")
        supabase = get_supabase()
        await async_supabase(lambda: supabase.table(BRACKET_TABLE).upsert(data, on_conflict=["oms_order_id"]).execute())
    except Exception as e:
        logger.warning("Failed to persist bracket order %s: %s", bracket.oms_order_id, e)


async def load_active_bracket_orders() -> list[dict[str, Any]]:
    """Load all active bracket orders."""
    try:
        supabase = get_supabase()
        rows = await async_safe_execute(
            supabase.table(BRACKET_TABLE).select("*").eq("active", True)
        )
        return rows or []
    except Exception as e:
        logger.warning("Failed to load active bracket orders: %s", e)
        return []


async def save_oco_order(oco) -> None:
    """Persist OCOOrder."""
    try:
        data = oco.model_dump(mode="json")
        supabase = get_supabase()
        await async_supabase(lambda: supabase.table(OCO_TABLE).upsert(data, on_conflict=["oms_order_id"]).execute())
    except Exception as e:
        logger.warning("Failed to persist OCO order %s: %s", oco.oms_order_id, e)


async def load_active_oco_orders() -> list[dict[str, Any]]:
    """Load all active OCO orders."""
    try:
        supabase = get_supabase()
        rows = await async_safe_execute(
            supabase.table(OCO_TABLE).select("*").eq("active", True)
        )
        return rows or []
    except Exception as e:
        logger.warning("Failed to load active OCO orders: %s", e)
        return []
