import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

import application.services.backup_service
from core.notifications import send_admin_notification_email
from application.services.admin_service import AdminService
from core.deps import require_admin, require_super_admin
from core.models import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

_service = AdminService()
_backup = application.services.backup_service.BackupService()


def _validate_backup_filename(filename: str) -> None:
    if ".." in filename or "/" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid backup filename")


@router.get("/backups")
async def admin_list_backups(admin: UserProfile = Depends(require_super_admin)):
    return await _backup.list_backups()


@router.post("/backups/run")
async def admin_run_backup(admin: UserProfile = Depends(require_super_admin)):
    return await _backup.run_backup()


@router.post("/backups/restore/{filename}")
async def admin_restore_backup(
    filename: str,
    admin: UserProfile = Depends(require_super_admin),
):
    _validate_backup_filename(filename)
    return await _backup.restore_backup(filename)


@router.delete("/backups/{filename}")
async def admin_delete_backup(
    filename: str,
    admin: UserProfile = Depends(require_super_admin),
):
    _validate_backup_filename(filename)
    return await _backup.delete_backup(filename)


class KillSwitchRequest(BaseModel):
    enabled: bool = True


@router.post("/kill-switch")
async def admin_kill_switch(
    req: KillSwitchRequest,
    admin: UserProfile = Depends(require_super_admin),
):
    import logging
    log = logging.getLogger(__name__)
    try:
        if req.enabled:
            return await _service.enable_kill_switch()
        return await _service.disable_kill_switch()
    except Exception as e:
        log.error("Kill switch operation failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Kill switch operation failed: {e}")


@router.post("/resume-trading")
async def admin_resume_trading(
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.disable_kill_switch()


@router.get("/kill-switch")
async def admin_get_kill_switch(
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.get_kill_switch()


@router.get("/stats")
async def admin_stats(admin: UserProfile = Depends(require_admin)):
    return await _service.get_stats()


@router.get("/users")
async def admin_list_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: UserProfile = Depends(require_admin),
):
    return await _service.list_users(limit=limit, offset=offset)
