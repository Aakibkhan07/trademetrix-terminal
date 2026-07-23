import logging

from fastapi import APIRouter, Depends, HTTPException, status

from application.services.strategy_service import StrategyService
from core.capabilities import Capabilities
from core.deps import get_capabilities, get_current_user, require_feature
from core.models import CreateUserStrategyRequest, DeployStrategyRequest, UpdateUserStrategyRequest, UserProfile

router = APIRouter(prefix="/user-strategies", tags=["user-strategies"])
logger = logging.getLogger(__name__)

_strategy_service = StrategyService()


@router.get("/")
async def list_user_strategies(
    current_user: UserProfile = Depends(get_current_user),
    status_filter: str | None = None,
):
    strategies = await _strategy_service.list_strategies(current_user.id, status_filter)
    return {"strategies": strategies}


@router.post("/", status_code=201)
async def create_user_strategy(
    req: CreateUserStrategyRequest,
    current_user: UserProfile = Depends(require_feature("builder")),
    caps: Capabilities = Depends(get_capabilities),
):
    try:
        return await _strategy_service.create_strategy(req, current_user, caps)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{strategy_id}")
async def get_user_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    try:
        return await _strategy_service.get_strategy(current_user.id, strategy_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{strategy_id}/activity")
async def get_strategy_activity(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    return await _strategy_service.get_strategy_activity(current_user.id, strategy_id)


@router.patch("/{strategy_id}")
async def update_user_strategy(
    strategy_id: str,
    req: UpdateUserStrategyRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    try:
        await _strategy_service.update_strategy(current_user.id, strategy_id, req)
        return {"message": "Strategy updated"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{strategy_id}", status_code=204)
async def delete_user_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    await _strategy_service.delete_strategy(current_user.id, strategy_id)


@router.post("/{strategy_id}/deploy")
async def deploy_user_strategy(
    strategy_id: str,
    req: DeployStrategyRequest,
    current_user: UserProfile = Depends(require_feature("builder")),
    caps: Capabilities = Depends(get_capabilities),
):
    try:
        return await _strategy_service.deploy_strategy(current_user.id, strategy_id, req, current_user, caps)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
