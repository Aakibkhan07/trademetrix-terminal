import json
import logging
from typing import Any

from builder.models import StrategyDSL

logger = logging.getLogger(__name__)


def to_json(dsl: StrategyDSL, indent: int = 2) -> str:
    return dsl.model_dump_json(indent=indent, exclude_none=True)


def from_json(data: str | dict | bytes) -> StrategyDSL:
    if isinstance(data, (str, bytes)):
        parsed = json.loads(data)
    else:
        parsed = data
    return StrategyDSL(**parsed)


def to_dsl_text(dsl: StrategyDSL) -> str:
    lines = []
    lines.append(f"STRATEGY: {dsl.name}")
    lines.append(f"VERSION: {dsl.version}")
    lines.append(f"DESCRIPTION: {dsl.description}")
    lines.append(f"AUTHOR: {dsl.author}")
    lines.append(f"STATUS: {dsl.status.value}")
    lines.append(f"TAGS: {', '.join(dsl.tags)}")
    lines.append("")
    lines.append("[SETTINGS]")
    s = dsl.settings
    lines.append(f"  Symbol: {s.symbol}")
    lines.append(f"  Exchange: {s.exchange}")
    lines.append(f"  Interval: {s.interval}")
    lines.append(f"  Trigger: {s.trigger}")
    lines.append(f"  Max Positions: {s.max_positions}")
    lines.append("")
    lines.append("[BLOCKS]")
    for i, node in enumerate(dsl.nodes):
        lines.append(f"  {i + 1}. [{node.block_type}] (ID: {node.id[:8]}...)")
        if node.params:
            for k, v in node.params.items():
                lines.append(f"       {k} = {v}")
        if node.nested_graph:
            lines.append(f"       [Nested: {len(node.nested_graph.nodes)} blocks]")
    lines.append("")
    lines.append("[CONNECTIONS]")
    for edge in dsl.edges:
        lines.append(f"  {edge.source_node[:8]}...{edge.source_port} → {edge.target_node[:8]}...{edge.target_port}")
    lines.append("")
    lines.append(f"[NODES: {len(dsl.nodes)} | EDGES: {len(dsl.edges)}]")
    return "\n".join(lines)


def from_dsl_text(text: str) -> StrategyDSL | None:
    try:
        lines = text.strip().split("\n")
        name = ""
        description = ""
        author = "user"

        for line in lines:
            if line.startswith("STRATEGY:"):
                name = line.replace("STRATEGY:", "").strip()
            elif line.startswith("DESCRIPTION:"):
                description = line.replace("DESCRIPTION:", "").strip()
            elif line.startswith("AUTHOR:"):
                author = line.replace("AUTHOR:", "").strip()

        dsl = StrategyDSL(name=name, description=description, author=author)
        return dsl
    except Exception as e:
        logger.warning("Failed to parse DSL text: %s", e)
        return None


def validate_import(data: dict) -> tuple[bool, list[str]]:
    errors = []
    if not isinstance(data, dict):
        errors.append("Root must be a JSON object")
        return False, errors

    if "version" not in data:
        errors.append("Missing required field: version")
    if "name" not in data:
        errors.append("Missing required field: name")
    if "nodes" not in data:
        errors.append("Missing required field: nodes")
    elif not isinstance(data["nodes"], list):
        errors.append("'nodes' must be an array")

    if "edges" not in data:
        errors.append("Missing required field: edges")
    elif not isinstance(data["edges"], list):
        errors.append("'edges' must be an array")

    return len(errors) == 0, errors
