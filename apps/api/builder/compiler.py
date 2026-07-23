from __future__ import annotations

import logging
from collections import defaultdict, deque

from builder.blocks import get_block
from builder.models import (
    ExecutionGraph,
    ExecutionNode,
    GraphEdge,
    GraphNode,
    StrategyDSL,
    ValidationIssue,
    ValidationResult,
)

logger = logging.getLogger(__name__)

_LATENCY_LOOKUP: dict[str, float] = {
    "source": 1.0,
    "indicator": 50.0,
    "pattern": 20.0,
    "math": 5.0,
    "logic": 2.0,
    "smc": 100.0,
    "ict": 80.0,
    "greek": 200.0,
    "oi": 30.0,
    "signal": 10.0,
    "order": 5.0,
    "portfolio": 50.0,
    "risk": 20.0,
    "time": 2.0,
    "variable": 5.0,
    "function": 10.0,
    "group": 50.0,
}


def _resolve_block_type(node: GraphNode) -> str:
    return node.block_type


def _get_input_nodes(node_id: str, edges: list[GraphEdge]) -> list[str]:
    incoming = [e for e in edges if e.target_node == node_id]
    return [e.source_node for e in incoming]


def _get_output_nodes(node_id: str, edges: list[GraphEdge]) -> list[str]:
    outgoing = [e for e in edges if e.source_node == node_id]
    return [e.target_node for e in outgoing]


def _topological_sort(nodes: list[GraphNode], edges: list[GraphEdge]) -> tuple[list[str], list[list[str]]]:
    node_ids = {n.id for n in nodes}
    adj: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {n.id: 0 for n in nodes}

    for e in edges:
        if e.source_node in node_ids and e.target_node in node_ids:
            adj[e.source_node].append(e.target_node)
            in_degree[e.target_node] = in_degree.get(e.target_node, 0) + 1

    queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
    sorted_nodes: list[str] = []
    cycles: list[list[str]] = []

    temp_mark: set[str] = set()
    perm_mark: set[str] = set()
    path: list[str] = []

    def _find_cycle(nid: str):
        if nid in perm_mark:
            return
        if nid in temp_mark:
            cycle_start = path.index(nid)
            cycles.append(path[cycle_start:] + [nid])
            return
        temp_mark.add(nid)
        path.append(nid)
        for neighbor in adj.get(nid, []):
            _find_cycle(neighbor)
        path.pop()
        temp_mark.discard(nid)
        perm_mark.add(nid)

    for nid in node_ids:
        if nid not in temp_mark and nid not in perm_mark:
            _find_cycle(nid)

    while queue:
        nid = queue.popleft()
        sorted_nodes.append(nid)
        for neighbor in adj.get(nid, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return sorted_nodes, cycles


def compile_dsl(dsl: StrategyDSL) -> tuple[ExecutionGraph | None, ValidationResult]:
    validation = validate(dsl)
    if not validation.valid and any(i.severity == "error" for i in validation.issues):
        return None, validation

    node_map = {n.id: n for n in dsl.nodes}
    sorted_ids, cycles = _topological_sort(dsl.nodes, dsl.edges)

    if not sorted_ids:
        return None, ValidationResult(
            valid=False,
            issues=[ValidationIssue(severity="error", message="No executable nodes found")],
        )

    exec_nodes: list[ExecutionNode] = []
    entry_points: list[str] = []
    exit_points: list[str] = []
    total_latency = 0.0
    depth_map: dict[str, int] = {}

    for order, nid in enumerate(sorted_ids):
        node = node_map.get(nid)
        if not node:
            continue
        block = get_block(node.block_type)

        input_node_ids = _get_input_nodes(nid, dsl.edges)

        depth = 0
        for inp_id in input_node_ids:
            depth = max(depth, depth_map.get(inp_id, 0) + 1)
        depth_map[nid] = depth

        if not input_node_ids:
            entry_points.append(nid)

        latency = _LATENCY_LOOKUP.get(block.category.value if block else "math", 10.0)
        total_latency += latency

        output_port = "result"
        if block and block.outputs:
            output_port = block.outputs[0].name

        exec_nodes.append(ExecutionNode(
            id=nid,
            block_type=node.block_type,
            category=block.category.value if block else "unknown",
            order=order,
            inputs=input_node_ids,
            output_port=output_port,
            params=node.params,
            compute=node.block_type,
            estimated_latency_us=latency,
        ))

    out_degree = defaultdict(int)
    for e in dsl.edges:
        out_degree[e.source_node] += 1
    for nid in sorted_ids:
        if out_degree.get(nid, 0) == 0:
            exit_points.append(nid)

    max_depth = max(depth_map.values()) if depth_map else 0

    graph = ExecutionGraph(
        nodes=exec_nodes,
        entry_points=entry_points,
        exit_points=exit_points,
        total_estimated_latency_us=round(total_latency, 1),
        max_depth=max_depth,
    )

    return graph, validation


def validate(dsl: StrategyDSL) -> ValidationResult:
    issues: list[ValidationIssue] = []
    cycles: list[list[str]] = []
    missing_inputs: list = []
    type_mismatches: list = []

    node_map = {n.id: n for n in dsl.nodes}

    if not dsl.nodes:
        issues.append(ValidationIssue(severity="error", message="Strategy has no blocks", code="EMPTY_GRAPH"))
        return ValidationResult(valid=False, issues=issues)

    for node in dsl.nodes:
        block = get_block(node.block_type)
        if not block:
            issues.append(ValidationIssue(
                severity="error", node_id=node.id,
                message=f"Unknown block type: {node.block_type}", code="UNKNOWN_BLOCK",
            ))
            continue

        connected_inputs = {e.target_port for e in dsl.edges if e.target_node == node.id}

        for inp in block.inputs:
            if inp.required and inp.name not in connected_inputs and inp.name not in node.params:
                if inp.default is None and not inp.name.startswith("_"):
                    issues.append(ValidationIssue(
                        severity="error", node_id=node.id,
                        message=f"Required input '{inp.label or inp.name}' not connected on {block.name}",
                        code="MISSING_INPUT",
                    ))
                    missing_inputs.append({"node": node.id, "block": block.name, "port": inp.name})

        for param in block.params:
            if param.required and param.name not in node.params:
                if param.default is None:
                    issues.append(ValidationIssue(
                        severity="error", node_id=node.id,
                        message=f"Required parameter '{param.label}' not set on {block.name}",
                        code="MISSING_PARAM",
                    ))

    for edge in dsl.edges:
        if edge.source_node not in node_map:
            issues.append(ValidationIssue(
                severity="error",
                message=f"Edge references unknown source node: {edge.source_node}",
                code="INVALID_EDGE_SOURCE",
            ))
        if edge.target_node not in node_map:
            issues.append(ValidationIssue(
                severity="error",
                message=f"Edge references unknown target node: {edge.target_node}",
                code="INVALID_EDGE_TARGET",
            ))

    _, cycles_found = _topological_sort(dsl.nodes, dsl.edges)
    cycles = cycles_found
    for cycle in cycles_found:
        issues.append(ValidationIssue(
            severity="error",
            message=f"Cycle detected: {' → '.join(cycle)}",
            code="CYCLE_DETECTED",
        ))

    has_signal = any(
        get_block(n.block_type) and get_block(n.block_type).category.value == "order"
        for n in dsl.nodes
    )
    has_input = any(
        get_block(n.block_type) and get_block(n.block_type).category.value == "input"
        for n in dsl.nodes
    )

    if not has_signal:
        issues.append(ValidationIssue(
            severity="warning",
            message="Strategy has no order/signal output block. It will analyze but not trade.",
            code="NO_OUTPUT",
        ))
    if not has_input:
        issues.append(ValidationIssue(
            severity="error",
            message="Strategy has no input blocks (candle, tick, or source). Add a data source.",
            code="NO_INPUT",
        ))

    valid = not any(i.severity == "error" for i in issues)

    return ValidationResult(
        valid=valid,
        issues=issues,
        cycles=cycles,
        missing_inputs=missing_inputs,
        type_mismatches=type_mismatches,
    )


def estimate_latency(block_type: str) -> float:
    block = get_block(block_type)
    if block:
        return _LATENCY_LOOKUP.get(block.category.value, 10.0)
    return 10.0
