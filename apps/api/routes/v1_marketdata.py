import asyncio
import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status

from core.deps import get_current_user
from core.models import Tick, UserProfile
from core.security import decode_access_token
from market.data_socket import shared_socket
from market.simulator import market_simulator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/marketdata", tags=["marketdata"])


@router.websocket("/ws")
async def marketdata_ws(websocket: WebSocket, token: str | None = None):
    token = token or websocket.query_params.get("access_token")
    if not token or decode_access_token(token) is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return

    await websocket.accept()
    subscribed_symbols: set[str] = set()
    queue: asyncio.Queue[Tick] = asyncio.Queue()
    stop_event = asyncio.Event()

    async def tick_handler(tick: Tick):
        if tick.symbol in subscribed_symbols:
            await queue.put(tick)

    shared_socket.subscribe("*", tick_handler)

    async def drain_loop():
        while not stop_event.is_set():
            try:
                tick = await asyncio.wait_for(queue.get(), timeout=0.5)
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
                    "change": tick.change,
                    "change_pct": tick.change_pct,
                })
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

    drain_task = asyncio.create_task(drain_loop())

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

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error("WebSocket error: %s", e)
    finally:
        stop_event.set()
        drain_task.cancel()
        shared_socket.unsubscribe("*", tick_handler)


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
                "change": tick.change,
                "change_pct": tick.change_pct,
            })
        except asyncio.QueueEmpty:
            break


@router.post("/feed/start")
async def start_market_feed(current_user: UserProfile = Depends(get_current_user)):
    try:
        await shared_socket.start_broker_feed(
            user_id=current_user.id,
            broker_type="fyers",
            symbols=["NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX", "NSE:FINNIFTY-INDEX"],
        )
        return {"message": "Market feed started"}
    except Exception as e:
        logger.warning("Failed to start market feed: %s", e)
        return {"message": f"Feed start failed: {e}"}


@router.post("/feed/stop")
async def stop_market_feed():
    await shared_socket.stop_broker_feed("fyers")
    return {"message": "Market feed stopped"}


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
