"""Execution Engine bootstrap (Execution Engine v1.0).

``init_execution_engine`` wires the canonical bus + all engine modules once at
application startup (called from ``main.py`` lifespan), and
``shutdown_execution_engine`` drains the bus on shutdown. Idempotent.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

_initialized = False


def init_execution_engine(loop: asyncio.AbstractEventLoop | None = None) -> dict[str, Any]:
    """Wire the Execution Engine: bus, managers, metrics and legacy bridge.

    Returns a registry of engine singletons for introspection/tests.
    """
    global _initialized
    if _initialized:
        return _registry()

    from execution_engine import trade_manager, position_manager, pnl_engine, portfolio_engine, execution_bus
    from execution_engine.engine import execution_engine as facade
    from execution_engine.events import bridge_legacy_events
    from execution_engine.metrics import execution_metrics

    # Chain: ORDER fills -> TradeManager -> TRADE -> PositionManager -> POSITION
    # -> PnLEngine -> PORTFOLIO_REVALUED -> PortfolioEngine -> PORTFOLIO_SNAPSHOT
    pnl_engine._positions = position_manager
    portfolio_engine._positions = position_manager
    portfolio_engine._pnl = pnl_engine

    trade_manager.install()
    position_manager.install()
    pnl_engine.install()
    portfolio_engine.install()
    execution_metrics.install()

    bridge_legacy_events()

    if loop is not None:
        execution_bus.start(loop)
    else:
        try:
            execution_bus.start(asyncio.get_running_loop())
        except RuntimeError:
            logger.warning("Execution engine bus not started: no running event loop (bus dispatches inline)")

    _initialized = True
    logger.info(
        "Execution Engine v1.0 initialized (bus running=%s, subscribers=%d)",
        execution_bus.running,
        execution_bus.subscriber_count(),
    )
    return _registry()


async def shutdown_execution_engine() -> None:
    """Drain + stop the canonical bus and its dispatcher task."""
    from execution_engine import execution_bus

    if execution_bus.running:
        await execution_bus.stop()
        logger.info("Execution Engine bus stopped")


def reset_execution_engine() -> None:
    """Test hook: forget initialization state (does not touch state)."""
    global _initialized
    _initialized = False


def _registry() -> dict[str, Any]:
    from execution_engine import (
        execution_bus,
        pnl_engine,
        portfolio_engine,
        position_manager,
        trade_manager,
    )
    from execution_engine.engine import execution_engine as facade

    return {
        "bus": execution_bus,
        "trade_manager": trade_manager,
        "position_manager": position_manager,
        "pnl_engine": pnl_engine,
        "portfolio_engine": portfolio_engine,
        "execution_engine": facade,
    }
