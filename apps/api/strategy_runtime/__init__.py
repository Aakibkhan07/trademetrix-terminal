"""Strategy Runtime v1.0 — production strategy execution layer.

Built additively on the frozen Broker SDK + Execution Engine: strategies run
through the existing ``engine.gate`` path (Risk Engine + paper routing + engine
accounting unchanged). Components:

- RuntimeManager (orchestrator + lifecycle verbs)
- StrategyScheduler (time triggers + session edges)
- Strategy Workers (one isolated task per strategy)
- Execution Context (position/portfolio/PnL/risk/market/history/broker)
- Strategy Lifecycle Manager (state machine)
- Event Router, Tick Dispatcher, Multi-Timeframe Dispatcher
- Runtime Registry, Strategy State Manager, Runtime Recovery
- Observability (metrics + structured logs)

Not wired by import: the singleton (:data:`strategy_runtime_manager`) is
initialized by the app lifespan (see ``main.py``).
"""
from __future__ import annotations

from strategy_runtime.manager import StrategyRuntimeManager, strategy_runtime_manager
from strategy_runtime.models import (
    RuntimeState,
    StrategyRuntimeStatus,
    StrategySpec,
    StrategyTrigger,
)
from strategy_runtime.observability import RuntimeObservability, runtime_observability
from strategy_runtime.registry import RuntimeRecord, RuntimeRegistry
from strategy_runtime.state_machine import IllegalTransition, can_transition
from strategy_runtime.state_store import StrategyStateStore
from strategy_runtime.workers import StrategyWorker

__all__ = [
    "StrategyRuntimeManager",
    "strategy_runtime_manager",
    "RuntimeState",
    "StrategyRuntimeStatus",
    "StrategySpec",
    "StrategyTrigger",
    "RuntimeObservability",
    "runtime_observability",
    "RuntimeRecord",
    "RuntimeRegistry",
    "IllegalTransition",
    "can_transition",
    "StrategyStateStore",
    "StrategyWorker",
]

__version__ = "1.0.0"
