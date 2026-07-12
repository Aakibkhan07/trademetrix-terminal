from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from application.services.strategy_catalog_service import StrategyCatalogService
from core.capabilities import Capabilities
from core.deps import get_capabilities, get_current_user
from core.models import UserProfile

router = APIRouter(prefix="/strategies", tags=["strategies"])
service = StrategyCatalogService()


class CreateStrategyRequest(BaseModel):
    name: str
    type: str = "builtin"
    config: dict = {}


class UpdateStrategyRequest(BaseModel):
    name: str | None = None
    config: dict | None = None
    is_active: bool | None = None


@router.get("/list-builtin")
async def list_builtin():
    return {"strategies": await service.list_builtin()}


@router.get("/marketplace")
async def get_marketplace():
    return {"strategies": await service.get_marketplace()}


@router.get("/{key}/detail")
async def get_strategy_detail(key: str):
    result = await service.get_strategy_detail(key)
    if not result:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return result


@router.get("/assigned")
async def get_assigned_strategies(
    current_user: UserProfile = Depends(get_current_user),
    caps: Capabilities = Depends(get_capabilities),
):
    return await service.get_assigned_strategies(current_user.id, caps)


@router.get("/")
async def get_strategies(current_user: UserProfile = Depends(get_current_user)):
    return {"strategies": await service.list_user_strategies(current_user.id)}


@router.post("/", status_code=201)
async def create_strategy(
    req: CreateStrategyRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    try:
        return await service.create_strategy(current_user.id, req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{strategy_id}")
async def update_strategy(
    strategy_id: str,
    req: UpdateStrategyRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    updates = req.model_dump(exclude_none=True)
    try:
        await service.update_strategy(strategy_id, current_user.id, updates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "Strategy updated"}


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(
    strategy_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    await service.delete_strategy(strategy_id, current_user.id)
