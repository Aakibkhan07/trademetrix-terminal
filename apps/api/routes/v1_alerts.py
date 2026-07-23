import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from application.services.alert_service import AlertService
from core.deps import get_current_user
from core.models import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])

alert_service = AlertService()


class CreateAlertRequest(BaseModel):
    symbol: str
    condition: str
    target_price: float
    note: str = ""


class AlertResponse(BaseModel):
    id: str
    symbol: str
    condition: str
    target_price: float
    is_active: bool
    triggered_at: str | None
    note: str
    created_at: str


class NotificationPrefsRequest(BaseModel):
    channels: list[str]


@router.get("/")
async def list_alerts(current_user: UserProfile = Depends(get_current_user)):
    return await alert_service.list_alerts(current_user.id)


@router.post("/", status_code=201)
async def create_alert(
    req: CreateAlertRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    result = await alert_service.create_alert(
        current_user.id, req.symbol, req.condition, req.target_price, req.note,
    )
    return AlertResponse(**result)


@router.delete("/{alert_id}", status_code=204)
async def delete_alert(
    alert_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    await alert_service.delete_alert(current_user.id, alert_id)


@router.post("/{alert_id}/toggle")
async def toggle_alert(
    alert_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    return await alert_service.toggle_alert(current_user.id, alert_id)


@router.get("/notification-prefs")
async def get_notification_prefs(current_user: UserProfile = Depends(get_current_user)):
    return await alert_service.get_notification_prefs(current_user.id)


@router.put("/notification-prefs")
async def update_notification_prefs(
    req: NotificationPrefsRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    return await alert_service.update_notification_prefs(current_user.id, req.channels)
