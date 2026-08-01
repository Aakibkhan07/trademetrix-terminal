"""Strategy quality / risk / complexity / readability / readiness scoring.

Pure heuristics over the DSL + compiler validation output. Used by the
builder UI to show a deployment-readiness scorecard. No engine interaction.
"""

from __future__ import annotations

from builder.compiler import compile_dsl
from builder.models import StrategyDSL, StrategyScore


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, round(v, 1)))


def _grade(overall: float) -> str:
    if overall >= 90:
        return "A+"
    if overall >= 80:
        return "A"
    if overall >= 70:
        return "B"
    if overall >= 60:
        return "C"
    if overall >= 50:
        return "D"
    return "F"


def score_strategy(dsl: StrategyDSL) -> StrategyScore:
    graph, validation = compile_dsl(dsl)
    nodes = dsl.nodes or []
    edges = dsl.edges or []
    node_count = len(nodes)
    edge_count = len(edges)

    errors = [i for i in validation.issues if i.severity == "error"]
    warnings = [i for i in validation.issues if i.severity == "warning"]
    breakdown: list[dict] = []

    # ── Quality: completeness of wiring + parameters ──
    quality = 100.0
    quality -= len(errors) * 8.0
    quality -= len(warnings) * 5.0
    configured = sum(1 for n in nodes if n.params)
    if node_count:
        quality -= (node_count - configured) * 2.0
    if not dsl.description:
        quality -= 5.0
    if not dsl.tags:
        quality -= 2.0
    quality = _clamp(quality)
    breakdown.append({
        "metric": "quality",
        "label": "Quality",
        "score": quality,
        "note": f"{len(errors)} errors, {len(warnings)} warnings, {configured}/{node_count} nodes configured",
    })

    # ── Complexity: nodes, depth, category diversity ──
    complexity = 0.0
    if node_count:
        categories = {n.block_type.split(".")[0] for n in nodes}
        complexity += min(node_count * 6.0, 55.0)
        complexity += min(len(categories) * 6.0, 25.0)
        if graph:
            complexity += min(graph.max_depth * 4.0, 20.0)
    complexity = _clamp(complexity)
    breakdown.append({
        "metric": "complexity",
        "label": "Complexity",
        "score": complexity,
        "note": f"{node_count} nodes, {len(categories) if node_count else 0} categories, depth {graph.max_depth if graph else 0}",
    })

    # ── Risk: exit wiring, order gating, capital limits ──
    risk = 0.0
    order_nodes = [n for n in nodes if n.block_type.startswith("order.")]
    exit_nodes = [n for n in nodes if any(k in n.block_type for k in ("exit", "sl", "target", "reverse"))]
    risk_blocks = [n for n in nodes if n.block_type.startswith("risk.") or n.block_type.startswith("portfolio.")]
    conditioned = sum(
        1 for n in order_nodes
        if any(e.target_node == n.id and e.target_port in ("condition", "triggered", "result", "value") for e in edges)
    )
    risk += min(len(order_nodes) * 6.0, 30.0)
    if order_nodes and not exit_nodes:
        risk += 20.0
    if order_nodes and conditioned < len(order_nodes):
        risk += 15.0
    if not risk_blocks:
        risk += 10.0
    settings = dsl.settings
    if settings.max_positions <= 0:
        risk += 10.0
    if not settings.max_risk_per_trade and not dsl.deployment.risk.risk_per_trade:
        risk += 5.0
    if dsl.deployment.mode == "live" and not dsl.deployment.capital:
        risk += 10.0
    risk = _clamp(risk)
    breakdown.append({
        "metric": "risk",
        "label": "Risk",
        "score": risk,
        "note": f"{len(order_nodes)} order blocks ({conditioned} conditioned), {len(exit_nodes)} exits, {len(risk_blocks)} guards",
    })

    # ── Readability: structure quality ──
    readability = 100.0
    if node_count and edge_count == 0:
        readability -= 30.0
    if graph and validation.cycles:
        readability -= 15.0
    if graph:
        depth_ratio = graph.max_depth / max(node_count, 1)
        if depth_ratio > 0.6:
            readability -= 10.0  # long chains are harder to read
    if dsl.name in ("", "Untitled Strategy"):
        readability -= 10.0
    readability = _clamp(readability)
    breakdown.append({
        "metric": "readability",
        "label": "Readability",
        "score": readability,
        "note": f"{edge_count} connections, name {'set' if dsl.name not in ('', 'Untitled Strategy') else 'missing'}",
    })

    # ── Readiness: can it actually be deployed safely ──
    readiness = 0.0
    if validation.valid:
        readiness += 40.0
    if not warnings:
        readiness += 20.0
    if order_nodes:
        readiness += 15.0
    if order_nodes and all(
        any(e.target_node == n.id and e.target_port in ("condition", "triggered", "result", "value") for e in edges)
        for n in order_nodes
    ):
        readiness += 10.0
    if exit_nodes:
        readiness += 10.0
    if dsl.deployment.capital > 0 or dsl.deployment.mode != "live":
        readiness += 5.0
    readiness = _clamp(readiness)
    breakdown.append({
        "metric": "readiness",
        "label": "Deployment Readiness",
        "score": readiness,
        "note": f"{'valid' if validation.valid else 'invalid'}, {len(order_nodes)} order blocks, capital {'set' if dsl.deployment.capital > 0 else 'unset'}",
    })

    overall = _clamp(0.35 * quality + 0.25 * (100.0 - risk) + 0.2 * readiness + 0.2 * readability)

    return StrategyScore(
        overall=overall,
        quality=quality,
        risk=risk,
        complexity=complexity,
        readability=readability,
        readiness=readiness,
        grade=_grade(overall),
        breakdown=breakdown,
    )
