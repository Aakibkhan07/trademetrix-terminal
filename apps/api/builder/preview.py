import logging
from typing import Any

from builder.compiler import compile_dsl, estimate_latency
from builder.models import (
    ExecutionGraph,
    PreviewData,
    StrategyDSL,
    ValidationResult,
)

logger = logging.getLogger(__name__)


def generate_preview(dsl: StrategyDSL) -> dict:
    graph, validation = compile_dsl(dsl)

    if not graph:
        graph = ExecutionGraph()

    execution_order = []
    for node in graph.nodes:
        execution_order.append({
            "order": node.order,
            "block_type": node.block_type,
            "id": node.id,
            "inputs": node.inputs,
            "estimated_latency_us": node.estimated_latency_us,
            "category": node.category,
        })

    warnings = _generate_warnings(dsl, graph, validation)
    total_latency = graph.total_estimated_latency_us

    preview = PreviewData(
        execution_order=execution_order,
        total_latency_us=total_latency,
        max_depth=graph.max_depth,
        node_count=len(dsl.nodes),
        edge_count=len(dsl.edges),
        graph=graph,
        validation=validation,
        warnings=warnings,
    )

    return preview.model_dump(mode="json")


def _generate_warnings(dsl: StrategyDSL, graph: ExecutionGraph, validation: ValidationResult) -> list[str]:
    warnings = []
    warnings.extend(i.message for i in validation.issues if i.severity == "warning")

    if graph.nodes:
        slow_blocks = [n for n in graph.nodes if n.estimated_latency_us > 100]
        if slow_blocks:
            warnings.append(f"{len(slow_blocks)} high-latency block(s) detected (greek, deep indicators) — may impact real-time performance")

    category_counts: dict[str, int] = {}
    for n in graph.nodes:
        category_counts[n.category] = category_counts.get(n.category, 0) + 1

    if category_counts.get("smc", 0) > 3:
        warnings.append("Multiple SMC blocks may increase false signals — consider reducing")
    if category_counts.get("indicator", 0) > 8:
        warnings.append(f"Large number of indicators ({category_counts.get('indicator', 0)}) — may cause overfitting")
    if category_counts.get("order", 0) > 2:
        warnings.append("Multiple order blocks — only the first triggered order will execute per candle")

    if dsl.nodes and not graph.exit_points:
        warnings.append("No exit/order nodes detected — strategy will analyze but not trade")

    return warnings


def estimate_candle_latency(dsl: StrategyDSL) -> float:
    graph, _ = compile_dsl(dsl)
    if graph:
        return graph.total_estimated_latency_us
    return 0.0


def get_execution_depth(dsl: StrategyDSL) -> int:
    graph, _ = compile_dsl(dsl)
    return graph.max_depth if graph else 0
