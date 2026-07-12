import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from application.services.admin_service import AdminService
from core.deps import require_admin, require_super_admin
from core.models import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

_service = AdminService()


class AssignRequest(BaseModel):
    user_id: str
    strategy_key: str


class AssignResponse(BaseModel):
    id: str
    user_id: str
    strategy_key: str
    required_tier: str
    message: str


class UpdateTierRequest(BaseModel):
    subscription_tier: str


class BroadcastRequest(BaseModel):
    strategy_key: str
    symbol: str
    action: str
    quantity: int
    price: float = 0.0
    exchange: str = "NSE"
    order_type: str = "MARKET"
    product: str = "INTRADAY"
    reason: str = ""
    paper: bool = True


class SetAdminRoleRequest(BaseModel):
    email: str
    role: str


class UpdateAdminRoleRequest(BaseModel):
    role: str


@router.get("/users")
async def admin_list_users(admin: UserProfile = Depends(require_admin)):
    return await _service.list_users()


@router.get("/assignments")
async def admin_list_assignments(
    user_id: str = Query(""),
    admin: UserProfile = Depends(require_admin),
):
    return await _service.list_assignments(user_id)


@router.post("/assignments", status_code=201)
async def admin_assign_strategy(
    req: AssignRequest,
    admin: UserProfile = Depends(require_admin),
):
    return await _service.assign_strategy(req.user_id, req.strategy_key, admin.id)


@router.delete("/assignments/{assignment_id}")
async def admin_unassign_strategy(
    assignment_id: str,
    admin: UserProfile = Depends(require_admin),
):
    return await _service.unassign_strategy(assignment_id, admin.id)


@router.patch("/users/{user_id}")
async def admin_update_user_tier(
    user_id: str,
    req: UpdateTierRequest,
    admin: UserProfile = Depends(require_admin),
):
    return await _service.update_user_tier(user_id, req.subscription_tier, admin.id)


@router.get("/broadcast/recipients")
async def admin_broadcast_recipients(
    strategy_key: str = Query(""),
    admin: UserProfile = Depends(require_admin),
):
    return await _service.get_broadcast_recipients(strategy_key)


@router.post("/broadcast")
async def admin_broadcast(
    req: BroadcastRequest,
    admin: UserProfile = Depends(require_admin),
):
    return await _service.broadcast(
        req.strategy_key, req.symbol, req.action, req.quantity,
        req.price, req.exchange, req.order_type, req.product,
        req.reason, req.paper,
    )


@router.get("/brokers")
async def admin_list_brokers(admin: UserProfile = Depends(require_admin)):
    return await _service.list_brokers()


@router.get("/orders")
async def admin_list_orders(
    user_id: str = Query(""),
    is_paper: str = Query(""),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    admin: UserProfile = Depends(require_admin),
):
    return await _service.list_orders(user_id, is_paper, limit, offset)


@router.get("/audit-log")
async def admin_audit_log(
    user_id: str = Query(""),
    action: str = Query(""),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    admin: UserProfile = Depends(require_admin),
):
    return await _service.get_audit_log(user_id, action, limit, offset)


@router.get("/stats")
async def admin_stats(admin: UserProfile = Depends(require_admin)):
    return await _service.get_stats()


@router.get("/risk")
async def admin_risk_overview(admin: UserProfile = Depends(require_admin)):
    return await _service.get_risk_overview()


@router.get("/active-brokers")
async def admin_active_brokers_count(admin: UserProfile = Depends(require_admin)):
    return await _service.get_active_brokers_count()


@router.post("/brokers/fyers/validate")
async def admin_validate_fyers_tokens(admin: UserProfile = Depends(require_admin)):
    return await _service.validate_fyers_tokens()


@router.post("/brokers/fyers/re-auth/{credential_id}")
async def admin_fyers_re_auth(
    credential_id: str,
    admin: UserProfile = Depends(require_admin),
):
    return await _service.fyers_re_auth(credential_id, admin.id)


@router.get("/admins")
async def admin_list_admins(admin: UserProfile = Depends(require_admin)):
    return await _service.list_admins()


@router.post("/admins", status_code=201)
async def admin_create_admin(
    req: SetAdminRoleRequest,
    admin: UserProfile = Depends(require_super_admin),
):
    return await _service.create_admin(req.email, req.role, admin.id)


@router.patch("/admins/{user_id}")
async def admin_update_role(
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
