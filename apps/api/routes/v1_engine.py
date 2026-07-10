from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from application.services.engine_service import EngineService
from core.deps import get_current_user
from core.models import UserProfile

router = APIRouter(prefix="/engine", tags=["engine"])

_engine_service = EngineService()


class StartRunRequest(BaseModel):
    strategy_id: str
    broker: str
    mode: str = "PAPER"
    symbols: list[str] = []


class ExecuteSignalRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    side: str
    order_type: str = "MARKET"
    product: str = "INTRADAY"
    quantity: int
    price: float = 0.0
    trigger_price: float | None = None
    strategy_id: str | None = None
    instrument_type: str = "EQ"
    strike_price: float | None = None
    expiry_date: str | None = None
    option_type: str | None = None


class OrderNoteRequest(BaseModel):
    note: str
    tags: list[str] = []


@router.post("/start")
async def start_engine(req: StartRunRequest, current_user: UserProfile = Depends(get_current_user)):
    result = await _engine_service.create_run(
        current_user.id, req.strategy_id, req.broker, req.mode, req.symbols
    )
    return result


@router.post("/stop/{run_id}")
async def stop_engine(run_id: str, current_user: UserProfile = Depends(get_current_user)):
    return await _engine_service.stop_run(current_user.id, run_id)


@router.post("/trade")
async def execute_trade(req: ExecuteSignalRequest, current_user: UserProfile = Depends(get_current_user)):
    return await _engine_service.execute_trade(current_user.id, req.model_dump())


@router.get("/orders")
async def get_orders(current_user: UserProfile = Depends(get_current_user)):
    orders = await _engine_service.get_orders(current_user.id)
    return {"orders": orders}


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, current_user: UserProfile = Depends(get_current_user)):
    try:
        return await _engine_service.cancel_order(current_user.id, order_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/note", status_code=201)
async def add_order_note(order_id: str, req: OrderNoteRequest, current_user: UserProfile = Depends(get_current_user)):
    try:
        return await _engine_service.add_order_note(current_user.id, order_id, req.note, req.tags)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/orders/notes")
async def get_order_notes(current_user: UserProfile = Depends(get_current_user)):
    return await _engine_service.get_order_notes(current_user.id)


@router.get("/positions")
async def get_positions(current_user: UserProfile = Depends(get_current_user)):
    positions = await _engine_service.get_positions(current_user.id)
    return {"positions": positions}


@router.get("/funds")
async def get_funds(current_user: UserProfile = Depends(get_current_user)):
    funds = await _engine_service.get_funds(current_user.id)
    return {"funds": funds}


@router.get("/runs")
async def get_runs(current_user: UserProfile = Depends(get_current_user)):
    runs = await _engine_service.get_runs(current_user.id)
    return {"runs": runs}


@router.get("/token-status")
async def token_status(current_user: UserProfile = Depends(get_current_user)):
    return await _engine_service.get_token_status(current_user.id)
