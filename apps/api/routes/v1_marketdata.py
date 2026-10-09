import asyncio
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from application.services.broker_service import BrokerService
from core.deps import get_current_user
from core.models import Tick, UserProfile
from core.security import decode_access_token
from infrastructure.repositories.broker_repository import SupabaseBrokerRepository
from market.data_socket import shared_socket
from market.option_chain import normalize_index_symbol, option_chain_engine
logger = logging.getLogger(__name__)

#: Credential lookups go through `BrokerService` over the repository, the same wiring
#: `routes/v1_brokers.py` and `routes/v1_portal.py` use. Constructed once at import: the
#: repository holds no state, it reads through `get_supabase()` per call.
_broker_service = BrokerService(SupabaseBrokerRepository())

router = APIRouter(prefix="/marketdata", tags=["marketdata"])


_ws_connections: set[asyncio.Task] = set()
_ws_connections_lock = asyncio.Lock()
_MAX_WS_CONNECTIONS = 100


@router.websocket("/ws")
async def marketdata_ws(websocket: WebSocket):
    session_cookie = websocket.cookies.get("tm_session")
    if not session_cookie or decode_access_token(session_cookie) is None:
        logger.warning("WS rejected — missing/invalid tm_session cookie")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return

    async with _ws_connections_lock:
        if len(_ws_connections) >= _MAX_WS_CONNECTIONS:
            logger.warning("WS rejected — max connections reached")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Too many connections")
            return

    logger.info("WS client authenticated via tm_session cookie")
    current_task = asyncio.current_task()
    accepted = False
    drain_task = None
    tick_handler = None
    try:
        async with _ws_connections_lock:
            _ws_connections.add(current_task)
        await websocket.accept()
        accepted = True
        shared_socket.increment_connections()
        subscribed_symbols: set[str] = set()
        queue: asyncio.Queue[Tick] = asyncio.Queue(maxsize=256)
        stop_event = asyncio.Event()

        async def tick_handler(tick: Tick):
            if tick.symbol in subscribed_symbols:
                try:
                    queue.put_nowait(tick)
                except asyncio.QueueFull:
                    try:
                        queue.get_nowait()
                        queue.put_nowait(tick)
                    except asyncio.QueueEmpty:
                        pass

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
                except Exception as e:
                    logger.warning("WS drain loop send error: %s", e)
                    break

        drain_task = asyncio.create_task(drain_loop())

        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")

            if action == "subscribe":
                symbols = msg.get("symbols", [])
                subscribed_symbols.update(symbols)
                pending = symbols
                for _ in range(10):
                    if not pending:
                        break
                    pending = await shared_socket.add_feed_symbols("fyers", pending)
                    if not pending:
                        break
                    if not shared_socket.feed_has_ws("fyers"):
                        break
                    await asyncio.sleep(1)
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
        if drain_task:
            drain_task.cancel()
        if tick_handler:
            shared_socket.unsubscribe("*", tick_handler)
        if accepted:
            shared_socket.decrement_connections()
        async with _ws_connections_lock:
            _ws_connections.discard(current_task)
        async with _ws_connections_lock:
            _ws_connections.discard(current_task)


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
    from market.alert_checker import start_alert_checker
    await start_alert_checker()

    broker_type = "fyers"

    try:
        # The **market-data** broker, not the execution one. This feed exists only to
        # carry prices, so it has no business being bound to the venue that fills orders.
        # It also keeps this screen and the REST quote path on one broker — if the two
        # disagreed, the tape and the quote panel would show prices from different venues
        # at the same moment, which is worse than either being wrong alone.
        active_broker = await _broker_service.resolve_market_data_broker(current_user.id)
        if active_broker:
            broker_type = active_broker
    except Exception as e:
        logger.warning("Could not resolve market-data broker for feed (%s), defaulting to fyers", e)

    try:
        await shared_socket.start_broker_feed(
            user_id=current_user.id,
            broker_type=broker_type,
            symbols=symbols,
        )
        logger.info("Market feed started for user %s with %d symbols", current_user.id, len(symbols))
        return {"message": "Market feed started", "broker": broker_type}
    except Exception as e:
        logger.error("Market feed failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Market feed failed: {e}")


@router.post("/feed/stop")
async def stop_market_feed():
    await shared_socket.stop_all_feeds()
    from market.alert_checker import stop_alert_checker
    await stop_alert_checker()
    return {"message": "Market feed stopped"}


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


@router.get("/quote")
async def get_quote(
    symbol: str | None = Query(None),
    symbols: str | None = Query(None),
    current_user: UserProfile = Depends(get_current_user),
):
    syms: list[str] = []
    if symbol:
        syms = [symbol]
    elif symbols:
        syms = [s.strip() for s in symbols.split(",")]
    if not syms:
        raise HTTPException(status_code=422, detail="Provide symbol or symbols parameter")

    quotes = await _quotes_with_broker_first(syms, current_user)
    if not quotes:
        raise HTTPException(status_code=503, detail="Quote unavailable")
    return quotes if len(quotes) > 1 else quotes[0]


async def _quotes_with_broker_first(symbols: list[str], current_user) -> list:
    from application.services.engine_service import EngineService
    from core.models import Quote
    from providers.yahoo import fetch_quotes

    broker_quotes: dict[str, Quote] = {}
    try:
        service = EngineService()
        # Market-data broker, for the same reason as the feed above. Falls back to the
        # execution broker when the tenant has made no separate choice, so every
        # existing tenant resolves to exactly what it resolved to before.
        broker = await _broker_service.resolve_market_data_broker(current_user.id)
        if broker:
            adapter = shared_socket.get_broker_adapter(broker)
            if adapter is None:
                engine = await service._get_engine(current_user.id, broker)
                adapter = getattr(engine, "_adapter", None)
            if adapter is not None and callable(getattr(adapter, "get_quotes", None)):
                quotes = await adapter.get_quotes(symbols)
                for q in quotes:
                    if q.last_price and float(q.last_price) > 0:
                        broker_quotes[q.symbol] = q
    except Exception as e:
        logger.warning("Broker-first quotes failed for %s: %s", current_user.id, e)

    result: list[Quote] = []
    missing: list[str] = []
    for s in symbols:
        q = broker_quotes.get(s)
        if q is not None:
            result.append(q)
        else:
            missing.append(s)

    if missing:
        try:
            yahoo = await fetch_quotes(missing)
            for q in yahoo:
                if q.last_price and float(q.last_price) > 0:
                    result.append(q)
        except Exception as e:
            logger.warning("Yahoo quote fill failed for %s: %s", missing, e)

    if not result:
        logger.warning("Market data unavailable — all sources failed for %s", symbols)
        raise HTTPException(status_code=503, detail=f"Market data unavailable for {', '.join(symbols)}")

    return result


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
    days: int = Query(7, ge=1, le=1825),
    current_user: UserProfile = Depends(get_current_user),
):
    from engine.backtest import fetch_historical_data
    from strategies import MAX_BACKTEST_DAYS, MAX_INTRADAY_DAYS
    if days > MAX_BACKTEST_DAYS:
        raise HTTPException(status_code=400, detail=f"Max {MAX_BACKTEST_DAYS} days allowed")
    if days > MAX_INTRADAY_DAYS and interval not in ("1d", "1D", "daily"):
        raise HTTPException(status_code=400, detail=f"{interval} data only up to {MAX_INTRADAY_DAYS} days — use daily for longer")
    try:
        candles = await fetch_historical_data(symbol, exchange, interval, days, user_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Historical fetch failed for %s", symbol)
        raise HTTPException(status_code=502, detail=f"Historical data unavailable for {symbol}")
    return {"symbol": symbol, "interval": interval, "candles": candles}


@router.get("/option-chain")
async def get_option_chain(
    symbol: str = Query("NIFTY"),
    expiry: str = Query(""),
    current_user: UserProfile = Depends(get_current_user),
):
    """Option chain for an index, via the single canonical engine.

    This handler used to carry its own ~165-line copy of the NSE fetch, duplicating
    `market.option_chain.OptionChainEngine`. That copy still called the retired
    `/api/option-chain-indices` endpoint, so it returned None and every caller got a
    503 -- and fixing the engine changed nothing here, because the route never called
    it. `option_chain_engine` was already imported at module scope and unused.

    Delegating makes the endpoint and `/terminal/option-chain` share one
    implementation, one cache and one set of vendor quirks (the v3 endpoint's required
    `expiry` parameter and its `buyPrice1`/`sellPrice1` bid/ask rename).

    `expiry` is newly accepted because the v3 endpoint requires one to return any rows
    at all. Omitting it uses the nearest expiry, which is what the frontend does.
    """
    symbol = normalize_index_symbol(symbol)
    data = await option_chain_engine.get_option_chain(symbol, expiry=expiry)
    if data and data.get("optionChain"):
        return data

    # No simulated fallback. See the note on `OptionChainEngine.get_option_chain`: the
    # generator that used to be called here produced a formula-built chain whose only
    # label was `mock: True`, which the frontend does not read, so fabricated premiums
    # reached the UI as though they were real. The 503 is the honest answer.
    raise HTTPException(status_code=503, detail=f"Option chain unavailable for {symbol}")


@router.get("/status")
async def get_market_status(current_user: UserProfile = Depends(get_current_user)):
    from market.status import market_status_service
    return market_status_service.get_market_status()


@router.get("/instruments")
async def get_instruments(
    query: str = Query(""),
    instrument_type: str | None = Query(None),
    limit: int = Query(20, le=100),
    current_user: UserProfile = Depends(get_current_user),
):
    from market.symbol_master import symbol_master
    if query:
        results = symbol_master.search_symbols(query, instrument_type, limit)
        return {"instruments": results, "total": len(results)}
    return {"instruments": [], "total": 0}


@router.get("/metrics")
async def get_market_metrics(current_user: UserProfile = Depends(get_current_user)):
    from market.observability import market_metrics
    return market_metrics.get_metrics()
