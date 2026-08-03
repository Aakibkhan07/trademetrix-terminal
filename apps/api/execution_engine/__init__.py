"""Execution Engine v1.0 — enterprise execution layer above the frozen Broker SDK.

The engine formalizes the production OMS/execution/paper/portfolio stack and
fills its genuine gaps: canonical typed domain events, a canonical order state
machine, a Trade Manager (fills ledger), a Position Manager (event-driven
netting), a P&L Engine, a Portfolio Engine (aggregation + persistence) and a
facade with idempotent multi-account submit/modify/cancel.
"""

from execution_engine.events import (
    ExecutionDomain,
    ExecutionEngineBus,
    ExecutionEngineEvent,
    ExecutionEventType,
    execution_bus,
    order_event,
    position_event,
    portfolio_event,
    risk_event,
    trade_event,
)
from execution_engine.state_machine import (
    OrderState,
    OrderStateMachine,
    STATE_TRANSITIONS,
    state_machine,
)
from execution_engine.trades import TradeManager, trade_manager
from execution_engine.positions import PositionManager, position_manager
from execution_engine.pnl import PnLEngine, pnl_engine
from execution_engine.portfolio_engine import PortfolioEngine, portfolio_engine
from execution_engine.engine import ExecutionEngine, execution_engine

__all__ = [
    "ExecutionDomain",
    "ExecutionEngineBus",
    "ExecutionEngineEvent",
    "ExecutionEventType",
    "execution_bus",
    "order_event",
    "position_event",
    "portfolio_event",
    "risk_event",
    "trade_event",
    "OrderState",
    "OrderStateMachine",
    "STATE_TRANSITIONS",
    "state_machine",
    "TradeManager",
    "trade_manager",
    "PositionManager",
    "position_manager",
    "PnLEngine",
    "pnl_engine",
    "PortfolioEngine",
    "portfolio_engine",
    "ExecutionEngine",
    "execution_engine",
]
