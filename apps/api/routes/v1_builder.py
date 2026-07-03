import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from builder.blocks import list_blocks, list_categories, get_block, BLOCK_DEFINITIONS
from builder.compiler import compile_dsl
from builder.io import to_json, from_json, to_dsl_text, validate_import
from builder.manager import builder_manager
from builder.models import (
    GraphEdge,
    GraphNode,
    StrategyDSL,
    StrategySettings,
    StrategyStatus,
)
from builder.preview import generate_preview
from builder.templates import STRATEGY_TEMPLATES
from core.deps import get_current_user
from core.models import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/builder", tags=["builder"])


class CreateStrategyRequest(BaseModel):
    name: str = ""
    description: str = ""
    template: str = ""


class UpdateStrategyRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    nodes: list[dict] | None = None
    edges: list[dict] | None = None
    settings: dict | None = None
    tags: list[str] | None = None


@router.get("/blocks")
async def list_builder_blocks(category: str | None = None):
    blocks = list_blocks()
    result = []
    for b in blocks:
        result.append({
            "type": b.type,
            "name": b.name,
            "category": b.category.value,
            "description": b.description,
            "inputs": [{"name": i.name, "type": i.type.value, "label": i.label, "required": i.required} for i in b.inputs],
            "outputs": [{"name": o.name, "type": o.type.value, "label": o.label} for o in b.outputs],
            "params": [{"name": p.name, "type": p.type, "label": p.label, "default": p.default, "options": p.options} for p in b.params],
        })
    return {"blocks": result, "total": len(result)}


@router.get("/blocks/categories")
async def list_builder_categories():
    return {"categories": list_categories()}


@router.get("/blocks/{block_type}")
async def get_builder_block(block_type: str):
    block = get_block(block_type)
    if not block:
        raise HTTPException(status_code=404, detail=f"Block type not found: {block_type}")
    return block


# ─── CRUD ───

@router.post("/strategies")
async def create_strategy(
    req: CreateStrategyRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    dsl = await builder_manager.create(
        name=req.name,
        description=req.description,
        author=current_user.id,
        template=req.template,
    )
    return dsl.model_dump(mode="json", exclude_none=True)


@router.get("/strategies")
async def list_strategies(status: str | None = None):
    strategies = await builder_manager.list(status=status)
    return {"strategies": strategies, "total": len(strategies)}


@router.get("/strategies/{strategy_id}")
async def get_strategy(strategy_id: str):
    dsl = await builder_manager.get(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return dsl.model_dump(mode="json", exclude_none=True)


@router.put("/strategies/{strategy_id}")
async def update_strategy(strategy_id: str, req: UpdateStrategyRequest):
    updates = {}
    if req.name is not None:
        updates["name"] = req.name
    if req.description is not None:
        updates["description"] = req.description
    if req.nodes is not None:
        updates["nodes"] = [GraphNode(**n) for n in req.nodes]
    if req.edges is not None:
        updates["edges"] = [GraphEdge(**e) for e in req.edges]
    if req.settings is not None:
        updates["settings"] = StrategySettings(**req.settings)
    if req.tags is not None:
        updates["tags"] = req.tags

    dsl = await builder_manager.update(strategy_id, updates)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return dsl.model_dump(mode="json", exclude_none=True)


@router.delete("/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str):
    success = await builder_manager.delete(strategy_id)
    if not success:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"status": "deleted"}


# ─── Compile ───

@router.post("/strategies/{strategy_id}/compile")
async def compile_strategy(strategy_id: str):
    dsl = await builder_manager.get(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")

    graph, validation = compile_dsl(dsl)
    if not graph:
        raise HTTPException(
            status_code=400,
            detail={"error": "Compilation failed", "issues": [i.model_dump() for i in validation.issues]},
        )

    return {
        "strategy_id": strategy_id,
        "compiled": True,
        "node_count": len(graph.nodes),
        "total_estimated_latency_us": graph.total_estimated_latency_us,
        "max_depth": graph.max_depth,
        "execution_order": [
            {"order": n.order, "block_type": n.block_type, "id": n.id, "latency_us": n.estimated_latency_us}
            for n in graph.nodes
        ],
        "validation": {
            "valid": validation.valid,
            "issues": [i.model_dump() for i in validation.issues],
        },
    }


# ─── Validate ───

@router.post("/strategies/{strategy_id}/validate")
async def validate_strategy(strategy_id: str):
    dsl = await builder_manager.get(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")

    _, validation = compile_dsl(dsl)
    return {
        "strategy_id": strategy_id,
        "valid": validation.valid,
        "issues": [i.model_dump() for i in validation.issues],
        "cycles": validation.cycles,
    }


# ─── Preview ───

@router.get("/strategies/{strategy_id}/preview")
async def preview_strategy(strategy_id: str):
    preview = await builder_manager.preview(strategy_id)
    if "error" in preview:
        raise HTTPException(status_code=404, detail=preview["error"])
    return preview


# ─── Versioning ───

@router.post("/strategies/{strategy_id}/publish")
async def publish_strategy(strategy_id: str):
    dsl = await builder_manager.publish(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"status": "published", "strategy_id": strategy_id}


@router.post("/strategies/{strategy_id}/archive")
async def archive_strategy(strategy_id: str):
    dsl = await builder_manager.archive(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"status": "archived", "strategy_id": strategy_id}


@router.post("/strategies/{strategy_id}/clone")
async def clone_strategy(strategy_id: str):
    dsl = await builder_manager.clone(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return dsl.model_dump(mode="json", exclude_none=True)


@router.post("/strategies/{strategy_id}/rollback/{version}")
async def rollback_strategy(strategy_id: str, version: int):
    dsl = await builder_manager.rollback(strategy_id, version)
    if not dsl:
        raise HTTPException(status_code=404, detail="Version not found")
    return dsl.model_dump(mode="json", exclude_none=True)


@router.get("/strategies/{strategy_id}/versions")
async def get_strategy_versions(strategy_id: str):
    versions = await builder_manager.get_versions(strategy_id)
    return {"versions": versions}


# ─── Templates ───

@router.get("/templates")
async def list_templates():
    templates = await builder_manager.list_templates()
    return {"templates": templates, "total": len(templates)}


@router.get("/templates/{template_key}")
async def get_template(template_key: str):
    dsl = await builder_manager.get_template(template_key)
    if not dsl:
        raise HTTPException(status_code=404, detail="Template not found")
    return dsl.model_dump(mode="json", exclude_none=True)


# ─── Import / Export ───

@router.post("/import")
async def import_strategy(data: dict):
    valid, errors = validate_import(data)
    if not valid:
        raise HTTPException(status_code=400, detail={"error": "Invalid import data", "details": errors})
    try:
        dsl = from_json(data)
        existing = await builder_manager.get(dsl.id)
        if existing:
            dsl.id = __import__("uuid").uuid4().hex[:12]
        await builder_manager.update(dsl.id, dsl.model_dump())
        return dsl.model_dump(mode="json", exclude_none=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Import failed: {str(e)}")


@router.get("/strategies/{strategy_id}/export")
async def export_strategy(strategy_id: str, format: str = "json"):
    dsl = await builder_manager.get(strategy_id)
    if not dsl:
        raise HTTPException(status_code=404, detail="Strategy not found")

    if format == "dsl":
        return {"format": "dsl", "content": to_dsl_text(dsl)}
    return dsl.model_dump(mode="json", exclude_none=True)
