"""Runtime Persistence + Recovery (Execution Engine add-on).

Durably checkpoints the minimum required paper-trading runtime state so it
survives process restarts without touching the Broker SDK or the Execution
Engine architecture (the engine already documents attached-store protocols;
this module is that adapter, wiring itself onto the canonical bus additively):

- ``engine``    — open positions + FIFO lots + P&L accounts per user, written
                  after every portfolio rebuild (PORTFOLIO_SNAPSHOT event).
- ``strategy``  — running graph strategies (params needed to restart them),
                  written by the graph runner on start, removed on stop.

``recover_runtime_state`` restores engine accounting state first (positions,
lots, P&L accounts, portfolio snapshot), then re-starts every persisted running
strategy. Recovery is deterministic (canonical JSON round-trip), idempotent
(replace-in-place; ``already_running`` guard) and fail-open (a broken store
never blocks the engine or startup).

Backend is the ``execution_checkpoints`` table (Supabase); a store is injected
at runtime (:func:`enable_execution_persistence`), so tests (and engines with
no durable store) run untouched with persistence as a no-op.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

KIND_ENGINE = "engine"
KIND_STRATEGY = "strategy"
ENGINE_KEY = "all"
CHECKPOINT_VERSION = 1

_TABLE = "execution_checkpoints"


class CheckpointStore:
    """Durable backend for engine checkpoints.

    Same surface is implemented by :class:`InMemoryCheckpointStore` (tests)
    and by the Supabase adapter (:class:`SupabaseCheckpointStore`).
    """

    async def load(
        self,
        kind: str,
        user_id: str | None = None,
        key: str | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def upsert(self, user_id: str, kind: str, key: str, data: dict[str, Any]) -> None:
        raise NotImplementedError

    async def delete(self, user_id: str, kind: str, key: str) -> None:
        raise NotImplementedError


class SupabaseCheckpointStore(CheckpointStore):
    """Upsert-style adapter over the ``execution_checkpoints`` table.

    Read-then-insert-or-update keeps writes idempotent and reuses the
    fail-open query helpers (``core.safe_query``), so a Supabase outage never
    raises out of the engine.
    """

    def __init__(self, table: str = _TABLE) -> None:
        self._table = table

    async def load(
        self,
        kind: str,
        user_id: str | None = None,
        key: str | None = None,
    ) -> list[dict[str, Any]]:
        from core.safe_query import async_safe_execute
        from core.db import get_supabase

        query = get_supabase().table(self._table).select("*").eq("kind", kind)
        if user_id:
            query = query.eq("user_id", user_id)
        if key:
            query = query.eq("key", key)
        rows = await async_safe_execute(query) or []
        return [self._parse_row(r) for r in rows]

    @staticmethod
    def _parse_row(row: dict[str, Any]) -> dict[str, Any]:
        data = row.get("data")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}
        return {
            "user_id": row.get("user_id", ""),
            "kind": row.get("kind", ""),
            "key": row.get("key", ""),
            "data": data or {},
            "updated_at": row.get("updated_at"),
        }

    async def upsert(self, user_id: str, kind: str, key: str, data: dict[str, Any]) -> None:
        from core.safe_query import async_safe_execute
        from core.db import get_supabase

        table = get_supabase().table(self._table)
        existing = await async_safe_execute(
            table.select("*").eq("user_id", user_id).eq("kind", kind).eq("key", key)
        ) or []
        now = datetime.now(timezone.utc).isoformat()
        body = {"user_id": user_id, "kind": kind, "key": key, "data": data, "updated_at": now}
        if existing:
            await async_safe_execute(
                get_supabase().table(self._table)
                .update(body)
                .eq("user_id", user_id)
                .eq("kind", kind)
                .eq("key", key)
            )
        else:
            await async_safe_execute(get_supabase().table(self._table).insert(body))

    async def delete(self, user_id: str, kind: str, key: str) -> None:
        from core.safe_query import async_safe_execute
        from core.db import get_supabase

        await async_safe_execute(
            get_supabase().table(self._table)
            .delete()
            .eq("user_id", user_id)
            .eq("kind", kind)
            .eq("key", key)
        )


class InMemoryCheckpointStore(CheckpointStore):
    """Deterministic test store: a plain dict, no I/O."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str, str], dict[str, Any]] = {}

    async def load(self, kind, user_id=None, key=None):
        out = []
        for (uid, kd, ky), row in self._rows.items():
            if kind != kd:
                continue
            if user_id and uid != user_id:
                continue
            if key and ky != key:
                continue
            out.append({"user_id": uid, "kind": kd, "key": ky, "data": dict(row), "updated_at": None})
        out.sort(key=lambda r: (r["user_id"], r["key"]))
        return out

    async def upsert(self, user_id, kind, key, data):
        self._rows[(user_id, kind, key)] = json.loads(json.dumps(data, sort_keys=True))

    async def delete(self, user_id, kind, key):
        self._rows.pop((user_id, kind, key), None)


# --------------------------------------------------------------------------- #
class _EnginePersistence:
    """Event-driven checkpoint writer + deterministic recovery.

    One process-wide instance (``runtime_persistence``). No-op until a store
    is set via :func:`enable_execution_persistence`.
    """

    def __init__(self) -> None:
        self._store: CheckpointStore | None = None
        self._installed = False
        self._last_hash: dict[str, str] = {}
        self._lock = asyncio.Lock()

    # -- setup ---------------------------------------------------------------
    def configure(self, store: CheckpointStore | None) -> None:
        self._store = store
        self._last_hash.clear()

    def install(self) -> None:
        """Subscribe to the canonical PORTFOLIO domain (idempotent)."""
        if self._installed:
            return
        try:
            from execution_engine.events import (
                ExecutionDomain,
                ExecutionEventType,
                execution_bus,
            )

            def _handler(event: Any) -> None:
                if event.type == ExecutionEventType.PORTFOLIO_SNAPSHOT and event.user_id:
                    self.persist_engine_nowait(event.user_id)

            execution_bus.subscribe(ExecutionDomain.PORTFOLIO, _handler)
            self._installed = True
            logger.debug("Runtime persistence coordinator wired to PORTFOLIO domain")
        except Exception as e:  # pragma: no cover
            logger.warning("Runtime persistence install skipped: %s", e)

    # ------------------------------------------------------------------
    # Engine checkpoints
    # ------------------------------------------------------------------
    def persist_engine_nowait(self, user_id: str) -> None:
        try:
            asyncio.get_running_loop().create_task(self.persist_engine(user_id))
        except RuntimeError:
            logger.debug("No running loop; engine checkpoint skipped for %s", user_id)

    async def persist_engine(self, user_id: str) -> None:
        store = self._store
        if store is None:
            return
        state = self._dump_engine_state(user_id)
        if not state["positions"] and not state["accounts"]:
            return
        payload = json.dumps(state, sort_keys=True)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        async with self._lock:
            if self._last_hash.get(user_id) == digest:
                return
            try:
                await store.upsert(user_id, KIND_ENGINE, ENGINE_KEY, state)
                self._last_hash[user_id] = digest
                logger.debug("Engine checkpoint written for user=%s (%d B)", user_id, len(payload))
            except Exception as e:  # fail-open
                logger.warning("Engine checkpoint write failed for user=%s: %s", user_id, e)

    def _dump_engine_state(self, user_id: str) -> dict[str, Any]:
        from execution_engine import pnl_engine, position_manager

        positions = position_manager.get_positions(user_id)
        accounts = pnl_engine.get_accounts(user_id)

        return {
            "version": CHECKPOINT_VERSION,
            "user_id": user_id,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "positions": [
                p.model_dump(mode="json")
                for p in sorted(positions, key=lambda p: (p.broker, p.symbol))
            ],
            "fifos": self._dump_fifos(user_id),
            "accounts": [
                a.model_dump(mode="json")
                for a in sorted(accounts, key=lambda a: a.broker)
            ],
        }

    def _dump_fifos(self, user_id: str) -> dict[str, dict[str, list[list[float]]]]:
        from execution_engine import position_manager

        out: dict[str, dict[str, list[list[float]]]] = {}
        with position_manager._lock:
            prefix = f"{user_id}:"
            for key, fifo in position_manager._fifos.items():
                if key.startswith(prefix):
                    out[key] = fifo.to_lots()
        return dict(sorted(out.items()))

    # ------------------------------------------------------------------
    # Restore (deterministic: replace-in-place, no events replayed)
    # ------------------------------------------------------------------
    def restore_user_state(self, user_id: str, data: dict[str, Any]) -> dict[str, int]:
        from execution_engine import pnl_engine, position_manager
        from execution_engine.fifo import FifoLots
        from execution_engine.pnl import PnLAccount
        from execution_engine.portfolio_engine import portfolio_engine
        from execution_engine.positions import EnginePosition

        restored = {"positions": 0, "accounts": 0}
        with position_manager._lock:
            for pos in data.get("positions", []):
                if pos.get("user_id") != user_id:
                    continue
                key = position_manager._key(
                    user_id, str(pos.get("broker", "")), str(pos.get("symbol", ""))
                )
                position_manager._positions[key] = EnginePosition(**pos)
                restored["positions"] += 1
            for key, lots in (data.get("fifos") or {}).items():
                if key.startswith(f"{user_id}:"):
                    position_manager._fifos[key] = FifoLots.from_lots(lots)

        with pnl_engine._lock:
            for acc in data.get("accounts", []):
                if acc.get("user_id") != user_id:
                    continue
                key = pnl_engine._key(user_id, str(acc.get("broker", "")))
                pnl_engine._accounts[key] = PnLAccount(**acc)
                restored["accounts"] += 1

        try:
            portfolio_engine.rebuild(user_id)
        except Exception as e:
            logger.warning("Portfolio rebuild after restore failed for %s: %s", user_id, e)
        return restored

    # ------------------------------------------------------------------
    # Strategy checkpoints (called by the graph runner)
    # ------------------------------------------------------------------
    async def persist_strategy(self, strategy_id: str) -> None:
        store = self._store
        if store is None:
            return
        try:
            from engine.graph_strategy_runner import _runtime_stats

            stats = _runtime_stats(strategy_id)
            user_id = stats.get("user_id", "")
            if not user_id or stats.get("status") != "running":
                return
            body = {
                "strategy_id": strategy_id,
                "user_id": user_id,
                "symbol": stats.get("symbol", ""),
                "interval": stats.get("interval", "15m"),
                "mode": stats.get("mode", "paper"),
                "is_paper": stats.get("mode", "paper") != "live",
                "started_at": stats.get("started_at", ""),
            }
            await store.upsert(user_id, KIND_STRATEGY, strategy_id, body)
            logger.info("Strategy checkpoint written for %s", strategy_id)
        except Exception as e:
            logger.warning("Strategy checkpoint failed for %s: %s", strategy_id, e)

    async def delete_strategy(self, strategy_id: str) -> None:
        store = self._store
        if store is None:
            return
        try:
            from engine.graph_strategy_runner import _runtime_stats

            user_id = _runtime_stats(strategy_id).get("user_id", "")
            if not user_id:
                return
            await store.delete(user_id, KIND_STRATEGY, strategy_id)
        except Exception as e:
            logger.warning("Strategy checkpoint delete failed for %s: %s", strategy_id, e)


# ------------------------------------------------------------------
    # Recovery loaders (fail-open: None store / unreadable store -> empty)
    # ------------------------------------------------------------------
    async def _store_load(self, kind: str) -> list[dict[str, Any]]:
        store = self._store
        if store is None:
            return []
        try:
            return await store.load(kind)
        except Exception as e:
            logger.warning("Checkpoints unreadable (recovery skipped for kind=%s): %s", kind, e)
            return []


runtime_persistence = _EnginePersistence()


def enable_execution_persistence(store: CheckpointStore | None) -> None:
    """Point production persistence at the durable backend (idempotent)."""
    runtime_persistence.configure(store)


# --------------------------------------------------------------------------- #
def dump_engine_state(user_id: str) -> dict[str, Any]:
    """Canonical engine checkpoint body (exposed for tests/ops)."""
    return runtime_persistence._dump_engine_state(user_id)


def restore_engine_state(user_id: str, data: dict[str, Any]) -> dict[str, int]:
    """Restore engine accounting state for one user (exposed for tests/ops)."""
    return runtime_persistence.restore_user_state(user_id, data)


async def recover_runtime_state() -> dict[str, Any]:
    """Restore persisted paper-trading state after a process restart.

    Order matters: engine accounting state first (positions/lots/P&L + a
    rebuilt portfolio snapshot), then running strategies (whose fills feed the
    already-restored book). Deterministic + idempotent + fail-open.
    """
    result: dict[str, Any] = {
        "engine_users": 0,
        "positions": 0,
        "accounts": 0,
        "strategies": 0,
        "strategy_skips": [],
    }
    try:
        for row in await runtime_persistence._store_load(KIND_ENGINE):
            user_id = row["user_id"]
            counts = runtime_persistence.restore_user_state(user_id, row["data"])
            result["engine_users"] += 1
            result["positions"] += counts["positions"]
            result["accounts"] += counts["accounts"]
        if result["engine_users"]:
            logger.info(
                "Engine runtime recovered: %d user(s), %d positions, %d accounts",
                result["engine_users"], result["positions"], result["accounts"],
            )

        from engine.graph_strategy_runner import start_graph_strategy

        for row in await runtime_persistence._store_load(KIND_STRATEGY):
            spec = row["data"]
            sid = spec.get("strategy_id") or row.get("key", "")
            if not sid or not spec.get("user_id"):
                continue
            try:
                outcome = await start_graph_strategy(
                    strategy_id=sid,
                    user_id=spec["user_id"],
                    symbol=spec.get("symbol") or "NIFTY",
                    interval=spec.get("interval") or "15m",
                    is_paper=bool(spec.get("is_paper", spec.get("mode", "paper") != "live")),
                )
                if outcome == "already_running":
                    result["strategy_skips"].append(sid)
                else:
                    result["strategies"] += 1
                    logger.info("Runtime recovery restarted strategy %s (%s)", sid, outcome)
            except Exception as e:
                logger.warning("Runtime recovery failed to restart strategy %s: %s", sid, e)
                result["strategy_skips"].append(sid)
        if result["strategies"]:
            logger.info(
                "Runtime strategies restarted: %d (skipped %d already-running)",
                result["strategies"], len(result["strategy_skips"]),
            )
    except Exception as e:  # recovery must never block startup
        logger.warning("Runtime recovery aborted (non-fatal): %s", e)
    return result