import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from application.services.broker_service import BrokerService
from brokers import list_brokers
from brokers.registry import get_broker_metadata
from core.config import settings
from core.deps import get_current_user
from core.models import UserProfile
from infrastructure.repositories.broker_repository import SupabaseBrokerRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/brokers", tags=["brokers"])

_broker_service = BrokerService(SupabaseBrokerRepository())


class BrokerCredentialInput(BaseModel):
    broker: str
    api_key: str = ""
    secret_key: str = ""
    client_id: str = ""
    client_code: str = ""
    access_token: str = ""
    additional_params: dict = {}


class BrokerCredentialResponse(BaseModel):
    id: str
    broker: str
    is_active: bool


class ActivateBrokerRequest(BaseModel):
    broker: str


class AuthCodeInput(BaseModel):
    auth_code: str


def _frontend_url() -> str:
    return f"{settings.frontend_url or 'https://ai.trademetrix.tech'}/brokers"


@router.get("/list")
async def list_available_brokers():
    return {"brokers": list_brokers()}


@router.get("/metadata")
async def list_broker_metadata():
    return {"brokers": get_broker_metadata()}


@router.get("/metadata/{broker}")
async def broker_metadata(broker: str):
    try:
        return get_broker_metadata(broker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/credentials")
async def get_credentials(current_user: UserProfile = Depends(get_current_user)):
    credentials = await _broker_service.list_credentials(current_user.id)
    return {"credentials": credentials}


@router.post("/activate")
async def activate_broker(req: ActivateBrokerRequest, current_user: UserProfile = Depends(get_current_user)):
    ok = await _broker_service.activate_broker(current_user.id, req.broker)
    if not ok:
        raise HTTPException(status_code=404, detail=f"No credentials found for broker '{req.broker}'")
    return {"message": f"Broker '{req.broker}' activated", "broker": req.broker}


@router.post("/credentials", status_code=201)
async def save_credentials(req: BrokerCredentialInput, current_user: UserProfile = Depends(get_current_user)):
    api_key = req.api_key or req.client_id or req.client_code or ""
    try:
        cred = await _broker_service.save_credentials(
            current_user.id, req.broker, api_key, req.secret_key,
            access_token=req.access_token or None,
            additional_params=req.additional_params,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return BrokerCredentialResponse(id=cred.id, broker=cred.broker, is_active=cred.is_active)


@router.delete("/credentials/{broker_name}", status_code=204)
async def delete_credentials(broker_name: str, current_user: UserProfile = Depends(get_current_user)):
    ok = await _broker_service.delete_credentials(current_user.id, broker_name)
    if not ok:
        raise HTTPException(status_code=404, detail="Credentials not found")


@router.post("/{broker}/re-auth")
async def broker_re_auth(broker: str, current_user: UserProfile = Depends(get_current_user)):
    try:
        auth_url = await _broker_service.re_auth(current_user.id, broker)
        return {"auth_url": auth_url}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{broker}/auth-url")
async def broker_auth_url(broker: str, current_user: UserProfile = Depends(get_current_user)):
    try:
        auth_url = await _broker_service.get_auth_url(current_user.id, broker)
        return {"auth_url": auth_url}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{broker}/exchange-code")
async def broker_exchange_code(broker: str, req: AuthCodeInput, current_user: UserProfile = Depends(get_current_user)):
    try:
        msg = await _broker_service.exchange_code(current_user.id, broker, req.auth_code)
        return {"message": msg}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{broker}/callback")
async def broker_callback(broker: str, code: str = Query(None, alias="auth_code"), state: str | None = Query(None)):
    query_code = code
    if not query_code:
        query_code = state
    success, msg = await _broker_service.handle_callback(broker, query_code, state)
    key = "auth_success" if success else "auth_error"
    return RedirectResponse(url=f"{_frontend_url()}?{key}=1")
