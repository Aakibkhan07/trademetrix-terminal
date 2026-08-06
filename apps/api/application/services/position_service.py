"""Canonical PositionService — the single position read implementation.

Consumed by the Portfolio, Engine, Paper and Admin routers as thin adapters.
Every method reproduces the historical response envelope of its consumer
byte-for-byte (payload parity is a hard requirement):

- ``get_positions_with_broker`` → ``{"positions": [...], "broker": ...}``  (v1_portfolio)
- ``get_user_positions``        → ``{"positions": [...]}``                (v1_engine)
- ``get_paper_positions``       → ``{"positions": [...], "count": n}``    (v1_paper, open only)
- ``list_all_positions``        → ``{"positions": [...], "count": n}``    (v1_admin, cross-user)

The four data sources remain the same as before consolidation:
portfolio_manager (live broker / running paper run), execution_engine
position_manager (paper ledger), and the persisted positions_snapshot
(admin cross-user view).
"""
from __future__ import annotations

import logging

from core.db import get_supabase
from core.exceptions import BrokerTokenExpiredError
from core.resilience import CircuitBreakerError
from core.safe_query import async_safe_execute, async_safe_single
from risk.helpers import get_active_broker

logger = logging.getLogger(__name__)


class PositionService:
    # ── v1_portfolio: GET /api/v1/positions ──────────────────────────────
    async def get_positions_with_broker(self, user_id: str, broker: str | None = None) -> dict:
        resolved = broker or await get_active_broker(user_id)
        if not resolved:
            return {"positions": [], "broker": None}
        from portfolio.manager import portfolio_manager

        await portfolio_manager.refresh(user_id, resolved)
        positions = await portfolio_manager.get_positions(user_id, resolved)
        return {"positions": [p.model_dump() for p in positions], "broker": resolved}

    # ── v1_engine: GET /api/v1/engine/positions ──────────────────────────
    async def get_user_positions(self, user_id: str) -> dict:
        return {"positions": await self.get_user_positions_list(user_id)}

    async def get_user_positions_list(self, user_id: str) -> list[dict]:
        paper_run = await async_safe_single(
            get_supabase().table("strategy_runs")
            .select("mode, broker")
            .eq("user_id", user_id)
            .eq("status", "running")
            .eq("mode", "PAPER")
            .limit(1)
        )
        if paper_run:
            from portfolio.manager import portfolio_manager

            broker = paper_run.get("broker", "paper")
            try:
                await portfolio_manager.refresh(user_id, broker)
                positions = await portfolio_manager.get_positions(user_id, broker)
                return [p.model_dump() for p in positions]
            except Exception:
                return []

        broker = await get_active_broker(user_id)
        if not broker:
            return []
        try:
            from application.services.engine_service import EngineService

            engine = await EngineService().get_engine_for(user_id, broker)
            positions = await engine.get_positions()
            return [p.model_dump() for p in positions]
        except BrokerTokenExpiredError:
            raise
        except (ValueError, RuntimeError, CircuitBreakerError):
            return []

    # ── v1_paper: GET /api/v1/paper/positions ────────────────────────────
    def get_paper_positions(self, user_id: str) -> dict:
        from execution_engine import position_manager

        positions = position_manager.get_positions(user_id, broker="paper")
        positions = [p for p in positions if p.is_open]
        return {
            "positions": [p.model_dump(mode="json") for p in positions],
            "count": len(positions),
        }

    # ── v1_admin: GET /api/v1/admin/positions ────────────────────────────
    async def list_all_positions(self, user_id: str = "") -> dict:
        supabase = get_supabase()
        query = supabase.table("positions_snapshot").select("*").order("snapshot_at", desc=True)
        if user_id:
            query = query.eq("user_id", user_id)

        data = await async_safe_execute(query) or []

        seen: dict[str, dict] = {}
        for p in data:
            key = (p.get("user_id", ""), p.get("symbol", ""))
            if key not in seen:
                seen[key] = p

        user_ids = list(set(p["user_id"] for p in seen.values() if p.get("user_id")))
        profile_map = {}
        if user_ids:
            profiles = await async_safe_execute(
                supabase.table("profiles").select("id, email, full_name").in_("id", user_ids)
            ) or []
            profile_map = {p["id"]: p for p in profiles}

        positions = []
        for p in seen.values():
            prof = profile_map.get(p.get("user_id", ""), {})
            positions.append({
                "id": p.get("id", ""),
                "user_id": p.get("user_id", ""),
                "email": prof.get("email", ""),
                "full_name": prof.get("full_name", ""),
                "broker": p.get("broker", ""),
                "symbol": p.get("symbol", ""),
                "exchange": p.get("exchange", ""),
                "quantity": p.get("quantity", 0),
                "buy_quantity": p.get("buy_quantity", 0),
                "sell_quantity": p.get("sell_quantity", 0),
                "average_buy_price": p.get("average_buy_price", 0.0),
                "average_sell_price": p.get("average_sell_price", 0.0),
                "unrealised_pnl": p.get("unrealised_pnl", 0.0),
                "realised_pnl": p.get("realised_pnl", 0.0),
                "m2m": p.get("m2m", 0.0),
                "product": p.get("product", ""),
                "instrument_type": p.get("instrument_type", "EQ"),
                "strike_price": p.get("strike_price"),
                "expiry_date": p.get("expiry_date"),
                "option_type": p.get("option_type", ""),
                "snapshot_at": p.get("snapshot_at", ""),
            })

        return {"positions": positions, "count": len(positions)}


position_service = PositionService()
