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


class KillSwitchRequest(BaseModel):
    enabled: bool = True


class UpdateTierRequest(BaseModel):
    subscription_tier: str


class CreateAssignmentRequest(BaseModel):
    user_id: str
    strategy_key: str


class BatchAssignRequest(BaseModel):
    user_ids: list[str]
    strategy_key: str


class ImportAssignmentsRequest(BaseModel):
    entries: list[dict]


class BroadcastNotifyRequest(BaseModel):
    title: str
    message: str
    type: str | None = None
    user_ids: list[str] | None = None


class CreateAdminRequest(BaseModel):
    email: str
    role: str


class UpdateAdminRoleRequest(BaseModel):
    role: str


class BroadcastSendRequest(BaseModel):
    strategy_key: str
    symbol: str
    action: str
    quantity: int
    price: float | None = None
    exchange: str | None = None
    order_type: str | None = None
    product: str | None = None
    reason: str | None = None
    paper: bool = True


class CreateStrategyRequest(BaseModel):
    key: str
    name: str
    description: str | None = None
    required_tier: str | None = None
    category: str | None = None


class UpdateStrategyRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    required_tier: str | None = None
    category: str | None = None


class ExecuteTradeRequest(BaseModel):
    user_id: str
    symbol: str
    side: str
    quantity: int
    price: float | None = None
    exchange: str | None = None
    order_type: str | None = None
    product: str | None = None
    trigger_price: float | None = None
    instrument_type: str | None = None
    expiry_date: str | None = None
    strike_price: float | None = None
    option_type: str | None = None


# ── Backups ──

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


# ── Kill Switch ──

@router.post("/kill-switch")
async def admin_kill_switch(
    req: KillSwitchRequest,
    admin: UserProfile = Depends(require_super_admin),
):
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


# ── Stats & Users ──

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


@router.patch("/users/{user_id}")
async def admin_update_user_tier(
    user_id: str,
    req: UpdateTierRequest,
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.update_user_tier(user_id, req.subscription_tier, admin.id)


# ── Assignments ──

@router.get("/assignments")
async def admin_list_assignments(
    user_id: str = Query(""),
    admin: UserProfile = Depends(require_admin),
):
    return await _service.list_assignments(user_id=user_id)


@router.post("/assignments")
async def admin_create_assignment(
    req: CreateAssignmentRequest,
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.assign_strategy(req.user_id, req.strategy_key, admin.id)


@router.delete("/assignments/{assignment_id}")
async def admin_remove_assignment(
    assignment_id: str,
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.unassign_strategy(assignment_id, admin.id)


@router.post("/assignments/batch")
async def admin_batch_assign(
    req: BatchAssignRequest,
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.batch_assign(req.user_ids, req.strategy_key, admin.id)


@router.get("/assignments/export")
async def admin_export_assignments(
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.export_assignments()


@router.post("/assignments/import")
async def admin_import_assignments(
    req: ImportAssignmentsRequest,
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.import_assignments(req.entries, admin.id)


# ── Brokers ──

@router.get("/brokers")
async def admin_list_brokers(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: UserProfile = Depends(require_admin),
):
    return await _service.list_brokers(limit=limit, offset=offset)


@router.post("/brokers/fyers/validate")
async def admin_fyers_validate(
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.validate_fyers_tokens()


@router.post("/brokers/fyers/re-auth/{credential_id}")
async def admin_fyers_re_auth(
    credential_id: str,
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.fyers_re_auth(credential_id, admin.id)


# ── Orders, Positions, Audit ──

@router.get("/orders")
async def admin_list_orders(
    user_id: str = Query(""),
    is_paper: str = Query(""),
    symbol: str = Query(""),
    from_date: str = Query(""),
    to_date: str = Query(""),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: UserProfile = Depends(require_admin),
):
    return await _service.list_orders(
        user_id=user_id, is_paper=is_paper, symbol=symbol,
        from_date=from_date, to_date=to_date, limit=limit, offset=offset,
    )


@router.get("/positions")
async def admin_list_positions(
    user_id: str = Query(""),
    admin: UserProfile = Depends(require_admin),
):
    return await _service.list_positions(user_id=user_id)


@router.get("/audit-log")
async def admin_get_audit_log(
    user_id: str = Query(""),
    action: str = Query(""),
    from_date: str = Query(""),
    to_date: str = Query(""),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: UserProfile = Depends(require_admin),
):
    return await _service.get_audit_log(
        user_id=user_id, action=action,
        from_date=from_date, to_date=to_date, limit=limit, offset=offset,
    )


# ── Risk, Active Brokers ──

@router.get("/risk")
async def admin_get_risk_overview(
    admin: UserProfile = Depends(require_admin),
):
    return await _service.get_risk_overview()


@router.get("/active-brokers")
async def admin_get_active_brokers(
    admin: UserProfile = Depends(require_admin),
):
    return await _service.get_active_brokers_count()


# ── Admins ──

@router.get("/admins")
async def admin_list_admins(
    admin: UserProfile = Depends(require_admin),
):
    return await _service.list_admins()


@router.post("/admins")
async def admin_create_admin(
    req: CreateAdminRequest,
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.create_admin(req.email, req.role, admin.id)


@router.patch("/admins/{user_id}")
async def admin_update_admin_role(
    user_id: str,
    req: UpdateAdminRoleRequest,
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.update_admin_role(user_id, req.role, admin.id)


@router.delete("/admins/{user_id}")
async def admin_remove_admin(
    user_id: str,
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.remove_admin(user_id, admin.id)


# ── Broadcast ──

@router.get("/broadcast/recipients")
async def admin_broadcast_recipients(
    strategy_key: str = Query(...),
    admin: UserProfile = Depends(require_admin),
):
    return await _service.get_broadcast_recipients(strategy_key)


@router.post("/broadcast")
async def admin_broadcast_send(
    req: BroadcastSendRequest,
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.broadcast(
        req.strategy_key, req.symbol, req.action, req.quantity, req.price or 0,
        req.exchange or "NSE", req.order_type or "MARKET", req.product or "INTRADAY",
        req.reason or "", req.paper,
    )


@router.post("/broadcast/notify")
async def admin_broadcast_notify(
    req: BroadcastNotifyRequest,
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.notify_broadcast(req.title, req.message, req.type or "info", req.user_ids, admin.id)


# ── Strategies ──

@router.get("/strategies")
async def admin_list_strategies(
    admin: UserProfile = Depends(require_admin),
):
    return await _service.list_catalog_strategies()


@router.post("/strategies")
async def admin_create_strategy(
    req: CreateStrategyRequest,
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.create_catalog_strategy(req.key, req.name, req.description or "", req.required_tier or "free", req.category or "", admin.id)


@router.put("/strategies/{key}")
async def admin_update_strategy(
    key: str,
    req: UpdateStrategyRequest,
    admin: UserProfile = Depends(require_super_admin),
):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    return await _service.update_catalog_strategy(key, updates, admin.id)


@router.delete("/strategies/{key}")
async def admin_delete_strategy(
    key: str,
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.delete_catalog_strategy(key, admin.id)


# ── Execute Trade ──

@router.post("/execute-trade")
async def admin_execute_trade(
    req: ExecuteTradeRequest,
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.execute_trade_for_user(req.model_dump(), admin.id)