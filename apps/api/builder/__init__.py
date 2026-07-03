from strategies import register_strategy

from builder.blocks import BLOCK_DEFINITIONS, list_blocks, list_categories, get_block
from builder.compiler import compile_dsl, validate
from builder.io import to_json, from_json, to_dsl_text, from_dsl_text, validate_import
from builder.manager import builder_manager
from builder.models import (
    BlockCategory,
    BlockDef,
    DataType,
    ExecutionGraph,
    ExecutionNode,
    GraphEdge,
    GraphNode,
    PortDef,
    ParamDef,
    PreviewData,
    StrategyDSL,
    StrategySettings,
    StrategyStatus,
    ValidationIssue,
    ValidationResult,
)
from builder.preview import generate_preview
from builder.strategy import GraphStrategy
from builder.templates import STRATEGY_TEMPLATES

register_strategy("graph_strategy", GraphStrategy)

__all__ = [
    "BLOCK_DEFINITIONS",
    "list_blocks",
    "list_categories",
    "get_block",
    "compile_dsl",
    "validate",
    "to_json",
    "from_json",
    "to_dsl_text",
    "from_dsl_text",
    "validate_import",
    "builder_manager",
    "generate_preview",
    "GraphStrategy",
    "STRATEGY_TEMPLATES",
    "BlockCategory",
    "BlockDef",
    "DataType",
    "ExecutionGraph",
    "ExecutionNode",
    "GraphEdge",
    "GraphNode",
    "PortDef",
    "ParamDef",
    "PreviewData",
    "StrategyDSL",
    "StrategySettings",
    "StrategyStatus",
    "ValidationIssue",
    "ValidationResult",
]
