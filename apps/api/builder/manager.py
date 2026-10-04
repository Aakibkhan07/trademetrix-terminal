from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime

from builder.models import (
    GraphEdge,
    GraphNode,
    StrategyDSL,
    StrategyStatus,
)
from builder.templates import STRATEGY_TEMPLATES, TEMPLATE_CATEGORIES
from builder.preview import generate_preview
from core.db import async_supabase, get_supabase

logger = logging.getLogger(__name__)

MAX_VERSIONS = 50

_strategies: dict = {}
_versions: dict = {}
_db_loaded = False


async def _ensure_db() -> None:
    global _db_loaded
    if _db_loaded:
        return
    _db_loaded = True
    try:
        supabase = get_supabase()
        result = await async_supabase(lambda: supabase.table("builder_strategies").select("*").execute())
        for row in result.data or []:
            _strategies[row["id"]] = row
        vres = await async_supabase(lambda: supabase.table("builder_strategy_versions").select("strategy_id,version,data,saved_at").execute())
        by_sid: dict = {}
        for v in vres.data or []:
            by_sid.setdefault(v["strategy_id"], []).append({"version": v["version"], "data": v["data"], "saved_at": v["saved_at"]})
        for sid, vs in by_sid.items():
            _versions[sid] = vs
        if result.data:
            logger.info("BuilderManager loaded %d strategies from DB", len(result.data))
    except Exception as e:
        logger.warning("BuilderManager DB load skipped: %s", e)


_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _owner_of(data: dict) -> str | None:
    """The profile id that owns a stored strategy, or None when it recorded no owner.

    `author` is not an owner column. On production it holds three different kinds of value:
    a real uuid for the 23 rows created through an authenticated request, the literal string
    'user' for the 1144 created without one, and an empty string for some. Reading it as an
    owner and comparing it to a user id is what made every strategy match every tenant.
    `user_id` is the real column; `author` is consulted only where it is uuid-shaped, which
    is the ownership that was recorded before the column existed.
    """
    owner = data.get("user_id")
    if owner:
        return str(owner)
    author = data.get("author") or ""
    return author if _UUID_RE.match(author) else None


def _visible_to(data: dict, user_id: str | None) -> bool:
    """Whether `user_id` may see this strategy.

    `user_id=None` means an internal caller with no tenant context — templates, the builder
    compiling a DSL that was never saved — and those keep the previous behaviour of seeing
    everything. Every authenticated route passes the caller's id, and a strategy with no
    recoverable owner is then visible to nobody, which is the direction that fails closed.
    """
    if user_id is None:
        return True
    owner = _owner_of(data)
    return owner is not None and owner == str(user_id)


async def _persist(data: dict) -> None:
    try:
        supabase = get_supabase()
        row = {k: data.get(k) for k in ("id", "version", "name", "description", "author", "status",
                                        "tags", "settings", "nodes", "edges", "created_at",
                                        "updated_at", "parent_id", "version_number", "deployment",
                                        "user_id")}
        await async_supabase(lambda r=row: supabase.table("builder_strategies").upsert(r, on_conflict="id").execute())
    except Exception as e:
        logger.warning("BuilderManager persist skipped for %s: %s", data.get("id", ""), e)


async def _persist_version(strategy_id: str, version: dict) -> None:
    try:
        supabase = get_supabase()
        row = {"id": f"{strategy_id}::{version['version']}", "strategy_id": strategy_id,
               "version": version["version"], "data": version["data"], "saved_at": version["saved_at"]}
        await async_supabase(lambda r=row: supabase.table("builder_strategy_versions").upsert(r, on_conflict="id").execute())
    except Exception as e:
        logger.warning("BuilderManager version persist skipped for %s: %s", strategy_id, e)


async def _delete_persist(strategy_id: str) -> None:
    try:
        supabase = get_supabase()
        await async_supabase(lambda s=strategy_id: supabase.table("builder_strategy_versions").delete().eq("strategy_id", s).execute())
        await async_supabase(lambda s=strategy_id: supabase.table("builder_strategies").delete().eq("id", s).execute())
    except Exception as e:
        logger.warning("BuilderManager delete persist skipped for %s: %s", strategy_id, e)


def _snapshot_version(strategy_id: str, data: dict) -> None:
    """Append a new version snapshot for a strategy (capped ring)."""
    version = data.get("version_number", 1)
    versions = _versions.setdefault(strategy_id, [])
    versions.append({"version": version, "data": dict(data), "saved_at": data.get("updated_at", "")})
    if len(versions) > MAX_VERSIONS:
        del versions[: len(versions) - MAX_VERSIONS]


class BuilderManager:
    def __init__(self):
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        logger.info("BuilderManager initialized with %d templates", len(STRATEGY_TEMPLATES))
        self._initialized = True

    # ─── CRUD ───

    async def create(
        self,
        name: str = "",
        description: str = "",
        author: str = "user",
        template: str = "",
        owner_id: str | None = None,
    ) -> StrategyDSL:
        """Create a strategy.

        `owner_id` is the authenticated profile that will own it and is what `_visible_to`
        filters on. `author` stays a free-text display value and keeps its historical default
        of the literal 'user', because 1144 production rows carry exactly that and it is read
        as a display field by the strategy list — writing a uuid there would change what the
        list shows without making ownership queryable.
        """
        await _ensure_db()
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
        _strategies[key]["user_id"] = owner_id
        _versions[key] = [{"version": 1, "data": dsl.model_dump(mode="json"), "saved_at": dsl.created_at}]
        await _persist(_strategies[key])
        await _persist_version(key, _versions[key][0])
        return dsl

    async def get(self, strategy_id: str, user_id: str | None = None) -> StrategyDSL | None:
        await _ensure_db()
        data = _strategies.get(strategy_id)
        if data and _visible_to(data, user_id):
            return StrategyDSL(**data)
        return None

    async def update(self, strategy_id: str, updates: dict, user_id: str | None = None) -> StrategyDSL | None:
        await _ensure_db()
        existing = _strategies.get(strategy_id)
        if not existing or not _visible_to(existing, user_id):
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
            elif key == "deployment" and isinstance(val, dict):
                current = existing.get("deployment", {})
                if isinstance(current, dict):
                    merged = {**current, **val}
                    for section in ("risk", "schedule"):
                        if isinstance(val.get(section), dict) and isinstance(current.get(section), dict):
                            merged[section] = {**current[section], **val[section]}
                    existing["deployment"] = merged
                else:
                    existing["deployment"] = val
            else:
                existing[key] = val

        existing["updated_at"] = datetime.now(UTC).isoformat()
        _strategies[strategy_id] = existing
        await _persist(existing)

        # Every save snapshots a new version (v1, v2, v3, ...)
        if updates.get("name") is not None or updates.get("nodes") is not None or updates.get("edges") is not None or updates.get("settings") is not None:
            existing["version_number"] = (existing.get("version_number") or 0) + 1
            _strategies[strategy_id] = existing
            _snapshot_version(strategy_id, existing)
            await _persist(existing)
            await _persist_version(strategy_id, _versions[strategy_id][-1])
        return StrategyDSL(**existing)

    async def delete(self, strategy_id: str, user_id: str | None = None) -> bool:
        await _ensure_db()
        if strategy_id in _strategies and _visible_to(_strategies[strategy_id], user_id):
            del _strategies[strategy_id]
            _versions.pop(strategy_id, None)
            await _delete_persist(strategy_id)
            return True
        return False

    async def list(self, status: str | None = None, user_id: str | None = None) -> list:
        await _ensure_db()
        results = []
        for sid, data in _strategies.items():
            if not _visible_to(data, user_id):
                continue
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

    async def owns(self, strategy_id: str, user_id: str | None) -> bool:
        """Whether `user_id` may act on this strategy.

        The version-history methods read `_versions` directly rather than going through
        `get()`, so they need this to answer the same question.
        """
        await _ensure_db()
        data = _strategies.get(strategy_id)
        return data is not None and _visible_to(data, user_id)

    async def publish(self, strategy_id: str, user_id: str | None = None) -> StrategyDSL | None:
        await _ensure_db()
        dsl = await self.get(strategy_id, user_id)
        if not dsl:
            return None
        dsl.status = StrategyStatus.PUBLISHED
        dsl.updated_at = datetime.now(UTC).isoformat()
        _strategies[strategy_id] = dsl.model_dump(mode="json")
        await _persist(_strategies[strategy_id])
        return dsl

    async def archive(self, strategy_id: str, user_id: str | None = None) -> StrategyDSL | None:
        await _ensure_db()
        dsl = await self.get(strategy_id, user_id)
        if not dsl:
            return None
        dsl.status = StrategyStatus.ARCHIVED
        dsl.updated_at = datetime.now(UTC).isoformat()
        _strategies[strategy_id] = dsl.model_dump(mode="json")
        await _persist(_strategies[strategy_id])
        return dsl

    async def clone(self, strategy_id: str, user_id: str | None = None) -> StrategyDSL | None:
        await _ensure_db()
        original = await self.get(strategy_id, user_id)
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
        await _persist(_strategies[key])
        await _persist_version(key, _versions[key][0])
        return clone

    async def rollback(self, strategy_id: str, version: int, user_id: str | None = None) -> StrategyDSL | None:
        await _ensure_db()
        if not await self.owns(strategy_id, user_id):
            return None
        versions = _versions.get(strategy_id, [])
        target = next((v for v in versions if v["version"] == version), None)
        if not target:
            return None

        dsl = StrategyDSL(**target["data"])
        dsl.version_number = (max(v["version"] for v in versions) + 1) if versions else 1
        dsl.updated_at = datetime.now(UTC).isoformat()

        _strategies[strategy_id] = dsl.model_dump(mode="json")
        _versions[strategy_id].append({"version": dsl.version_number, "data": dsl.model_dump(mode="json"), "saved_at": dsl.updated_at})
        await _persist(_strategies[strategy_id])
        await _persist_version(strategy_id, _versions[strategy_id][-1])
        return dsl

    async def get_versions(self, strategy_id: str, user_id: str | None = None) -> list:
        await _ensure_db()
        if not await self.owns(strategy_id, user_id):
            return []
        return [{"version": v["version"], "saved_at": v["saved_at"], "data": v["data"]} for v in _versions.get(strategy_id, [])]

    async def get_version(self, strategy_id: str, version: int, user_id: str | None = None) -> StrategyDSL | None:
        await _ensure_db()
        if not await self.owns(strategy_id, user_id):
            return None
        target = next((v for v in _versions.get(strategy_id, []) if v["version"] == version), None)
        if not target:
            return None
        return StrategyDSL(**target["data"])

    async def compare(self, strategy_id: str, from_version: int, to_version: int, user_id: str | None = None) -> dict | None:
        await _ensure_db()
        if not await self.owns(strategy_id, user_id):
            return None
        a = await self.get_version(strategy_id, from_version, user_id)
        b = await self.get_version(strategy_id, to_version, user_id)
        if not a or not b:
            return None

        changes: list[dict] = []
        if a.name != b.name:
            changes.append({"field": "name", "kind": "changed", "from": a.name, "to": b.name})
        if a.description != b.description:
            changes.append({"field": "description", "kind": "changed", "from": a.description, "to": b.description})

        nodes_a = {n.id: n for n in a.nodes}
        nodes_b = {n.id: n for n in b.nodes}
        for nid in sorted(set(nodes_a) | set(nodes_b)):
            if nid not in nodes_b:
                changes.append({"field": "nodes", "kind": "removed", "node_id": nid, "block_type": nodes_a[nid].block_type})
            elif nid not in nodes_a:
                changes.append({"field": "nodes", "kind": "added", "node_id": nid, "block_type": nodes_b[nid].block_type})
            else:
                pa, pb = nodes_a[nid].params, nodes_b[nid].params
                for k in sorted(set(pa) | set(pb)):
                    if pa.get(k) != pb.get(k):
                        changes.append({
                            "field": "params", "kind": "changed", "node_id": nid,
                            "block_type": nodes_b[nid].block_type, "param": k,
                            "from": pa.get(k), "to": pb.get(k),
                        })

        edges_a = {(e.source_node, e.source_port, e.target_node, e.target_port) for e in a.edges}
        edges_b = {(e.source_node, e.source_port, e.target_node, e.target_port) for e in b.edges}
        for e in sorted(edges_b - edges_a):
            changes.append({"field": "edges", "kind": "added", "edge": list(e)})
        for e in sorted(edges_a - edges_b):
            changes.append({"field": "edges", "kind": "removed", "edge": list(e)})

        sa, sb = a.settings.model_dump(), b.settings.model_dump()
        for k in sorted(set(sa) | set(sb)):
            if sa.get(k) != sb.get(k):
                changes.append({"field": "settings", "kind": "changed", "param": k, "from": sa.get(k), "to": sb.get(k)})

        return {
            "strategy_id": strategy_id,
            "from_version": from_version,
            "to_version": to_version,
            "summary": {"added": sum(1 for c in changes if c["kind"] == "added"),
                        "removed": sum(1 for c in changes if c["kind"] == "removed"),
                        "changed": sum(1 for c in changes if c["kind"] == "changed")},
            "changes": changes,
        }

    async def set_status(self, strategy_id: str, status: StrategyStatus | str, user_id: str | None = None) -> StrategyDSL | None:
        await _ensure_db()
        dsl = await self.get(strategy_id, user_id)
        if not dsl:
            return None
        dsl.status = status if isinstance(status, StrategyStatus) else StrategyStatus(str(status))
        dsl.updated_at = datetime.now(UTC).isoformat()
        _strategies[strategy_id] = dsl.model_dump(mode="json")
        await _persist(_strategies[strategy_id])
        return dsl

    # ─── Templates ───

    async def list_templates(self) -> list[dict]:
        return [
            {"key": k, "name": t.name, "description": t.description,
             "node_count": len(t.nodes), "tags": t.tags,
             "category": TEMPLATE_CATEGORIES.get(k, "official")}
            for k, t in STRATEGY_TEMPLATES.items()
        ]

    async def get_template(self, template_key: str) -> StrategyDSL | None:
        return STRATEGY_TEMPLATES.get(template_key)

    # ─── Preview ───

    async def preview(self, strategy_id: str, user_id: str | None = None) -> dict:
        dsl = await self.get(strategy_id, user_id)
        if not dsl:
            return {"error": "Strategy not found"}
        return generate_preview(dsl)


builder_manager = BuilderManager()
