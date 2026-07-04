from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from builder.models import (
    GraphEdge,
    GraphNode,
    Position,
    StrategyDSL,
    StrategySettings,
    StrategyStatus,
)
from builder.templates import STRATEGY_TEMPLATES
from builder.preview import generate_preview

logger = logging.getLogger(__name__)

_strategies: dict = {}
_versions: dict = {}


class BuilderManager:
    def __init__(self):
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        logger.info("BuilderManager initialized with %d templates", len(STRATEGY_TEMPLATES))
        self._initialized = True

    # ─── CRUD ───

    async def create(self, name: str = "", description: str = "", author: str = "user", template: str = "") -> StrategyDSL:
        if template and template in STRATEGY_TEMPLATES:
            dsl = STRATEGY_TEMPLATES[template].model_copy(deep=True)
            dsl.id = uuid.uuid4().hex[:12]
            dsl.author = author
            dsl.status = StrategyStatus.DRAFT
            dsl.created_at = datetime.now(UTC).isoformat()
            dsl.updated_at = datetime.now(UTC).isoformat()
            dsl.version_number = 1
            dsl.parent_id = ""
        else:
            dsl = StrategyDSL(
                id=uuid.uuid4().hex[:12],
                name=name or "Untitled Strategy",
                description=description,
                author=author,
                status=StrategyStatus.DRAFT,
                version_number=1,
            )

        key = dsl.id
        _strategies[key] = dsl.model_dump(mode="json")
        _versions[key] = [{"version": 1, "data": dsl.model_dump(mode="json"), "saved_at": dsl.created_at}]
        return dsl

    async def get(self, strategy_id: str) -> StrategyDSL | None:
        data = _strategies.get(strategy_id)
        if data:
            return StrategyDSL(**data)
        return None

    async def update(self, strategy_id: str, updates: dict) -> StrategyDSL | None:
        existing = _strategies.get(strategy_id)
        if not existing:
            return None

        for key, val in updates.items():
            if key in ("id", "created_at"):
                continue
            if key == "settings" and isinstance(val, dict):
                current_settings = existing.get("settings", {})
                if isinstance(current_settings, dict):
                    current_settings.update(val)
                    existing["settings"] = current_settings
                else:
                    existing["settings"] = val
            elif key == "nodes" and isinstance(val, list):
                existing["nodes"] = [n.model_dump() if isinstance(n, GraphNode) else n for n in val]
            elif key == "edges" and isinstance(val, list):
                existing["edges"] = [e.model_dump() if isinstance(e, GraphEdge) else e for e in val]
            else:
                existing[key] = val

        existing["updated_at"] = datetime.now(UTC).isoformat()
        _strategies[strategy_id] = existing
        return StrategyDSL(**existing)

    async def delete(self, strategy_id: str) -> bool:
        if strategy_id in _strategies:
            del _strategies[strategy_id]
            _versions.pop(strategy_id, None)
            return True
        return False

    async def list(self, status: str | None = None) -> list:
        results = []
        for sid, data in _strategies.items():
            if status and data.get("status") != status:
                continue
            results.append({
                "id": sid,
                "name": data.get("name", ""),
                "description": data.get("description", ""),
                "status": data.get("status", "draft"),
                "version": data.get("version_number", 1),
                "author": data.get("author", ""),
                "tags": data.get("tags", []),
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
                "node_count": len(data.get("nodes", [])),
                "edge_count": len(data.get("edges", [])),
            })
        return sorted(results, key=lambda r: r.get("updated_at", ""), reverse=True)

    # ─── Versioning ───

    async def publish(self, strategy_id: str) -> StrategyDSL | None:
        dsl = await self.get(strategy_id)
        if not dsl:
            return None
        dsl.status = StrategyStatus.PUBLISHED
        dsl.updated_at = datetime.now(UTC).isoformat()
        _strategies[strategy_id] = dsl.model_dump(mode="json")
        return dsl

    async def archive(self, strategy_id: str) -> StrategyDSL | None:
        dsl = await self.get(strategy_id)
        if not dsl:
            return None
        dsl.status = StrategyStatus.ARCHIVED
        dsl.updated_at = datetime.now(UTC).isoformat()
        _strategies[strategy_id] = dsl.model_dump(mode="json")
        return dsl

    async def clone(self, strategy_id: str) -> StrategyDSL | None:
        original = await self.get(strategy_id)
        if not original:
            return None

        clone = original.model_copy(deep=True)
        clone.id = uuid.uuid4().hex[:12]
        clone.name = f"{original.name} (Copy)"
        clone.status = StrategyStatus.DRAFT
        clone.parent_id = original.id
        clone.version_number = 1
        clone.created_at = datetime.now(UTC).isoformat()
        clone.updated_at = datetime.now(UTC).isoformat()

        key = clone.id
        _strategies[key] = clone.model_dump(mode="json")
        _versions[key] = [{"version": 1, "data": clone.model_dump(mode="json"), "saved_at": clone.created_at}]
        return clone

    async def rollback(self, strategy_id: str, version: int) -> StrategyDSL | None:
        versions = _versions.get(strategy_id, [])
        target = next((v for v in versions if v["version"] == version), None)
        if not target:
            return None

        dsl = StrategyDSL(**target["data"])
        dsl.version_number = (max(v["version"] for v in versions) + 1) if versions else 1
        dsl.updated_at = datetime.now(UTC).isoformat()

        _strategies[strategy_id] = dsl.model_dump(mode="json")
        _versions[strategy_id].append({"version": dsl.version_number, "data": dsl.model_dump(mode="json"), "saved_at": dsl.updated_at})
        return dsl

    async def get_versions(self, strategy_id: str) -> list:
        return [{"version": v["version"], "saved_at": v["saved_at"]} for v in _versions.get(strategy_id, [])]

    # ─── Templates ───

    async def list_templates(self) -> list[dict]:
        return [
            {"key": k, "name": t.name, "description": t.description,
             "node_count": len(t.nodes), "tags": t.tags}
            for k, t in STRATEGY_TEMPLATES.items()
        ]

    async def get_template(self, template_key: str) -> StrategyDSL | None:
        return STRATEGY_TEMPLATES.get(template_key)

    # ─── Preview ───

    async def preview(self, strategy_id: str) -> dict:
        dsl = await self.get(strategy_id)
        if not dsl:
            return {"error": "Strategy not found"}
        return generate_preview(dsl)


builder_manager = BuilderManager()
