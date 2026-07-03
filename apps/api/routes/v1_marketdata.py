import asyncio
import datetime
import json
import logging
import random

import httpx
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status

from core.db import get_supabase
from core.deps import get_current_user
from core.models import Tick, UserProfile
from core.safe_query import safe_single
from core.security import decode_access_token
from market.data_socket import shared_socket
from market.simulator import market_simulator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/marketdata", tags=["marketdata"])


@router.websocket("/ws")
async def marketdata_ws(websocket: WebSocket):
    session_cookie = websocket.cookies.get("tm_session")
    if not session_cookie or decode_access_token(session_cookie) is None:
        logger.warning("WS rejected — missing/invalid tm_session cookie")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return

    logger.info("WS client authenticated via tm_session cookie")
    await websocket.accept()
    shared_socket.increment_connections()
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
        shared_socket.decrement_connections()


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
    symbols = [s["symbol"] for s in MAJOR_INDICES + MAJOR_STOCKS]

    await shared_socket.stop_all_feeds()
    await market_simulator.stop()
    from market.alert_checker import start_alert_checker
    await start_alert_checker()

    supabase = get_supabase()
    active = safe_single(
        supabase.table("broker_credentials")
        .select("broker")
        .eq("user_id", current_user.id)
        .eq("is_active", True)
    )

    if active and active["broker"] in STREAMING_SUPPORTED:
        broker_type = active["broker"]
        try:
            await shared_socket.start_broker_feed(
                user_id=current_user.id,
                broker_type=broker_type,
                symbols=symbols,
            )
            logger.info("Broker feed started for %s with %d symbols", broker_type, len(symbols))
            return {"message": "Market feed started", "broker": broker_type}
        except Exception as e:
            logger.warning("Broker feed %s failed (%s), falling back to simulator", broker_type, e)
    elif active:
        logger.warning("Active broker %s has no streaming support — falling back to simulator", active["broker"])
    else:
        logger.warning("No active broker configured — falling back to simulator")

    await market_simulator.start(symbols=symbols)
    logger.info("Market simulator started with %d symbols", len(symbols))
    return {"message": "Market feed started (simulator)", "broker": "simulator"}


@router.post("/feed/stop")
async def stop_market_feed():
    await shared_socket.stop_all_feeds()
    await market_simulator.stop()
    from market.alert_checker import stop_alert_checker
    await stop_alert_checker()
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


@router.get("/historical")
async def get_historical(
    symbol: str = Query("NIFTY"),
    exchange: str = Query("NSE"),
    interval: str = Query("15m"),
    days: int = Query(7),
    current_user: UserProfile = Depends(get_current_user),
):
    from engine.backtest import fetch_historical_data
    candles = await fetch_historical_data(symbol, exchange, interval, days, user_id=current_user.id)
    return {"symbol": symbol, "interval": interval, "candles": candles}


from core.config import STREAMING_SUPPORTED

STRIKE_INTERVALS: dict[str, int] = {"NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50, "SENSEX": 100}
LOT_SIZES: dict[str, int] = {"NIFTY": 65, "BANKNIFTY": 30, "FINNIFTY": 60, "SENSEX": 20}


def _strikes_near_spot(spot: float, interval: int, count: int = 12) -> list[int]:
    nearest = round(spot / interval) * interval
    start = nearest - (count // 2) * interval
    return [start + i * interval for i in range(count)]


def _generate_option_chain(symbol: str, spot_price: float, expiry: str) -> dict:
    interval = STRIKE_INTERVALS.get(symbol.upper(), 50)
    strikes = _strikes_near_spot(spot_price, interval, 16)

    chain = []
    for strike in strikes:
        moneyness = (strike - spot_price) / spot_price
        call_prem = max(0.05, abs(spot_price - strike) * 0.3 + 10 * (1 + moneyness))
        put_prem = max(0.05, abs(spot_price - strike) * 0.3 + 10 * (1 - moneyness))
        iv = 15 + random.uniform(-3, 5)

        chain.append({
            "strike": strike,
            "call": {
                "ltp": round(call_prem, 1),
                "change": round(random.uniform(-10, 15), 1),
                "change_pct": round(random.uniform(-5, 8), 1),
                "bid": round(call_prem * 0.95, 1),
                "ask": round(call_prem * 1.05, 1),
                "volume": random.randint(1000, 500000),
                "oi": random.randint(50000, 5000000),
                "iv": round(iv, 1),
            },
            "put": {
                "ltp": round(put_prem, 1),
                "change": round(random.uniform(-10, 15), 1),
                "change_pct": round(random.uniform(-5, 8), 1),
                "bid": round(put_prem * 0.95, 1),
                "ask": round(put_prem * 1.05, 1),
                "volume": random.randint(1000, 500000),
                "oi": random.randint(50000, 5000000),
                "iv": round(iv, 1),
            },
        })
    return {"optionChain": chain, "expiries": [expiry]}


NSE_INDICES = {"NIFTY", "BANKNIFTY", "FINNIFTY"}


async def _fetch_nse_option_chain(symbol: str) -> dict | None:
    if symbol.upper() not in NSE_INDICES:
        return None
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            client.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "application/json, text/plain, */*",
            })
            await client.get("https://www.nseindia.com")
            resp = await client.get(f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol.upper()}")
            if resp.status_code != 200:
                logger.warning("NSE option chain returned status %d", resp.status_code)
                return None
            data = resp.json()
            records = data.get("records", {})
            raw_expiries = records.get("expiryDates", [])
            raw_data = records.get("data", [])
            if not raw_expiries or not raw_data:
                return None
            expiries = []
            for e in raw_expiries:
                try:
                    dt = datetime.datetime.strptime(e, "%d-%b-%Y").strftime("%d%b").upper()
                    expiries.append(dt)
                except Exception:
                    expiries.append(e.upper().replace("-", ""))
            option_chain = []
            strikes_seen = set()
            for row in raw_data:
                strike = row.get("strikePrice", 0)
                if not strike or strike in strikes_seen:
                    continue
                strikes_seen.add(strike)
                ce = row.get("CE") or {}
                pe = row.get("PE") or {}
                option_chain.append({
                    "strike": strike,
                    "call": {
                        "ltp": ce.get("lastPrice", 0),
                        "change": ce.get("change", 0),
                        "change_pct": ce.get("pChange", 0),
                        "bid": ce.get("bidprice", 0),
                        "ask": ce.get("askPrice", 0),
                        "volume": ce.get("totalTradedVolume", 0),
                        "oi": ce.get("openInterest", 0),
                        "iv": ce.get("impliedVolatility", 0),
                    },
                    "put": {
                        "ltp": pe.get("lastPrice", 0),
                        "change": pe.get("change", 0),
                        "change_pct": pe.get("pChange", 0),
                        "bid": pe.get("bidprice", 0),
                        "ask": pe.get("askPrice", 0),
                        "volume": pe.get("totalTradedVolume", 0),
                        "oi": pe.get("openInterest", 0),
                        "iv": pe.get("impliedVolatility", 0),
                    },
                })
            if option_chain and expiries:
                logger.info("NSE option chain fetched successfully for %s (%d strikes, %d expiries)", symbol, len(option_chain), len(expiries))
                return {"optionChain": option_chain, "expiries": expiries}
    except Exception as e:
        logger.warning("NSE option chain fetch failed for %s: %s", symbol, e)
    return None


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
        if data.get("s") == "ok":
            chain = data.get("data", {})
            raw_options = chain.get("optionsChain", []) or chain.get("optionChain", [])
            raw_expiry_data = chain.get("expiryData", [])

            expiries = []
            for e in raw_expiry_data:
                if isinstance(e, dict):
                    date_str = e.get("date", "")
                    try:
                        dt = datetime.datetime.strptime(date_str, "%d-%m-%Y")
                        expiries.append(dt.strftime("%d%b").upper())
                    except Exception:
                        expiries.append(date_str.replace("-", "").upper())

            by_strike: dict[int, dict[str, dict]] = {}
            for row in raw_options:
                strike = row.get("strike_price", 0)
                if strike < 0:
                    continue
                opt_type = row.get("option_type", "")
                if opt_type not in ("CE", "PE"):
                    continue
                by_strike.setdefault(strike, {})[opt_type] = row

            option_chain = []
            for strike in sorted(by_strike):
                ce = by_strike[strike].get("CE", {})
                pe = by_strike[strike].get("PE", {})
                option_chain.append({
                    "strike": strike,
                    "call": {
                        "ltp": ce.get("ltp", 0),
                        "change": ce.get("ltpch", 0),
                        "change_pct": ce.get("ltpchp", 0),
                        "bid": ce.get("bid", 0),
                        "ask": ce.get("ask", 0),
                        "volume": ce.get("volume", 0),
                        "oi": ce.get("oi", 0),
                        "iv": ce.get("iv", 0),
                    },
                    "put": {
                        "ltp": pe.get("ltp", 0),
                        "change": pe.get("ltpch", 0),
                        "change_pct": pe.get("ltpchp", 0),
                        "bid": pe.get("bid", 0),
                        "ask": pe.get("ask", 0),
                        "volume": pe.get("volume", 0),
                        "oi": pe.get("oi", 0),
                        "iv": pe.get("iv", 0),
                    },
                })

            if option_chain and expiries:
                logger.info("Fyers option chain fetched for %s (%d strikes)", symbol, len(option_chain))
                return {"optionChain": option_chain, "expiries": expiries}
    except Exception as e:
        logger.warning("Fyers option chain unavailable (%s)", e)

    nse_data = await _fetch_nse_option_chain(symbol)
    if nse_data:
        return nse_data

    spot_prices = {"NIFTY": 24000, "BANKNIFTY": 52000, "FINNIFTY": 22000, "SENSEX": 80000}
    spot = spot_prices.get(symbol.upper(), 24000)

    WEEKLY_EXPIRY = {"NIFTY": 1, "BANKNIFTY": 1, "FINNIFTY": 1, "SENSEX": 3}
    target = WEEKLY_EXPIRY.get(symbol.upper(), 1)
    today = datetime.date.today()
    days = (target - today.weekday()) % 7
    if days == 0: days = 7
    expiry = (today + datetime.timedelta(days=days)).strftime("%d%b").upper()

    return _generate_option_chain(symbol, spot, expiry)
