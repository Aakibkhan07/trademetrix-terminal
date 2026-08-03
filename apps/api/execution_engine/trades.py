"""Trade Manager (Execution Engine v1.0) — canonical fills ledger.

Derives a trade for every executed fill (``order.filled`` /
``order.partially_filled``), records it in a thread-safe in-memory ledger and
publishes a canonical ``trade.executed`` domain event. Every downstream engine
(Position Manager, P&L Engine, Portfolio Engine) consumes trades from the bus,
never from broker internals.

The legacy ``orders`` audit table stays the durable audit trail; this ledger is
the formal fills book (a ``trades`` persistence adapter can be attached later
via the ``TradeStore`` protocol).
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel, Field

from execution_engine.events import (
    ExecutionDomain,
    ExecutionEngineEvent,
    ExecutionEventType,
    execution_bus,
    trade_event,
)

_FILL_EVENTS = (
    ExecutionEventType.ORDER_FILLED,
    ExecutionEventType.ORDER_PARTIALLY_FILLED,
)


class TradeRecord(BaseModel):
    """One executed fill."""

    trade_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    user_id: str = ""
    broker: str = ""
    account: str = ""
    order_id: str = ""
    client_order_id: str = ""
    broker_order_id: str = ""
    correlation_id: str = ""
    symbol: str = ""
    side: str = ""
    quantity: int = 0
    price: float = 0.0
    commission: float = 0.0
    exchange_charges: float = 0.0
    stt: float = 0.0
    stamp_duty: float = 0.0
    charges: float = 0.0
    strategy_id: str = ""
    source: str = ""
    is_paper: bool = False
    traded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def turnover(self) -> float:
        return round(self.quantity * self.price, 2)


class TradeStore(Protocol):
    """Optional durable store for the fills ledger (Supabase adapter later)."""

    async def save(self, trade: TradeRecord) -> None: ...

    async def load(self, user_id: str, broker: str | None = None, limit: int = 1000) -> list[TradeRecord]: ...


class TradeLedger:
    """Thread-safe in-memory fills book, capped per account."""

    def __init__(self, max_per_account: int = 20000) -> None:
        self._trades: dict[str, list[TradeRecord]] = {}
        self._lock = threading.RLock()
        self._max_per_account = max_per_account

    def _key(self, user_id: str, broker: str) -> str:
        return f"{user_id}:{broker}"

    def add(self, trade: TradeRecord) -> None:
        with self._lock:
            key = self._key(trade.user_id, trade.broker)
            bucket = self._trades.setdefault(key, [])
            bucket.append(trade)
            if len(bucket) > self._max_per_account:
                del bucket[: len(bucket) - self._max_per_account]

    def list(
        self,
        user_id: str,
        broker: str | None = None,
        symbol: str | None = None,
        since: datetime | None = None,
        limit: int = 1000,
    ) -> list[TradeRecord]:
        with self._lock:
            keys = [self._key(user_id, b) for b in (broker,)] if broker else [k for k in self._trades if k.startswith(user_id + ":")]
            rows: list[TradeRecord] = []
            for k in keys:
                for t in self._trades.get(k, []):
                    if symbol and t.symbol != symbol:
                        continue
                    if since and t.traded_at < since:
                        continue
                    rows.append(t)
        rows.sort(key=lambda t: t.traded_at)
        return rows[-limit:]

    def count(self, user_id: str | None = None) -> int:
        with self._lock:
            if user_id is None:
                return sum(len(v) for v in self._trades.values())
            return sum(len(v) for k, v in self._trades.items() if k.startswith(user_id + ":"))

    def totals(self, user_id: str, broker: str | None = None) -> dict[str, Any]:
        """Aggregate filled qty / turnover / charges per (user[, broker])."""
        rows = self.list(user_id, broker=broker)
        agg: dict[str, dict[str, Any]] = {}
        for t in rows:
            key = f"{t.broker}:{t.symbol}"
            a = agg.setdefault(key, {"quantity": 0, "turnover": 0.0, "charges": 0.0, "trades": 0})
            a["quantity"] += t.quantity
            a["turnover"] += t.turnover
            a["charges"] += t.charges
            a["trades"] += 1
        for a in agg.values():
            a["turnover"] = round(a["turnover"], 2)
            a["charges"] = round(a["charges"], 2)
        return agg

    def clear(self, user_id: str | None = None) -> None:
        with self._lock:
            if user_id is None:
                self._trades.clear()
            else:
                for k in list(self._trades):
                    if k.startswith(user_id + ":"):
                        del self._trades[k]


class TradeManager:
    """Subscribes to order fills, records trades, emits trade events."""

    def __init__(self, bus: Any | None = None, ledger: TradeLedger | None = None, store: TradeStore | None = None) -> None:
        self._bus = bus or execution_bus
        self._ledger = ledger or TradeLedger()
        self._store = store
        self._installed = False
        self._lock = threading.RLock()

    def install(self) -> None:
        """Idempotently subscribe to order-fill events."""
        with self._lock:
            if self._installed:
                return
            self._bus.subscribe(ExecutionDomain.ORDER, self._on_order_event)
            self._installed = True

    @property
    def ledger(self) -> TradeLedger:
        return self._ledger

    # ------------------------------------------------------------------
    async def _on_order_event(self, event: ExecutionEngineEvent) -> None:
        if event.type not in _FILL_EVENTS:
            return
        trade = self._build_trade(event)
        if trade is None:
            return
        self._ledger.add(trade)
        if self._store is not None:
            try:
                await self._store.save(trade)
            except Exception:
                # Fail-open: the in-memory ledger + audit trail still hold the fill.
                import logging

                logging.getLogger(__name__).warning("TradeStore.save failed for trade=%s", trade.trade_id)
        self._bus.publish(
            trade_event(
                user_id=trade.user_id,
                broker=trade.broker,
                order_id=trade.order_id,
                client_order_id=trade.client_order_id,
                broker_order_id=trade.broker_order_id,
                correlation_id=trade.correlation_id,
                symbol=trade.symbol,
                side=trade.side,
                quantity=trade.quantity,
                price=trade.price,
                message=f"Filled {trade.quantity} {trade.symbol} @ {trade.price}",
                payload={
                    "trade_id": trade.trade_id,
                    "commission": trade.commission,
                    "exchange_charges": trade.exchange_charges,
                    "stt": trade.stt,
                    "stamp_duty": trade.stamp_duty,
                    "charges": trade.charges,
                    "strategy_id": trade.strategy_id,
                    "source": trade.source,
                    "is_paper": trade.is_paper,
                    "account": trade.account,
                    "traded_at": trade.traded_at.isoformat(),
                },
            )
        )

    def _build_trade(self, event: ExecutionEngineEvent) -> TradeRecord | None:
        qty = int(event.filled_quantity or 0)
        price = float(event.avg_price or event.price or 0.0)
        if qty <= 0:
            return None
        if price <= 0:
            import logging

            logging.getLogger(__name__).warning(
                "Skipping trade with zero fill price: %s (%s)", event.client_order_id, event.symbol
            )
            return None
        payload = event.payload or {}
        commission = float(payload.get("commission", 0.0) or 0.0)
        exchange_charges = float(payload.get("exchange_charges", 0.0) or 0.0)
        stt = float(payload.get("stt", 0.0) or 0.0)
        stamp_duty = float(payload.get("stamp_duty", 0.0) or 0.0)
        return TradeRecord(
            user_id=event.user_id,
            broker=event.broker,
            account=str(payload.get("account", "") or ""),
            order_id=event.order_id,
            client_order_id=event.client_order_id,
            broker_order_id=event.broker_order_id,
            correlation_id=event.correlation_id,
            symbol=event.symbol,
            side=event.side,
            quantity=qty,
            price=price,
            commission=round(commission, 2),
            exchange_charges=round(exchange_charges, 2),
            stt=round(stt, 2),
            stamp_duty=round(stamp_duty, 2),
            charges=round(commission + exchange_charges + stt + stamp_duty, 2),
            strategy_id=str(payload.get("strategy_id", "") or ""),
            source=str(payload.get("source", "") or ""),
            is_paper=bool(payload.get("is_paper", event.broker == "paper")),
            traded_at=event.occurred_at,
        )

    # ------------------------------------------------------------------
    def list_trades(self, user_id: str, broker: str | None = None, symbol: str | None = None, limit: int = 1000) -> list[TradeRecord]:
        return self._ledger.list(user_id, broker=broker, symbol=symbol, limit=limit)

    def totals(self, user_id: str, broker: str | None = None) -> dict[str, Any]:
        return self._ledger.totals(user_id, broker=broker)

    def count(self, user_id: str | None = None) -> int:
        return self._ledger.count(user_id)


trade_manager = TradeManager()
