"""Portfolio Engine (Execution Engine v1.0) — aggregation + persistence.

Aggregates the Position Manager + P&L Engine into a per-user portfolio
snapshot across all brokers and keeps the last snapshot in memory. Publishes
``portfolio.snapshot`` events after every rebuild so analytics/history
consumers stay in sync without polling.

The legacy ``portfolio/manager.py`` remains the broker-sync authority; this
engine is the formal event-driven aggregation layer above it. A durable store
can be attached via the ``SnapshotStore`` protocol (Supabase adapter later).
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel, Field

from execution_engine.events import (
    ExecutionDomain,
    ExecutionEngineEvent,
    ExecutionEventType,
    execution_bus,
    portfolio_event,
)
from execution_engine.positions import EnginePosition, PositionManager
from execution_engine.pnl import PnLEngine


class PortfolioSnapshot(BaseModel):
    user_id: str = ""
    brokers: list[str] = Field(default_factory=list)
    positions: list[EnginePosition] = Field(default_factory=list)
    open_positions: int = 0
    total_positions: int = 0
    realised_pnl: float = 0.0
    unrealised_pnl: float = 0.0
    daily_pnl: float = 0.0
    current_equity: float = 0.0
    peak_equity: float = 0.0
    drawdown_pct: float = 0.0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SnapshotStore(Protocol):
    """Optional durable store for portfolio snapshots."""

    async def save_snapshot(self, user_id: str, snapshot: dict[str, Any]) -> None: ...

    async def load_snapshot(self, user_id: str) -> dict[str, Any] | None: ...


class PortfolioEngine:
    def __init__(
        self,
        bus: Any | None = None,
        positions: PositionManager | None = None,
        pnl: PnLEngine | None = None,
        store: SnapshotStore | None = None,
    ) -> None:
        self._bus = bus or execution_bus
        self._positions = positions
        self._pnl = pnl
        self._store = store
        self._snapshots: dict[str, PortfolioSnapshot] = {}
        self._lock = threading.RLock()
        self._installed = False

    def install(self) -> None:
        """Idempotently subscribe to position + portfolio events."""
        with self._lock:
            if self._installed:
                return
            self._bus.subscribe(ExecutionDomain.PORTFOLIO, self._on_event)
            self._installed = True

    async def _on_event(self, event: ExecutionEngineEvent) -> None:
        if event.type == ExecutionEventType.PORTFOLIO_SNAPSHOT:
            return  # never react to our own snapshots (would self-trigger)
        if not event.user_id:
            return
        snapshot = self.rebuild(event.user_id, broker=event.broker)
        self._publish_snapshot(snapshot)

    # ------------------------------------------------------------------
    def rebuild(self, user_id: str, broker: str | None = None) -> PortfolioSnapshot:
        positions = self._positions.get_positions(user_id) if self._positions is not None else []
        if broker:
            positions = [p for p in positions if p.broker == broker]
        pnl_agg = self._pnl.aggregate(user_id) if self._pnl is not None else {}

        snapshot = PortfolioSnapshot(
            user_id=user_id,
            brokers=sorted({p.broker for p in positions}),
            positions=sorted(positions, key=lambda p: (p.broker, p.symbol)),
            open_positions=sum(1 for p in positions if p.is_open),
            total_positions=len(positions),
            realised_pnl=float(pnl_agg.get("realised_pnl", 0.0)),
            unrealised_pnl=float(pnl_agg.get("unrealised_pnl", 0.0)),
            daily_pnl=float(pnl_agg.get("daily_pnl", 0.0)),
            current_equity=float(pnl_agg.get("current_equity", 0.0)),
            peak_equity=float(pnl_agg.get("peak_equity", 0.0)),
            drawdown_pct=float(pnl_agg.get("drawdown_pct", 0.0)),
        )
        with self._lock:
            self._snapshots[user_id] = snapshot
        return snapshot

    def _publish_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        self._bus.publish(
            portfolio_event(
                ExecutionEventType.PORTFOLIO_SNAPSHOT,
                user_id=snapshot.user_id,
                message=f"Snapshot: {snapshot.open_positions} open / {snapshot.total_positions} total positions",
                payload={
                    "open_positions": snapshot.open_positions,
                    "total_positions": snapshot.total_positions,
                    "realised_pnl": snapshot.realised_pnl,
                    "unrealised_pnl": snapshot.unrealised_pnl,
                    "daily_pnl": snapshot.daily_pnl,
                    "current_equity": snapshot.current_equity,
                    "drawdown_pct": snapshot.drawdown_pct,
                    "source": "portfolio_engine",
                },
            )
        )

    # ------------------------------------------------------------------
    def snapshot(self, user_id: str) -> PortfolioSnapshot | None:
        with self._lock:
            return self._snapshots.get(user_id)

    async def persist(self, user_id: str, snapshot: PortfolioSnapshot | None = None) -> None:
        if self._store is None:
            return
        data = snapshot or self.snapshot(user_id)
        if data is None:
            return
        try:
            await self._store.save_snapshot(user_id, data)
        except Exception:
            import logging

            logging.getLogger(__name__).warning("Snapshot store save failed for user=%s", user_id)

    def list_users(self) -> list[str]:
        with self._lock:
            return sorted(self._snapshots.keys())

    def clear(self, user_id: str | None = None) -> None:
        with self._lock:
            if user_id is None:
                self._snapshots.clear()
            else:
                self._snapshots.pop(user_id, None)


portfolio_engine = PortfolioEngine()