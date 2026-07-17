import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from core.db import get_supabase

logger = logging.getLogger(__name__)

BACKUP_DIR = os.getenv("BACKUP_DIR", "/backups")

EXPORT_TABLES = [
    "profiles",
    "broker_credentials",
    "orders",
    "strategy_assignments",
    "user_strategies",
    "strategy_runs",
    "audit_log",
    "risk_settings",
    "positions_snapshot",
    "subscriptions",
    "referrals",
    "notifications",
    "alerts",
]


class BackupService:
    def _ensure_dir(self):
        os.makedirs(BACKUP_DIR, exist_ok=True)

    def _backup_path(self, name: str) -> str:
        return os.path.join(BACKUP_DIR, name)

    async def run_backup(self) -> dict:
        self._ensure_dir()
        supabase = get_supabase()
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{ts}.json"
        manifest: dict[str, Any] = {
            "meta": {"created_at": datetime.now(UTC).isoformat(), "filename": filename, "tables": {}},
            "data": {},
        }
        total_rows = 0
        for table in EXPORT_TABLES:
            try:
                result = supabase.table(table).select("*").execute()
                rows = result.data or []
                manifest["data"][table] = rows
                manifest["meta"]["tables"][table] = len(rows)
                total_rows += len(rows)
                logger.info("Backed up %s: %d rows", table, len(rows))
            except Exception as e:
                logger.warning("Failed to back up %s: %s", table, e)
                manifest["meta"]["tables"][table] = -1
        manifest["meta"]["total_rows"] = total_rows
        path = self._backup_path(filename)
        with open(path, "w") as f:
            json.dump(manifest, f, default=str, indent=2)
        return {
            "filename": filename,
            "total_rows": total_rows,
            "tables": manifest["meta"]["tables"],
            "size_bytes": os.path.getsize(path),
        }

    async def list_backups(self) -> dict:
        self._ensure_dir()
        backups = []
        for fname in sorted(os.listdir(BACKUP_DIR), reverse=True):
            if not fname.endswith(".json"):
                continue
            fpath = self._backup_path(fname)
            try:
                with open(fpath) as f:
                    meta = json.load(f).get("meta", {})
                backups.append({
                    "filename": fname,
                    "size_bytes": os.path.getsize(fpath),
                    "created_at": meta.get("created_at", ""),
                    "total_rows": meta.get("total_rows", 0),
                    "tables": meta.get("tables", {}),
                })
            except Exception as e:
                backups.append({"filename": fname, "size_bytes": os.path.getsize(fpath), "error": str(e)})
        return {"backups": backups}

    async def delete_backup(self, filename: str) -> dict:
        fpath = self._backup_path(filename)
        if not os.path.exists(fpath):
            raise FileNotFoundError(f"Backup {filename} not found")
        if not filename.endswith(".json") or ".." in filename or "/" in filename:
            raise ValueError("Invalid filename")
        os.remove(fpath)
        return {"deleted": filename}

    async def restore_backup(self, filename: str) -> dict:
        fpath = self._backup_path(filename)
        if not os.path.exists(fpath):
            raise FileNotFoundError(f"Backup {filename} not found")
        if not filename.endswith(".json") or ".." in filename or "/" in filename:
            raise ValueError("Invalid filename")
        with open(fpath) as f:
            manifest = json.load(f)
        supabase = get_supabase()
        results: dict[str, int] = {}
        for table, rows in manifest.get("data", {}).items():
            if not rows:
                continue
            try:
                for row in rows:
                    row_id = row.get("id")
                    if row_id:
                        existing = supabase.table(table).select("id").eq("id", row_id).maybe_single().execute()
                        if existing.data:
                            supabase.table(table).update(row).eq("id", row_id).execute()
                        else:
                            supabase.table(table).insert(row).execute()
                    else:
                        supabase.table(table).insert(row).execute()
                results[table] = len(rows)
            except Exception as e:
                logger.warning("Failed to restore %s: %s", table, e)
                results[table] = -1
        return {
            "restored_from": filename,
            "tables": results,
            "total_rows": sum(v for v in results.values() if v > 0),
        }
