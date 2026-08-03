"""P&L Engine (Execution Engine v1.0).

Aggregates realized + unrealized P&L into per-account accounting state:
realized, unrealized, daily P&L (IST day window), equity and drawdown.

Consumes ``position.*`` events (which already carry realized/unrealized
breakdown per symbol) and recomputes the account totals from the Position
Manager, so the engine never drifts from the fills ledger. Publishes
``portfolio.revalued`` after every recompute.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field

from execution_engine.events import (
    ExecutionDomain,
    ExecutionEngineEvent,
    ExecutionEventType,
    execution_bus,
    portfolio_event,
)

IST = timezone(timedelta(hours=5, minutes=30))


def _now_today() -> str:
    return datetime.now(IST).date().isoformat()


class PnLAccount(BaseModel):
    user_id: str = ""
    broker: str = ""
    initial_capital: float = 500000.0
    realised_pnl: float = 0.0
    unrealised_pnl: float = 0.0
    daily_pnl: float = 0.0
    current_equity: float = 500000.0
    day_start_equity: float = 500000.0
    peak_equity: float = 500000.0
    drawdown_pct: float = 0.0
    day_date: str = ""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PnLEngine:
    def __init__(self, bus: Any | None = None, position_source: Any | None = None, initial_capital: float = 500000.0) -> None:
        self._bus = bus or execution_bus
        self._positions = position_source  # PositionManager (injected to avoid a cycle)
        self._initial_capital = initial_capital
        self._accounts: dict[str, PnLAccount] = {}
        self._lock = threading.RLock()
        self._installed = False

    def install(self) -> None:
        """Idempotently subscribe to position events."""
        with self._lock:
            if self._installed:
                return
            self._bus.subscribe(ExecutionDomain.POSITION, self._on_position_event)
            self._installed = True

    def _key(self, user_id: str, broker: str) -> str:
        return f"{user_id}:{broker}"

    def _ensure(self, user_id: str, broker: str) -> PnLAccount:
        with self._lock:
            key = self._key(user_id, broker)
            account = self._accounts.get(key)
            if account is None:
                account = PnLAccount(
                    user_id=user_id,
                    broker=broker,
                    initial_capital=self._initial_capital,
                    current_equity=self._initial_capital,
                    day_start_equity=self._initial_capital,
                    peak_equity=self._initial_capital,
                )
                self._accounts[key] = account
            account.day_date = _now_today()
            return account

    # ------------------------------------------------------------------
    async def _on_position_event(self, event: ExecutionEngineEvent) -> None:
        if event.type not in (
            ExecutionEventType.POSITION_OPENED,
            ExecutionEventType.POSITION_UPDATED,
            ExecutionEventType.POSITION_CLOSED,
        ):
            return
        self.recompute(event.user_id, event.broker)

    def recompute(self, user_id: str, broker: str) -> PnLAccount:
        """Recompute an account from the Position Manager's current state."""
        account = self._ensure(user_id, broker)
        totals = {"realised_pnl": account.realised_pnl, "unrealised_pnl": account.unrealised_pnl}
        if self._positions is not None:
            totals = self._positions.aggregate_pnl(user_id, broker)

        today = _now_today()
        if account.day_date and account.day_date != today:
            # New trading day: carry last equity forward as the day start.
            account.day_start_equity = account.current_equity
            account.day_date = today
        elif not account.day_date:
            account.day_date = today

        account.realised_pnl = totals["realised_pnl"]
        account.unrealised_pnl = totals["unrealised_pnl"]
        account.current_equity = round(account.initial_capital + account.realised_pnl + account.unrealised_pnl, 2)
        if account.current_equity > account.peak_equity:
            account.peak_equity = account.current_equity
        if account.peak_equity > 0:
            account.drawdown_pct = round(max(0.0, (account.peak_equity - account.current_equity) / account.peak_equity * 100), 2)
        account.daily_pnl = round(account.current_equity - account.day_start_equity, 2)
        account.updated_at = datetime.now(timezone.utc)

        open_positions = 0
        if self._positions is not None:
            open_positions = len(self._positions.open_positions(user_id, broker))

        self._bus.publish(
            portfolio_event(
                ExecutionEventType.PORTFOLIO_REVALUED,
                user_id=user_id,
                broker=broker,
                message=f"Revalued {broker} account: pnl={account.realised_pnl + account.unrealised_pnl:.2f}",
                payload={
                    "account": account.model_dump(mode="json"),
                    "open_positions": open_positions,
                    "source": "pnl_engine",
                },
            )
        )
        return account

    # ------------------------------------------------------------------
    def get_account(self, user_id: str, broker: str) -> PnLAccount:
        return self._ensure(user_id, broker)

    def get_accounts(self, user_id: str, broker: str | None = None) -> list[PnLAccount]:
        with self._lock:
            prefix = f"{user_id}:"
            if broker:
                prefix = f"{user_id}:{broker}"
                return [a for k, a in self._accounts.items() if k == prefix]
            return [a for k, a in self._accounts.items() if k.startswith(prefix)]

    def aggregate(self, user_id: str, broker: str | None = None) -> dict[str, float]:
        """Totals across a user's accounts."""
        accounts = self.get_accounts(user_id, broker)
        return {
            "realised_pnl": round(sum(a.realised_pnl for a in accounts), 2),
            "unrealised_pnl": round(sum(a.unrealised_pnl for a in accounts), 2),
            "daily_pnl": round(sum(a.daily_pnl for a in accounts), 2),
            "current_equity": round(sum(a.current_equity for a in accounts), 2),
            "peak_equity": round(max((a.peak_equity for a in accounts), default=0.0), 2),
            "drawdown_pct": round(max((a.drawdown_pct for a in accounts), default=0.0), 2),
        }

    def clear(self, user_id: str | None = None) -> None:
        with self._lock:
            if user_id is None:
                self._accounts.clear()
            else:
                prefix = f"{user_id}:"
                for k in [k for k in self._accounts if k.startswith(prefix)]:
                    del self._accounts[k]


def _now_today() -> str:
    return datetime.now(IST).date().isoformat()


pnl_engine = PnLEngine()