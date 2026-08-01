"""P0 regression tests: GraphStrategy Order Block condition gating.

Covers the incident: order blocks used to evaluate as triggered=true on every
candle regardless of their condition input, which could generate unintended
live orders. Now:
  - connected condition true   -> order fires
  - connected condition false  -> no order
  - no condition connected     -> no order (fail-closed)
  - multiple chained conditions -> gated through intermediate logic blocks
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from builder.models import GraphEdge, GraphNode, StrategyDSL
from builder.strategy import GraphStrategy
from core.models import Candle, Exchange, InstrumentType


def _candle(close: float, i: int = 0) -> Candle:
    return Candle(
        symbol="NIFTY",
        exchange=Exchange.NSE,
        interval="5m",
        open=close - 0.5,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000,
        timestamp=datetime(2026, 8, 1, 9 + (15 + i) // 60, (15 + i) % 60, tzinfo=UTC),
        oi=0,
        instrument_type=InstrumentType.EQ,
    )


def _downtrend(n: int, start: float = 200.0, step: float = -0.5) -> list[Candle]:
    return [_candle(start + step * i, i=i) for i in range(n)]


def _uptrend(n: int, start: float = 100.0, step: float = 0.6) -> list[Candle]:
    return [_candle(start + step * i, i=i) for i in range(n)]


def _graph(nodes: list[GraphNode], edges: list[GraphEdge]) -> GraphStrategy:
    dsl = StrategyDSL(
        name="test",
        description="",
        nodes=nodes,
        edges=edges,
        settings={"symbol": "NIFTY", "interval": "5m"},
    )
    return GraphStrategy(config={"_dsl": dsl})


def _node(nid: str, block_type: str, params: dict | None = None) -> GraphNode:
    return GraphNode(id=nid, block_type=block_type, params=params or {})


def _edge(sid: str, sp: str, tid: str, tp: str) -> GraphEdge:
    return GraphEdge(id=f"{sid}-{sp}-{tid}-{tp}", source_node=sid, source_port=sp,
                     target_node=tid, target_port=tp)


def _ema_cross_chain(with_and: bool, not_gate: bool = False) -> tuple[list[GraphNode], list[GraphEdge]]:
    """close_history -> ema5/ema13 -> cross_above -> [logic.and] -> order.buy."""
    nodes = [
        _node("src", "source.candle"),
        _node("hist", "source.close_history", {"max_length": 100}),
        _node("f", "indicator.ema", {"period": 5}),
        _node("s", "indicator.ema", {"period": 13}),
        _node("x", "signal.cross_above"),
    ]
    edges = [
        _edge("hist", "prices", "f", "source"),
        _edge("hist", "prices", "s", "source"),
        _edge("f", "value", "x", "a"),
        _edge("s", "value", "x", "b"),
    ]
    if with_and:
        nodes.append(_node("and", "logic.and"))
        nodes.append(_node("buy", "order.buy", {"quantity": 75, "reason": "test"}))
        if not_gate:
            nodes.append(_node("not", "logic.not"))
            edges += [
                _edge("x", "triggered", "not", "value"),
                _edge("not", "result", "and", "a"),
                _edge("x", "triggered", "and", "b"),
            ]
        else:
            edges += [
                _edge("x", "triggered", "and", "a"),
                _edge("x", "triggered", "and", "b"),
            ]
        edges.append(_edge("and", "result", "buy", "condition"))
    else:
        nodes.append(_node("buy", "order.buy", {"quantity": 75, "reason": "test"}))
        edges.append(_edge("x", "triggered", "buy", "condition"))
    return nodes, edges


async def _run(strategy: GraphStrategy, candles: list[Candle]) -> list[str]:
    await strategy.on_start()
    sides: list[str] = []
    for c in candles:
        result = await strategy.on_candle(c)
        if result and result.orders:
            sides.extend(o.side.value for o in result.orders)
    return sides


# ─── Connected condition = true ───

@pytest.mark.asyncio
async def test_connected_condition_true_fires_order() -> None:
    nodes, edges = _ema_cross_chain(with_and=False)
    strategy = _graph(nodes, edges)
    assert strategy._graph is not None

    sides = await _run(strategy, _downtrend(30, start=200) + _uptrend(60, start=185))
    assert "BUY" in sides


# ─── Connected condition = false ───

@pytest.mark.asyncio
async def test_connected_condition_false_no_order() -> None:
    nodes, edges = _ema_cross_chain(with_and=False)
    strategy = _graph(nodes, edges)
    assert strategy._graph is not None

    sides = await _run(strategy, _downtrend(60, start=200))
    assert sides == []


# ─── No condition connected = fail closed ───

@pytest.mark.asyncio
async def test_no_condition_connected_no_order() -> None:
    src = _node("src", "source.candle")
    buy = _node("buy", "order.buy", {"quantity": 75})
    strategy = _graph(nodes=[src, buy], edges=[])
    assert strategy._graph is not None

    sides = await _run(strategy, _uptrend(10, start=100))
    assert sides == []


# ─── Multiple chained conditions ───

@pytest.mark.asyncio
async def test_chained_conditions_gate_order_true_path() -> None:
    nodes, edges = _ema_cross_chain(with_and=True)
    strategy = _graph(nodes, edges)
    assert strategy._graph is not None

    sides = await _run(strategy, _downtrend(30, start=200) + _uptrend(60, start=185))
    assert "BUY" in sides


@pytest.mark.asyncio
async def test_chained_conditions_gate_order_false_path() -> None:
    """and(cross.triggered, not(cross.triggered)) is always false -> never fires."""
    nodes, edges = _ema_cross_chain(with_and=True, not_gate=True)
    strategy = _graph(nodes, edges)
    assert strategy._graph is not None

    sides = await _run(strategy, _downtrend(30, start=200) + _uptrend(60, start=185))
    assert sides == []


@pytest.mark.asyncio
async def test_chained_condition_false_no_order() -> None:
    """Downtrend -> cross never fires -> chained condition false -> no order."""
    nodes, edges = _ema_cross_chain(with_and=True)
    strategy = _graph(nodes, edges)
    assert strategy._graph is not None

    sides = await _run(strategy, _downtrend(60, start=200))
    assert sides == []


# ─── Backward compatibility / no unrelated breakage ───

@pytest.mark.asyncio
async def test_non_order_blocks_unaffected() -> None:
    """Indicator + signal blocks still evaluate without order blocks."""
    src = _node("src", "source.candle")
    hist = _node("hist", "source.close_history", {"max_length": 50})
    ema_fast = _node("f", "indicator.ema", {"period": 5})
    ema_slow = _node("s", "indicator.ema", {"period": 13})
    cross = _node("x", "signal.cross_above")
    strategy = _graph(
        nodes=[src, hist, ema_fast, ema_slow, cross],
        edges=[
            _edge("hist", "prices", "f", "source"),
            _edge("hist", "prices", "s", "source"),
            _edge("f", "value", "x", "a"),
            _edge("s", "value", "x", "b"),
        ],
    )
    assert strategy._graph is not None

    sides = await _run(strategy, _uptrend(10, start=100))
    assert sides == []


@pytest.mark.asyncio
async def test_ema_cross_template_no_spurious_orders() -> None:
    """Template on a clean uptrend must not produce unconditional orders."""
    import builder.templates as templates

    dsl = templates.STRATEGY_TEMPLATES["ema_crossover"]
    strategy = GraphStrategy(config={"_dsl": dsl})
    assert strategy._graph is not None

    sides = await _run(strategy, _uptrend(40, start=100, step=0.5))
    assert sides == []
