import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from core.deps import get_current_user
from core.models import UserProfile, Tick
from market.data_socket import shared_socket
from market.simulator import market_simulator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/marketdata", tags=["marketdata"])


@router.websocket("/ws")
async def marketdata_ws(websocket: WebSocket):
    await websocket.accept()
    subscribed_symbols: set[str] = set()
    queue: asyncio.Queue[Tick] = asyncio.Queue()
    cancel_event = asyncio.Event()

    async def tick_handler(tick: Tick):
        if tick.symbol in subscribed_symbols or "*" in subscribed_symbols:
            await queue.put(tick)

    shared_socket.subscribe("*", tick_handler)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")

            if action == "subscribe":
                symbols = msg.get("symbols", [])
                subscribed_symbols.update(symbols)
                await websocket.send_json({
                    "type": "subscribed",
                    "symbols": list(subscribed_symbols),
                })

            elif action == "unsubscribe":
                symbols = msg.get("symbols", [])
                for s in symbols:
                    subscribed_symbols.discard(s)
                await websocket.send_json({
                    "type": "unsubscribed",
                    "symbols": list(subscribed_symbols),
                })

            elif action == "list":
                await websocket.send_json({
                    "type": "subscribed",
                    "symbols": list(subscribed_symbols),
                })

            await _drain_queue(websocket, queue, cancel_event)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error("WebSocket error: %s", e)
    finally:
        shared_socket.unsubscribe("*", tick_handler)
        cancel_event.set()


async def _drain_queue(websocket: WebSocket, queue: asyncio.Queue, cancel: asyncio.Event):
    while not queue.empty() and not cancel.is_set():
        try:
            tick = queue.get_nowait()
            await websocket.send_json({
                "type": "tick",
                "symbol": tick.symbol,
                "exchange": tick.exchange.value,
                "last_price": tick.last_price,
                "bid": tick.bid,
                "ask": tick.ask,
                "bid_qty": tick.bid_qty,
                "ask_qty": tick.ask_qty,
                "volume": tick.volume,
                "oi": tick.oi,
                "timestamp": tick.timestamp.isoformat(),
                "change": 0.0,
                "change_pct": 0.0,
            })
        except asyncio.QueueEmpty:
            break


@router.post("/simulator/start")
async def start_simulator(current_user: UserProfile = Depends(get_current_user)):
    await market_simulator.start()
    return {"message": "Market simulator started"}


@router.post("/simulator/stop")
async def stop_simulator(current_user: UserProfile = Depends(get_current_user)):
    await market_simulator.stop()
    return {"message": "Market simulator stopped"}


@router.get("/symbols")
async def get_symbols():
    return {"symbols": list(shared_socket.subscribed_symbols)}
