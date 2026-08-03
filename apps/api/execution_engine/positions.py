"""Position Manager (Execution Engine v1.0) — event-driven position netting.

Consumes canonical ``trade.executed`` events and maintains the net open
position per (user, broker, symbol) with FIFO-realized P&L, volume-weighted
average prices and mark-to-market unrealized P&L. Publishes
``position.opened`` / ``position.updated`` / ``position.closed`` events that
feed the P&L Engine and the Portfolio Engine.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from execution_engine.events import (
    ExecutionDomain,
    ExecutionEngineEvent,
    ExecutionEventType,
    execution_bus,
    position_event,
)
from execution_engine.fifo import FifoLots

LONG = "LONG"
SHORT = "SHORT"
FLAT = "FLAT"


class EnginePosition(BaseModel):
    """Canonical net position for one (user, broker, symbol)."""

    user_id: str = ""
    broker: str = ""
    account: str = ""
    symbol: str = ""
    exchange: str = "NSE"
    quantity: int = 0  # signed: +long / -short
    open_quantity: int = 0
    side: str = FLAT
    average_price: float = 0.0
    average_buy_price: float = 0.0
    average_sell_price: float = 0.0
    buy_quantity: int = 0
    sell_quantity: int = 0
    last_price: float = 0.0
    realised_pnl: float = 0.0
    unrealised_pnl: float = 0.0
    m2m: float = 0.0
    product: str = "INTRADAY"
    strategy_id: str = ""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_open(self) -> bool:
        return self.quantity != 0


class PositionManager:
    """Thread-safe, event-driven net position ledger."""

    def __init__(self, bus: Any | None = None) -> None:
        self._bus = bus or execution_bus
        self._positions: dict[str, EnginePosition] = {}
        self._fifos: dict[str, FifoLots] = {}
        self._lock = threading.RLock()
        self._installed = False

    def install(self) -> None:
        """Idempotently subscribe to trade events."""
        with self._lock:
            if self._installed:
                return
            self._bus.subscribe(ExecutionDomain.TRADE, self._on_trade_event)
            self._installed = True

    def _key(self, user_id: str, broker: str, symbol: str) -> str:
        return f"{user_id}:{broker}:{symbol}"

    # ------------------------------------------------------------------
    async def _on_trade_event(self, event: ExecutionEngineEvent) -> None:
        if event.type != ExecutionEventType.TRADE_EXECUTED:
            return
        payload = event.payload or {}
        side = (event.side or "").upper()
        if side not in ("BUY", "SELL"):
            return
        price = float(event.avg_price or event.price or 0.0)
        quantity = int(event.quantity or 0)
        if quantity <= 0 or price <= 0:
            return

        key = self._key(event.user_id, event.broker, event.symbol)
        with self._lock:
            position = self._positions.get(key)
            was_open = position.is_open if position is not None else False
            fifo = self._fifos.setdefault(key, FifoLots())
            realized = fifo.apply(side, quantity, price)
            position = self._sync_position(event, position, fifo, realized, payload)
            self._positions[key] = position

        now_open = position.is_open
        if now_open and not was_open:
            etype = ExecutionEventType.POSITION_OPENED
        elif not now_open and was_open:
            etype = ExecutionEventType.POSITION_CLOSED
        else:
            etype = ExecutionEventType.POSITION_UPDATED

        self._bus.publish(
            position_event(
                etype,
                user_id=position.user_id,
                broker=position.broker,
                symbol=position.symbol,
                side=position.side,
                quantity=position.quantity,
                avg_price=position.average_price,
                correlation_id=event.correlation_id,
                message=f"{etype.value} {position.symbol} qty={position.quantity} avg={position.average_price}",
                payload={
                    "realized_pnl": realized,
                    "realised_pnl": position.realised_pnl,
                    "unrealised_pnl": position.unrealised_pnl,
                    "open_quantity": position.open_quantity,
                    "last_price": position.last_price,
                    "trade_id": payload.get("trade_id", ""),
                    "account": position.account,
                },
            )
        )

    def _sync_position(
        self,
        event: ExecutionEngineEvent,
        position: EnginePosition | None,
        fifo: FifoLots,
        realized: float,
        payload: dict[str, Any],
    ) -> EnginePosition:
        base = position if position is not None else EnginePosition(user_id=event.user_id, broker=event.broker, symbol=event.symbol)
        account = str(payload.get("account", "") or base.account)
        if account:
            base.account = account
        strategy_id = str(payload.get("strategy_id", "") or base.strategy_id)
        if strategy_id:
            base.strategy_id = strategy_id
        snap = fifo.snapshot()
        net = snap["net_quantity"]
        base.quantity = net
        base.open_quantity = abs(net)
        base.side = LONG if net > 0 else SHORT if net < 0 else FLAT
        base.buy_quantity = snap["long_quantity"]
        base.sell_quantity = snap["short_quantity"]
        base.average_buy_price = round(snap["average_buy_price"], 2)
        base.average_sell_price = round(snap["average_sell_price"], 2)
        base.average_price = base.average_buy_price if net > 0 else base.average_sell_price if net < 0 else 0.0
        base.realised_pnl = round(base.realised_pnl + realized, 2)
        base.last_price = float(event.payload.get("last_price", base.last_price) or base.last_price)
        if base.last_price > 0:
            base.unrealised_pnl = fifo.unrealized_pnl(base.last_price)
            base.m2m = base.unrealised_pnl
        base.updated_at = datetime.now(timezone.utc)
        return base

    # ------------------------------------------------------------------
    def get_position(self, user_id: str, broker: str, symbol: str) -> EnginePosition | None:
        with self._lock:
            return self._positions.get(self._key(user_id, broker, symbol))

    def get_positions(self, user_id: str, broker: str | None = None) -> list[EnginePosition]:
        with self._lock:
            if broker:
                prefix = f"{user_id}:{broker}:"
                return [p for k, p in self._positions.items() if k.startswith(prefix)]
            prefix = f"{user_id}:"
            return [p for k, p in self._positions.items() if k.startswith(prefix)]

    def open_positions(self, user_id: str, broker: str | None = None) -> list[EnginePosition]:
        return [p for p in self.get_positions(user_id, broker) if p.is_open]

    def aggregate_pnl(self, user_id: str, broker: str | None = None) -> dict[str, float]:
        """Sum of realised/unrealised across positions for a user."""
        realised = 0.0
        unrealised = 0.0
        for p in self.get_positions(user_id, broker):
            realised += p.realised_pnl
            unrealised += p.unrealised_pnl
        return {"realised_pnl": round(realised, 2), "unrealised_pnl": round(unrealised, 2)}

    def mark_to_market(self, user_id: str, broker: str, prices: dict[str, float]) -> list[EnginePosition]:
        """Revalue positions from a {symbol: last_price} map; emits updates."""
        updated: list[EnginePosition] = []
        with self._lock:
            prefix = f"{user_id}:{broker}:"
            for key, position in self._positions.items():
                if not key.startswith(prefix):
                    continue
                price = prices.get(position.symbol)
                if price is None or price <= 0:
                    continue
                position.last_price = price
                fifo = self._fifos.get(key)
                if fifo is not None:
                    position.unrealised_pnl = fifo.unrealized_pnl(price)
                    position.m2m = position.unrealised_pnl
                position.updated_at = datetime.now(timezone.utc)
                updated.append(position)
        for p in updated:
            self._bus.publish(
                position_event(
                    ExecutionEventType.POSITION_UPDATED,
                    user_id=p.user_id,
                    broker=p.broker,
                    symbol=p.symbol,
                    side=p.side,
                    quantity=p.quantity,
                    avg_price=p.average_price,
                    message=f"Mark-to-market {p.symbol} @ {p.last_price}",
                    payload={
                        "realized_pnl": 0.0,
                        "realised_pnl": p.realised_pnl,
                        "unrealised_pnl": p.unrealised_pnl,
                        "open_quantity": p.open_quantity,
                        "last_price": p.last_price,
                        "account": p.account,
                        "source": "mark_to_market",
                    },
                )
            )
        return updated

    def clear(self, user_id: str | None = None) -> None:
        with self._lock:
            if user_id is None:
                self._positions.clear()
                self._fifos.clear()
            else:
                prefix = f"{user_id}:"
                for k in [k for k in self._positions if k.startswith(prefix)]:
                    self._positions.pop(k, None)
                    self._fifos.pop(k, None)


position_manager = PositionManager()
