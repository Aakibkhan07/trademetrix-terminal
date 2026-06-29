import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status

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
    broker_started = False
    try:
        await shared_socket.start_broker_feed(
            user_id=current_user.id,
            broker_type="fyers",
            symbols=[s["symbol"] for s in MAJOR_INDICES + MAJOR_STOCKS],
        )
        broker_started = True
        logger.info("Broker feed started successfully")
    except Exception as e:
        logger.warning("Broker feed unavailable (%s), falling back to simulator", e)

    if not broker_started:
        all_symbols = [s["symbol"] for s in MAJOR_INDICES + MAJOR_STOCKS]
        await market_simulator.start(symbols=all_symbols)
        logger.info("Market simulator started as fallback with %d symbols", len(all_symbols))

    return {"message": "Market feed started"}


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


MAJOR_INDICES = [
    {"symbol": "NSE:NIFTY50-INDEX", "name": "NIFTY 50", "type": "index"},
    {"symbol": "NSE:NIFTYBANK-INDEX", "name": "BANK NIFTY", "type": "index"},
    {"symbol": "NSE:FINNIFTY-INDEX", "name": "FIN NIFTY", "type": "index"},
    {"symbol": "BSE:SENSEX-INDEX", "name": "SENSEX", "type": "index"},
    {"symbol": "NSE:MIDCPNIFTY-INDEX", "name": "MIDCAP NIFTY", "type": "index"},
    {"symbol": "NSE:INDIAVIX-INDEX", "name": "INDIA VIX", "type": "index"},
    {"symbol": "NSE:NIFTYIT-INDEX", "name": "NIFTY IT", "type": "index"},
    {"symbol": "NSE:NIFTYPHARMA-INDEX", "name": "NIFTY PHARMA", "type": "index"},
    {"symbol": "NSE:NIFTYAUTO-INDEX", "name": "NIFTY AUTO", "type": "index"},
    {"symbol": "NSE:NIFTYFMCG-INDEX", "name": "NIFTY FMCG", "type": "index"},
    {"symbol": "NSE:NIFTYMETAL-INDEX", "name": "NIFTY METAL", "type": "index"},
    {"symbol": "NSE:NIFTYREALTY-INDEX", "name": "NIFTY REALTY", "type": "index"},
    {"symbol": "NSE:NIFTYENERGY-INDEX", "name": "NIFTY ENERGY", "type": "index"},
    {"symbol": "NSE:NIFTYMEDIA-INDEX", "name": "NIFTY MEDIA", "type": "index"},
    {"symbol": "NSE:NIFTYPSUBANK-INDEX", "name": "NIFTY PSU BANK", "type": "index"},
    {"symbol": "NSE:NIFTYPVTBANK-INDEX", "name": "NIFTY PVT BANK", "type": "index"},
    {"symbol": "NSE:NIFTYCONSR-INDEX", "name": "NIFTY CONSUMER DURABLES", "type": "index"},
    {"symbol": "NSE:NIFTYOILGAS-INDEX", "name": "NIFTY OIL & GAS", "type": "index"},
    {"symbol": "NSE:NIFTYDIVOP-INDEX", "name": "NIFTY DIVIDEND OPP", "type": "index"},
    {"symbol": "NSE:NIFTYGSEC-INDEX", "name": "NIFTY GSEC", "type": "index"},
]

MAJOR_STOCKS = [
    {"symbol": "NSE:RELIANCE-EQ", "name": "RELIANCE", "type": "stock"},
    {"symbol": "NSE:TCS-EQ", "name": "TCS", "type": "stock"},
    {"symbol": "NSE:HDFCBANK-EQ", "name": "HDFC BANK", "type": "stock"},
    {"symbol": "NSE:INFY-EQ", "name": "INFOSYS", "type": "stock"},
    {"symbol": "NSE:ICICIBANK-EQ", "name": "ICICI BANK", "type": "stock"},
    {"symbol": "NSE:SBIN-EQ", "name": "SBI", "type": "stock"},
    {"symbol": "NSE:BHARTIARTL-EQ", "name": "BHARTI AIRTEL", "type": "stock"},
    {"symbol": "NSE:KOTAKBANK-EQ", "name": "KOTAK BANK", "type": "stock"},
    {"symbol": "NSE:ITC-EQ", "name": "ITC", "type": "stock"},
    {"symbol": "NSE:WIPRO-EQ", "name": "WIPRO", "type": "stock"},
    {"symbol": "NSE:HCLTECH-EQ", "name": "HCL TECH", "type": "stock"},
    {"symbol": "NSE:LT-EQ", "name": "L&T", "type": "stock"},
    {"symbol": "NSE:TITAN-EQ", "name": "TITAN", "type": "stock"},
    {"symbol": "NSE:MARUTI-EQ", "name": "MARUTI SUZUKI", "type": "stock"},
    {"symbol": "NSE:ASIANPAINT-EQ", "name": "ASIAN PAINTS", "type": "stock"},
    {"symbol": "NSE:BAJFINANCE-EQ", "name": "BAJAJ FINANCE", "type": "stock"},
    {"symbol": "NSE:AXISBANK-EQ", "name": "AXIS BANK", "type": "stock"},
    {"symbol": "NSE:DMART-EQ", "name": "DMART", "type": "stock"},
    {"symbol": "NSE:SUNPHARMA-EQ", "name": "SUN PHARMA", "type": "stock"},
    {"symbol": "NSE:ULTRACEMCO-EQ", "name": "ULTRATECH CEMENT", "type": "stock"},
    {"symbol": "NSE:NTPC-EQ", "name": "NTPC", "type": "stock"},
    {"symbol": "NSE:POWERGRID-EQ", "name": "POWER GRID", "type": "stock"},
    {"symbol": "NSE:ONGC-EQ", "name": "ONGC", "type": "stock"},
    {"symbol": "NSE:COALINDIA-EQ", "name": "COAL INDIA", "type": "stock"},
    {"symbol": "NSE:ADANIENT-EQ", "name": "ADANI ENTERPRISES", "type": "stock"},
    {"symbol": "NSE:ADANIPORTS-EQ", "name": "ADANI PORTS", "type": "stock"},
    {"symbol": "NSE:BAJAJ-AUTO-EQ", "name": "BAJAJ AUTO", "type": "stock"},
    {"symbol": "NSE:BAJAJFINSV-EQ", "name": "BAJAJ FINSERV", "type": "stock"},
    {"symbol": "NSE:BRITANNIA-EQ", "name": "BRITANNIA", "type": "stock"},
    {"symbol": "NSE:CIPLA-EQ", "name": "CIPLA", "type": "stock"},
    {"symbol": "NSE:DRREDDY-EQ", "name": "DR REDDYS", "type": "stock"},
    {"symbol": "NSE:EICHERMOT-EQ", "name": "EICHER MOTORS", "type": "stock"},
    {"symbol": "NSE:GRASIM-EQ", "name": "GRASIM", "type": "stock"},
    {"symbol": "NSE:HDFCLIFE-EQ", "name": "HDFC LIFE", "type": "stock"},
    {"symbol": "NSE:HEROMOTOCO-EQ", "name": "HERO MOTOCORP", "type": "stock"},
    {"symbol": "NSE:HINDALCO-EQ", "name": "HINDALCO", "type": "stock"},
    {"symbol": "NSE:HINDUNILVR-EQ", "name": "HINDUSTAN UNILEVER", "type": "stock"},
    {"symbol": "NSE:INDUSINDBK-EQ", "name": "INDUSIND BANK", "type": "stock"},
    {"symbol": "NSE:JSWSTEEL-EQ", "name": "JSW STEEL", "type": "stock"},
    {"symbol": "NSE:KOTAKBANK-EQ", "name": "KOTAK BANK", "type": "stock"},
    {"symbol": "NSE:M&M-EQ", "name": "MAHINDRA & MAHINDRA", "type": "stock"},
    {"symbol": "NSE:NESTLEIND-EQ", "name": "NESTLE INDIA", "type": "stock"},
    {"symbol": "NSE:TATACONSUM-EQ", "name": "TATA CONSUMER", "type": "stock"},
    {"symbol": "NSE:TATAMOTORS-EQ", "name": "TATA MOTORS", "type": "stock"},
    {"symbol": "NSE:TATASTEEL-EQ", "name": "TATA STEEL", "type": "stock"},
    {"symbol": "NSE:TECHM-EQ", "name": "TECH MAHINDRA", "type": "stock"},
]


@router.get("/symbols")
async def get_symbols():
    symbols = set(shared_socket.subscribed_symbols)
    for s in MAJOR_INDICES + MAJOR_STOCKS:
        symbols.add(s["symbol"])
    return {"symbols": list(sorted(symbols))}


@router.get("/watchlist")
async def get_watchlist():
    return {"indices": MAJOR_INDICES, "stocks": MAJOR_STOCKS}


@router.get("/option-chain")
async def get_option_chain(
    symbol: str = Query("NIFTY"),
    current_user: UserProfile = Depends(get_current_user),
):
    from brokers.token_manager import TokenManager

    fyers_map = {"NIFTY": "NSE:NIFTY50-INDEX", "BANKNIFTY": "NSE:NIFTYBANK-INDEX", "FINNIFTY": "NSE:FINNIFTY-INDEX", "SENSEX": "BSE:SENSEX-INDEX"}
    fyers_symbol = fyers_map.get(symbol.upper(), symbol)

    try:
        tm = TokenManager(current_user.id, "fyers")
        session = await tm.get_session()
        raw_token = session["access_token"]

        from fyers_apiv3 import fyersModel
        fyers = fyersModel.FyersModel(client_id=session.get("client_id", ""), token=raw_token, log_path="")

        data = fyers.optionchain({"symbol": fyers_symbol, "strikecount": 9, "greeks": "0"})
        if data.get("s") != "ok":
            logger.warning("Fyers option chain failed for %s: %s", symbol, data.get("message", ""))
            return {"optionChain": [], "expiries": []}
    except ValueError as e:
        logger.warning("Fyers not connected for %s: %s", current_user.id, e)
        return {"optionChain": [], "expiries": []}

    chain = data.get("data", {})
    raw_options = chain.get("optionsChain", []) or chain.get("optionChain", [])
    raw_expiries = chain.get("expiries", [])

    expiries = []
    for e in raw_expiries:
        if isinstance(e, dict):
            expiries.append(e.get("expiry", ""))
        elif isinstance(e, str):
            expiries.append(e)

    option_chain = []
    for row in raw_options:
        strike = row.get("strikePrice", row.get("strike", 0))
        call = (row.get("call") or row.get("CE")) or {}
        put = (row.get("put") or row.get("PE")) or {}
        entry = {
            "strike": strike,
            "call": {
                "symbol": call.get("symbol", ""),
                "ltp": call.get("ltp", call.get("last_price", 0)),
                "change": call.get("change", 0),
                "change_pct": call.get("changePct", call.get("change_pct", 0)),
                "bid": call.get("bid", 0),
                "ask": call.get("ask", 0),
                "volume": call.get("volume", 0),
                "oi": call.get("oi", 0),
                "iv": call.get("iv", 0),
            },
            "put": {
                "symbol": put.get("symbol", ""),
                "ltp": put.get("ltp", put.get("last_price", 0)),
                "change": put.get("change", 0),
                "change_pct": put.get("changePct", put.get("change_pct", 0)),
                "bid": put.get("bid", 0),
                "ask": put.get("ask", 0),
                "volume": put.get("volume", 0),
                "oi": put.get("oi", 0),
                "iv": put.get("iv", 0),
            },
        }
        option_chain.append(entry)

    return {"optionChain": option_chain, "expiries": expiries}
