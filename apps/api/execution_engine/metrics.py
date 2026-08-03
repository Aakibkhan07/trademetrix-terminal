"""Prometheus metrics for the Execution Engine (Execution Engine v1.0).

A small event-driven sink that turns canonical domain events into Prometheus
counters/gauges. Includes generic aggregate gauges (no user_id label — avoids
cardinality blowout); broker-scoped labels only for broker where the broker set
is small.

Wired once from ``init_execution_engine``.
"""
from __future__ import annotations

import threading
from typing import Any

from prometheus_client import Counter, Gauge

from execution_engine.events import (
    ExecutionDomain,
    ExecutionEngineEvent,
    ExecutionEventType,
    execution_bus,
)

# Order lifecycle counters
ee_order_events_total = Counter(
    "execution_engine_order_events_total",
    "Execution engine order domain events by type",
    ["order_type"],
)
ee_orders_filled_total = Counter(
    "execution_engine_orders_filled_total", "Orders that reached FILLED", ["broker"]
)
ee_orders_partially_filled_total = Counter(
    "execution_engine_orders_partially_filled_total",
    "Orders that reached PARTIALLY_FILLED",
    ["broker"],
)
ee_orders_rejected_total = Counter(
    "execution_engine_orders_rejected_total", "Orders rejected", ["broker"]
)
ee_orders_cancelled_total = Counter(
    "execution_engine_orders_cancelled_total", "Orders cancelled", ["broker"]
)
ee_orders_failed_total = Counter(
    "execution_engine_orders_failed_total", "Orders failed (infrastructure)", ["broker"]
)
ee_orders_pending_gauge = Gauge(
    "execution_engine_orders_pending", "Orders currently resting in PENDING", ["broker"]
)

# Trade + risk counters
ee_trades_executed_total = Counter(
    "execution_engine_trades_executed_total", "Fills recorded by the Trade Manager", ["broker"]
)
ee_risk_decisions_total = Counter(
    "execution_engine_risk_decisions_total", "Risk decisions by outcome", ["decision"]
)

# Account/portfolio gauges (per broker — small label set)
ee_account_realized_pnl = Gauge(
    "execution_engine_realized_pnl", "Realized P&L per account", ["broker"]
)
ee_account_unrealized_pnl = Gauge(
    "execution_engine_unrealized_pnl", "Unrealized P&L per account", ["broker"]
)
ee_account_daily_pnl = Gauge(
    "execution_engine_daily_pnl", "Daily P&L per account", ["broker"]
)
ee_account_equity = Gauge(
    "execution_engine_account_equity", "Current equity per account", ["broker"]
)
ee_account_drawdown_pct = Gauge(
    "execution_engine_account_drawdown_pct", "Drawdown percent per account", ["broker"]
)
ee_open_positions = Gauge(
    "execution_engine_open_positions", "Open positions per broker", ["broker"]
)

_LINE_EVENTS = {
    ExecutionEventType.ORDER_SUBMITTED: "submitted",
    ExecutionEventType.ORDER_VALIDATED: "validated",
    ExecutionEventType.ORDER_QUEUED: "queued",
    ExecutionEventType.ORDER_SENT: "sent",
    ExecutionEventType.ORDER_ACCEPTED: "accepted",
    ExecutionEventType.ORDER_PENDING: "pending",
    ExecutionEventType.ORDER_PARTIALLY_FILLED: "partially_filled",
    ExecutionEventType.ORDER_FILLED: "filled",
    ExecutionEventType.ORDER_MODIFIED: "modified",
    ExecutionEventType.ORDER_CANCELLED: "cancelled",
    ExecutionEventType.ORDER_REJECTED: "rejected",
    ExecutionEventType.ORDER_EXPIRED: "expired",
    ExecutionEventType.ORDER_FAILED: "failed",
    ExecutionEventType.EXECUTION_VALIDATED: "validated",
    ExecutionEventType.EXECUTION_RETRY: "retry",
    ExecutionEventType.EXECUTION_RESULT: "result",
}

_RECORDED_EVENTS = {
    ExecutionEventType.ORDER_FILLED,
    ExecutionEventType.ORDER_PARTIALLY_FILLED,
    ExecutionEventType.ORDER_REJECTED,
    ExecutionEventType.ORDER_CANCELLED,
    ExecutionEventType.ORDER_FAILED,
}


class ExecutionMetrics:
    def __init__(self, bus: Any | None = None) -> None:
        self._bus = bus or execution_bus
        self._installed = False
        self._lock = threading.RLock()

    def install(self) -> None:
        with self._lock:
            if self._installed:
                return
            self._bus.subscribe(ExecutionDomain.ORDER, self._on_order)
            self._bus.subscribe(ExecutionDomain.TRADE, self._on_trade)
            self._bus.subscribe(ExecutionDomain.RISK, self._on_risk)
            self._bus.subscribe(ExecutionDomain.PORTFOLIO, self._on_portfolio)
            self._installed = True

    def _broker_label(self, event: ExecutionEngineEvent) -> str:
        return event.broker or "unknown"

    def _on_order(self, event: ExecutionEngineEvent) -> None:
        kind = _LINE_EVENTS.get(event.type)
        if kind is not None:
            ee_order_events_total.labels(order_type=kind).inc()
        if event.type not in _RECORDED_EVENTS:
            return
        broker = self._broker_label(event)
        if event.type == ExecutionEventType.ORDER_FILLED:
            ee_orders_filled_total.labels(broker=broker).inc()
        elif event.type == ExecutionEventType.ORDER_PARTIALLY_FILLED:
            ee_orders_partially_filled_total.labels(broker=broker).inc()
        elif event.type == ExecutionEventType.ORDER_REJECTED:
            ee_orders_rejected_total.labels(broker=broker).inc()
        elif event.type == ExecutionEventType.ORDER_CANCELLED:
            ee_orders_cancelled_total.labels(broker=broker).inc()
        elif event.type == ExecutionEventType.ORDER_FAILED:
            ee_orders_failed_total.labels(broker=broker).inc()
        if event.type == ExecutionEventType.ORDER_PENDING:
            ee_orders_pending_gauge.labels(broker=broker).inc()

    def _on_trade(self, event: ExecutionEngineEvent) -> None:
        ee_trades_executed_total.labels(broker=self._broker_label(event)).inc()

    def _on_risk(self, event: ExecutionEngineEvent) -> None:
        decision = event.state or "UNKNOWN"
        if decision not in ("APPROVED", "WARNING", "REJECTED"):
            decision = (event.payload or {}).get("decision", "UNKNOWN")
        ee_risk_decisions_total.labels(decision=str(decision)).inc()

    def _on_portfolio(self, event: ExecutionEngineEvent) -> None:
        payload = event.payload or {}
        account = payload.get("account") or {}
        broker = self._broker_label(event)
        realized = account.get("realised_pnl") if isinstance(account, dict) else None
        if realized is not None:
            ee_account_realized_pnl.labels(broker=broker).set(float(realized))
        unrealized = account.get("unrealised_pnl") if isinstance(account, dict) else None
        if unrealized is not None:
            ee_account_unrealized_pnl.labels(broker=broker).set(float(unrealized))
        daily = account.get("daily_pnl") if isinstance(account, dict) else None
        if daily is not None:
            ee_account_daily_pnl.labels(broker=broker).set(float(daily))
        equity = account.get("current_equity") if isinstance(account, dict) else None
        if equity is not None:
            ee_account_equity.labels(broker=broker).set(float(equity))
        drawdown = account.get("drawdown_pct") if isinstance(account, dict) else None
        if drawdown is not None:
            ee_account_drawdown_pct.labels(broker=broker).set(float(drawdown))
        open_positions = payload.get("open_positions")
        if open_positions is not None:
            ee_open_positions.labels(broker=broker).set(int(open_positions))


execution_metrics = ExecutionMetrics()