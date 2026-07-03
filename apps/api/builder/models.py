import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class BlockCategory(StrEnum):
    INPUT = "input"
    INDICATOR = "indicator"
    PATTERN = "pattern"
    MATH = "math"
    LOGIC = "logic"
    SMC = "smc"
    ICT = "ict"
    GREEK = "greek"
    OI = "oi"
    SIGNAL = "signal"
    ORDER = "order"
    PORTFOLIO = "portfolio"
    RISK = "risk"
    TIME = "time"
    VARIABLE = "variable"
    FUNCTION = "function"
    GROUP = "group"


class DataType(StrEnum):
    NUMBER = "number"
    STRING = "string"
    BOOLEAN = "boolean"
    CANDLE = "candle"
    PRICE = "price"
    SERIES = "series"
    SIGNAL = "signal"
    ORDER = "order"
    POSITION = "position"
    TIME = "time"
    ANY = "any"


class StrategyStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class PortDef(BaseModel):
    name: str
    type: DataType = DataType.ANY
    label: str = ""
    required: bool = True
    default: Any = None
    description: str = ""


class ParamDef(BaseModel):
    name: str
    type: str = "number"
    label: str = ""
    default: Any = None
    options: list[str] | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    description: str = ""
    required: bool = True


class BlockDef(BaseModel):
    type: str
    name: str
    category: BlockCategory
    description: str = ""
    display_name: str = ""
    icon: str = ""
    inputs: list[PortDef] = Field(default_factory=list)
    outputs: list[PortDef] = Field(default_factory=list)
    params: list[ParamDef] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    deprecated: bool = False


class Position(BaseModel):
    x: float = 0
    y: float = 0


class GraphNode(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    block_type: str
    position: Position = Field(default_factory=Position)
    params: dict[str, Any] = Field(default_factory=dict)
    nested_graph: "StrategyDSL | None" = None


class GraphEdge(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    source_node: str
    source_port: str
    target_node: str
    target_port: str


class StrategySettings(BaseModel):
    symbol: str = "NIFTY"
    exchange: str = "NSE"
    interval: str = "15m"
    max_positions: int = 1
    max_risk_per_trade: float = 0.0
    max_daily_trades: int = 0
    trigger: str = "CANDLE_CLOSE"
    require_confirmation: bool = False


class StrategyDSL(BaseModel):
    version: str = "1.0"
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    description: str = ""
    author: str = "user"
    status: StrategyStatus = StrategyStatus.DRAFT
    tags: list[str] = Field(default_factory=list)
    settings: StrategySettings = Field(default_factory=StrategySettings)
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    parent_id: str = ""
    version_number: int = 1


class ExecutionNode(BaseModel):
    id: str
    block_type: str
    category: str
    order: int
    inputs: list[str] = Field(default_factory=list)
    output_port: str = "result"
    params: dict[str, Any] = Field(default_factory=dict)
    compute: str = ""
    estimated_latency_us: float = 0.0


class ExecutionGraph(BaseModel):
    nodes: list[ExecutionNode] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)
    exit_points: list[str] = Field(default_factory=list)
    total_estimated_latency_us: float = 0.0
    max_depth: int = 0


class ValidationIssue(BaseModel):
    severity: str = "error"
    node_id: str = ""
    message: str = ""
    code: str = ""


class ValidationResult(BaseModel):
    valid: bool = True
    issues: list[ValidationIssue] = Field(default_factory=list)
    cycles: list[list[str]] = Field(default_factory=list)
    missing_inputs: list[dict] = Field(default_factory=list)
    type_mismatches: list[dict] = Field(default_factory=list)


class PreviewData(BaseModel):
    execution_order: list[dict] = Field(default_factory=list)
    total_latency_us: float = 0.0
    max_depth: int = 0
    node_count: int = 0
    edge_count: int = 0
    graph: ExecutionGraph | None = None
    validation: ValidationResult = Field(default_factory=ValidationResult)
    warnings: list[str] = Field(default_factory=list)
