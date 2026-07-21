import asyncio
import hashlib
import inspect
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx

from brokers.base import BaseBroker
from core.config import settings
from core.http_client import get_http_client
from core.models import (
    Candle,
    Exchange,
    Funds,
    Holding,
    InstrumentType,
    NormalizedOrder,
    OptionType,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Quote,
    Session,
    Tick,
)

logger = logging.getLogger(__name__)


_MARGIN_SIDE_MAP = {OrderSide.BUY: 1, OrderSide.SELL: -1}
_MARGIN_TYPE_MAP = {OrderType.MARKET: 1, OrderType.LIMIT: 2, OrderType.SL: 3, OrderType.SLM: 4}
_MARGIN_PRODUCT_MAP = {
    ProductType.INTRADAY: "INTRADAY",
    ProductType.MIS: "INTRADAY",
    ProductType.DELIVERY: "CNC",
    ProductType.NRML: "CNC",
}


class FyersAdapter(BaseBroker):
    broker_name = "fyers"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._client_id: str = ""
        self._access_token: str = ""
        self._user_id: str = ""
        self._base_url = "https://api.fyers.in/api/v2"
        self._data_url = "https://api-t1.fyers.in/data"
        self._v3_url = "https://api-t1.fyers.in/api/v3"
        self._running = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = await get_http_client()
        return self._client

    _BROWSER_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://myapi.fyers.in",
        "Referer": "https://myapi.fyers.in/",
    }

    def _headers(self) -> dict:
        return {
            **self._BROWSER_HEADERS,
            "Authorization": f"{self._client_id}:{self._access_token}",
            "Content-Type": "application/json",
        }

    def _ensure_fyers_symbol(self, symbol: str) -> str:
        if ":" in symbol:
            return symbol.upper()
        if symbol.startswith("NSE:") or symbol.startswith("BSE:") or symbol.startswith("NFO:") or symbol.startswith("MCX:"):
            return symbol.upper()
        return f"NSE:{symbol.upper()}"

    @staticmethod
    def _safe_json(resp: httpx.Response) -> dict:
        body = resp.text[:500]
        if resp.status_code == 403:
            try:
                err = resp.json()
                msg = err.get("message", err.get("errmsg", body))
            except Exception:
                msg = body
            logger.error("Fyers HTTP 403: %s", msg)
            raise ValueError(f"Fyers order rejected (HTTP 403): {msg}")
        try:
            return resp.json()
        except Exception as e:
            logger.error("Fyers JSON parse failed (status=%s, body=%s): %s", resp.status_code, body, e)
            return {"s": "error", "message": f"Empty or invalid response (HTTP {resp.status_code})"}

    async def authenticate(self, credentials: dict) -> Session:
        client_id = credentials.get("client_id", "")
        raw_token = credentials.get("access_token", "")

        self._client_id = client_id
        self._access_token = raw_token

        if raw_token:
            self._user_id = client_id
            logger.info("Fyers authenticate using existing access_token (skipping profile validation)")
        else:
            auth_code = credentials.get("auth_code", "")
            app_secret = credentials.get("secret_key", "")
            if not auth_code or not app_secret:
                raise ValueError("auth_code and secret_key required for Fyers OAuth flow")
            client = await self._get_client()
            app_id_hash = hashlib.sha256(f"{client_id}:{app_secret}".encode()).hexdigest()
            resp = await client.post(
                "https://api-t1.fyers.in/api/v3/validate-authcode",
                json={
                    "grant_type": "authorization_code",
                    "appIdHash": app_id_hash,
                    "code": auth_code,
                },
                headers={"Content-Type": "application/json", **self._BROWSER_HEADERS},
                timeout=httpx.Timeout(settings.broker_request_timeout, settings.broker_connect_timeout),
            )
            data = self._safe_json(resp)
            if data.get("s") != "ok":
                raise ValueError(f"Fyers token exchange failed: {data.get('message', 'unknown')}")
            raw_token = data.get("access_token", "")
            self._access_token = raw_token

        return Session(
            access_token=raw_token,
            user_id=self._user_id or client_id,
            broker=self.broker_name,
            authenticated=True,
        )

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        from core.constants import format_fyers_option_symbol, format_fyers_future_symbol

        client = await self._get_client()
        if order.option_type and order.strike_price and order.expiry_date:
            logger.info("Admin order: symbol=%s strike=%s opt_type=%s expiry=%s", order.symbol, order.strike_price, order.option_type, order.expiry_date)
            expiry_date = None
            for fmt in ("%Y-%m-%d", "%d%b%Y", "%d%b%y"):
                try:
                    expiry_date = datetime.strptime(order.expiry_date[:10], fmt).date()
                    break
                except Exception:
                    continue
            if expiry_date is None:
                try:
                    raw = order.expiry_date[:5]
                    for yr in (datetime.now().year, datetime.now().year + 1):
                        try:
                            candidate = datetime.strptime(raw + str(yr), "%d%b%Y").date()
                            if candidate >= datetime.now().date() - timedelta(days=7):
                                expiry_date = candidate
                                break
                        except Exception:
                            continue
                except Exception:
                    pass
            logger.info("Parsed expiry_date=%s", expiry_date)
            symbol = format_fyers_option_symbol(order.symbol, order.strike_price, order.option_type.value, expiry_date)
            logger.info("Constructed fyers symbol=%s", symbol)
        else:
            symbol = self._ensure_fyers_symbol(order.symbol)
        payload = {
            "symbol": symbol,
            "qty": order.quantity,
            "type": self._map_order_type(order.order_type),
            "side": 1 if order.side == OrderSide.BUY else -1,
            "productType": self._map_product(order.product),
            "limitPrice": order.price or 0,
            "stopPrice": order.trigger_price or 0,
            "validity": "DAY",
            "offlineOrder": False,
            "stopLoss": 0,
            "takeProfit": 0,
            "orderTag": order.client_order_id or "",
        }
        logger.info("Fyers order payload: %s", payload)
        resp = await client.post(
            f"{self._v3_url}/orders",
            json=payload,
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = self._safe_json(resp)
        success = data.get("s") == "ok"
        logger.info("Fyers place_order response: %s", data)
        return OrderResult(
            success=success,
            broker_order_id=data.get("id", ""),
            message=data.get("message", ""),
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        client = await self._get_client()
        payload = {"id": order_id, **changes}
        resp = await client.put(
            f"{self._base_url}/orders",
            json=payload,
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = self._safe_json(resp)
        return OrderResult(
            success=data.get("s") == "ok",
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        client = await self._get_client()
        resp = await client.delete(
            f"{self._base_url}/orders/{order_id}",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = self._safe_json(resp)
        return OrderResult(
            success=data.get("s") == "ok",
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def get_orderbook(self) -> list[NormalizedOrder]:
        client = await self._get_client()
        resp = await client.get(
            f"{self._base_url}/orders",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = self._safe_json(resp)
        orders = []
        for item in data.get("orderBook", []):
            orders.append(self._normalize_order(item))
        return orders

    async def get_positions(self) -> list[Position]:
        client = await self._get_client()
        resp = await client.get(
            f"{self._base_url}/positions",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = self._safe_json(resp)
        positions = []
        for item in data.get("netPositions", []):
            positions.append(self._normalize_position(item))
        return positions

    async def get_holdings(self) -> list[Holding]:
        client = await self._get_client()
        resp = await client.get(
            f"{self._base_url}/holdings",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = self._safe_json(resp)
        holdings = []
        for item in data.get("holdings", []):
            holdings.append(self._normalize_holding(item))
        return holdings

    async def get_funds(self) -> Funds:
        client = await self._get_client()
        resp = await client.get(
            f"{self._base_url}/funds",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = self._safe_json(resp)
        fund_limit = data.get("fund_limit", [])
        total = 0.0
        used = 0.0
        available = 0.0
        for item in fund_limit:
            title = item.get("title", "").lower()
            eq = float(item.get("equityAmount", 0))
            if "total" in title and "balance" in title:
                total = eq
            elif "utilized" in title:
                used = eq
            elif "clear" in title and "balance" in title:
                available = eq
        return Funds(
            total_margin=total,
            used_margin=used,
            available_margin=available,
            broker=self.broker_name,
        )

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        client = await self._get_client()
        try:
            fyers_symbols = [self._ensure_fyers_symbol(s) for s in symbols]
            fyers_to_orig = dict(zip(fyers_symbols, symbols))
            resp = await client.post(
                f"{self._data_url}/quotes",
                json={"symbols": ",".join(fyers_symbols)},
                headers=self._headers(),
                timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
            )
            if resp.status_code == 200:
                data = self._safe_json(resp)
                quotes = []
                for item in data.get("d", []):
                    v = item.get("v", {})
                    sym = v.get("symbol") or item.get("n", "")
                    orig = fyers_to_orig.get(sym, sym)
                    quotes.append(self._normalize_quote(item, orig))
                if quotes:
                    return quotes
            logger.warning("Fyers quotes status=%d, falling back to Yahoo", resp.status_code)
        except Exception as e:
            logger.warning("Fyers quotes failed (%s), falling back to Yahoo", e)
        from providers.yahoo import fetch_quotes
        return await fetch_quotes(symbols)

    async def get_historical(
        self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None
    ) -> list[Candle]:
        client = await self._get_client()
        params: dict = {
            "symbol": self._ensure_fyers_symbol(symbol),
            "resolution": interval,
            "date_format": "0",
        }
        now_ts = int(time.time())
        if range:
            params["range"] = range
        else:
            params["range_from"] = start or str(now_ts - 86400 * 60)
            params["range_to"] = end or str(now_ts)
        history_urls = [
            f"{self._data_url}/history",
            f"{self._base_url}/history",
            "https://api-t1.fyers.in/api/v3/history",
        ]
        candles = []
        for url in history_urls:
            try:
                resp = await client.post(
                    url,
                    json=params,
                    headers=self._headers(),
                    timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
                )
                if resp.status_code == 200:
                    try:
                        data = self._safe_json(resp)
                        candles = data.get("candles", [])
                        if candles:
                            logger.info("Fyers history fetched from %s (%d candles)", url, len(candles))
                            break
                    except Exception:
                        logger.warning("Fyers history non-JSON from %s: %s", url, resp.text[:300])
                else:
                    logger.warning("Fyers history status=%d from %s", resp.status_code, url)
            except Exception as e:
                logger.warning("Fyers history request failed for %s: %s", url, e)

        if not candles and self._access_token and self._client_id:
            try:
                from fyers_apiv3 import fyersModel
                fy = fyersModel.FyersModel(client_id=self._client_id, token=self._access_token, log_path="")
                sd = {"symbol": params["symbol"], "resolution": params["resolution"], "date_format": "0",
                      "range_from": params.get("range_from", start or str(now_ts - 86400 * 60)),
                      "range_to": params.get("range_to", end or str(now_ts))}
                raw = await asyncio.to_thread(lambda: fy.history(sd))
                if raw and raw.get("s") == "ok":
                    candles = raw.get("candles", [])
                    logger.info("Fyers history via SDK: %d candles for %s", len(candles), params["symbol"])
            except Exception as e:
                logger.warning("Fyers history SDK fallback failed: %s", e)

        if not candles:
            period_map = {"1": "1d", "5": "5d", "15": "5d", "30": "1mo", "60": "1mo", "D": "1mo"}
            y_period = period_map.get(interval, "1mo")
            logger.info("Fyers history returned 0 candles for %s, trying Yahoo Finance", params["symbol"])
            try:
                from providers.yahoo import fetch_historical
                candles_raw = await fetch_historical(symbol, interval=interval, period=y_period)
                if candles_raw:
                    logger.info("Yahoo history: %d candles for %s", len(candles_raw), symbol)
                    return candles_raw
            except Exception as e:
                logger.warning("Yahoo history fallback failed: %s", e)

        result = []
        for item in candles:
            result.append(
                Candle(
                    symbol=symbol,
                    exchange=Exchange.NSE,
                    interval=interval,
                    open=float(item[1]),
                    high=float(item[2]),
                    low=float(item[3]),
                    close=float(item[4]),
                    volume=int(item[5]),
                    timestamp=datetime.fromtimestamp(item[0]),
                )
            )
        return result

    async def stream(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        if not self._access_token:
            logger.warning("No access_token — falling back to Yahoo Finance streaming")
            await self._stream_yahoo(symbols, on_tick)
            return

        self._running = True

        from fyers_apiv3.FyersWebsocket.data_ws import FyersDataSocket

        old = getattr(FyersDataSocket, '_instance', None)
        if old is not None:
            try:
                old.close_connection()
            except Exception:
                pass
        FyersDataSocket._instance = None

        queue: asyncio.Queue[dict] = asyncio.Queue()
        errors: list[str] = []
        loop = asyncio.get_running_loop()
        connected = asyncio.Event()

        def on_message(msg: dict):
            loop.call_soon_threadsafe(queue.put_nowait, msg)

        def on_error(err):
            errors.append(str(err))
            logger.error("Fyers WS SDK error: %s", err)

        def on_connect():
            connected.set()
            logger.info("Fyers WS SDK connected")

        try:
            ws = FyersDataSocket(
                access_token=self._access_token,
                litemode=True,
                write_to_file=False,
                log_path="/tmp",
                on_message=on_message,
                on_error=on_error,
                on_connect=on_connect,
                on_close=lambda msg: logger.info("Fyers WS SDK closed: %s", msg),
                reconnect=True,
                reconnect_retry=5,
            )

            await loop.run_in_executor(None, ws.connect)

            ws_ok = True
            try:
                await asyncio.wait_for(connected.wait(), timeout=12)
            except asyncio.TimeoutError:
                ws.close_connection()
                ws_ok = False

            if errors or not ws_ok:
                ws.close_connection()
                ws_ok = False
        except Exception as e:
            logger.warning("Fyers DataSocket init failed (%s) — falling back to Yahoo", e)
            ws_ok = False

        if not ws_ok:
            logger.warning("Fyers DataSocket failed — falling back to Yahoo Finance streaming")
            await self._stream_yahoo(symbols, on_tick)
            return

        fyers_symbols = [self._ensure_fyers_symbol(s) for s in symbols]
        VALID_FYERS_INDICES = {"NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX", "NSE:FINNIFTY-INDEX", "NSE:MIDCPNIFTY-INDEX", "NSE:SENSEX-INDEX", "BSE:SENSEX-INDEX"}
        filtered = []
        for fs in fyers_symbols:
            if fs.endswith("-INDEX") and fs not in VALID_FYERS_INDICES:
                logger.warning("Skipping invalid Fyers index symbol: %s", fs)
                continue
            filtered.append(fs)
        if not filtered:
            logger.warning("No valid Fyers symbols after filtering — falling back to Yahoo")
            await self._stream_yahoo(symbols, on_tick)
            return
        ws.subscribe(symbols=filtered)
        logger.info("Fyers DataSocket subscribed to %d symbols (filtered from %d)", len(filtered), len(fyers_symbols))

        try:
            while self._running:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                    tick = self._parse_sdk_tick(msg)
                    if tick:
                        if inspect.iscoroutinefunction(on_tick):
                            await on_tick(tick)
                        else:
                            on_tick(tick)
                except asyncio.TimeoutError:
                    continue
        finally:
            try:
                ws.close_connection()
            except Exception:
                pass
            logger.info("Fyers DataSocket closed")

    async def _stream_yahoo(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        self._running = True
        yahoo_interval = 2.0
        last_prices: dict[str, float] = {}
        from providers.yahoo import _to_yahoo
        yahoo_symbols = [_to_yahoo(s) for s in symbols]
        async with httpx.AsyncClient(timeout=5) as client:
            while self._running:
                try:
                    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={','.join(yahoo_symbols)}"
                    resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                    if resp.status_code != 200:
                        await asyncio.sleep(yahoo_interval)
                        continue
                    data = self._safe_json(resp)
                    results = data.get("quoteResponse", {}).get("result", [])
                    for item in results:
                        ys = item.get("symbol", "")
                        try:
                            idx = yahoo_symbols.index(ys)
                        except ValueError:
                            continue
                        s = symbols[idx]
                        ltp = float(item.get("regularMarketPrice", 0))
                        if ltp == 0 or ltp == last_prices.get(s):
                            continue
                        last_prices[s] = ltp
                        prev_close = float(item.get("regularMarketPreviousClose", ltp))
                        tick = Tick(
                            symbol=s, exchange=Exchange.NSE,
                            last_price=ltp,
                            bid=float(item.get("bid", 0)),
                            ask=float(item.get("ask", 0)),
                            volume=int(item.get("regularMarketVolume", 0)),
                            oi=0,
                            change=round(ltp - prev_close, 2),
                            change_pct=round((ltp - prev_close) / max(prev_close, 0.01) * 100, 2),
                            timestamp=datetime.now(UTC), broker=self.broker_name,
                        )
                        if inspect.iscoroutinefunction(on_tick):
                            await on_tick(tick)
                        else:
                            on_tick(tick)
                except httpx.TimeoutException:
                    logger.warning("Yahoo quote API timed out")
                except Exception as e:
                    logger.warning("Yahoo stream error: %s", e)
                await asyncio.sleep(yahoo_interval)

    async def get_margin_estimate(self, legs: list[dict]) -> dict:
        if not self._access_token:
            return {"supported": False, "broker": self.broker_name}
        client = await self._get_client()
        total_span = 0.0
        total_exposure = 0.0
        for leg in legs:
            symbol = leg.get("symbol", "")
            qty = leg.get("quantity", 0)
            side_raw = leg.get("side", "BUY")
            side = _MARGIN_SIDE_MAP.get(side_raw, 1) if isinstance(side_raw, OrderSide) else (1 if str(side_raw).upper() == "BUY" else -1)
            order_type_raw = leg.get("order_type", "MARKET")
            order_type = _MARGIN_TYPE_MAP.get(order_type_raw, 1) if isinstance(order_type_raw, OrderType) else (2 if str(order_type_raw).upper() == "LIMIT" else 1)
            product_raw = leg.get("product", "INTRADAY")
            product = _MARGIN_PRODUCT_MAP.get(product_raw, "INTRADAY") if isinstance(product_raw, ProductType) else _MARGIN_PRODUCT_MAP.get(ProductType(product_raw.upper()), "INTRADAY") if isinstance(product_raw, str) and product_raw.upper() in [p.value for p in ProductType] else "INTRADAY"
            product = str(product).upper()
            price = float(leg.get("price", 0))
            payload = {
                "symbol": self._ensure_fyers_symbol(symbol),
                "qty": qty,
                "side": side,
                "type": order_type,
                "productType": product,
            }
            if price > 0:
                payload["limitPrice"] = price
            try:
                resp = await client.post(
                    f"{self._v3_url}/span_margin",
                    json=payload,
                    headers=self._headers(),
                    timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
                )
                data = self._safe_json(resp)
                if data.get("s") != "ok":
                    logger.warning("Fyers margin estimate failed for %s: %s", symbol, data.get("message", ""))
                    return {"supported": False, "broker": self.broker_name, "error": data.get("message", "margin estimate failed")}
                total_span += float(data.get("span_margin", data.get("span", 0)))
                total_exposure += float(data.get("exposure_margin", data.get("exposure", 0)))
            except Exception as e:
                logger.warning("Fyers margin estimate error for %s: %s", symbol, e)
                return {"supported": False, "broker": self.broker_name, "error": str(e)}
        return {
            "supported": True,
            "broker": self.broker_name,
            "total_margin": round(total_span + total_exposure, 2),
            "span_margin": round(total_span, 2),
            "exposure_margin": round(total_exposure, 2),
            "currency": "INR",
        }

    async def disconnect(self) -> None:
        self._running = False
        self._client = None

    def _parse_sdk_tick(self, msg: dict) -> Tick | None:
        try:
            symbol = msg.get("symbol", "")
            if not symbol:
                return None
            inst = self._parse_instrument(symbol)
            return Tick(
                symbol=symbol,
                exchange=Exchange.NSE,
                last_price=float(msg.get("ltp", 0)),
                bid=float(msg.get("bid_price", msg.get("bid", 0))),
                ask=float(msg.get("ask_price", msg.get("ask", 0))),
                bid_qty=int(msg.get("bid_size", msg.get("bid_qty", 0))),
                ask_qty=int(msg.get("ask_size", msg.get("ask_qty", 0))),
                volume=int(msg.get("volume", 0)),
                oi=int(msg.get("oi", 0)),
                change=round(float(msg.get("ch", 0)), 2),
                change_pct=round(float(msg.get("chp", 0)), 2),
                timestamp=datetime.now(UTC),
                broker=self.broker_name,
                instrument_type=inst["instrument_type"],
                strike_price=inst["strike_price"],
                expiry_date=inst["expiry_date"],
                option_type=inst["option_type"],
            )
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            logger.warning("Failed to parse SDK tick: %s", e)
            return None

    def _parse_tick(self, data: dict) -> Tick | None:
        try:
            v = data.get("v", {}) if "v" in data else data
            sym = v.get("symbol") or data.get("symbol", "")
            return Tick(
                symbol=sym,
                exchange=Exchange.NSE,
                last_price=float(v.get("lp", v.get("last_price", 0))),
                bid=float(v.get("bid", v.get("bidPrice", 0))),
                ask=float(v.get("ask", v.get("askPrice", 0))),
                bid_qty=int(v.get("bid_size", v.get("bidQty", 0))),
                ask_qty=int(v.get("ask_size", v.get("askQty", 0))),
                volume=int(v.get("volume", 0)),
                oi=int(v.get("oi", 0)),
                timestamp=datetime.now(UTC),
                broker=self.broker_name,
            )
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            logger.warning("Failed to parse Fyers tick: %s", e)
            return None

    def _normalize_order(self, item: dict) -> NormalizedOrder:
        inst = self._parse_instrument(item.get("symbol", ""))
        return NormalizedOrder(
            id=item.get("id", ""),
            broker_order_id=item.get("id_fyers", ""),
            symbol=item.get("symbol", ""),
            exchange=Exchange.NSE,
            side=OrderSide.BUY if item.get("side", 1) == 1 else OrderSide.SELL,
            order_type=self._rev_map_order_type(item.get("type", 1)),
            product=self._rev_map_product(item.get("productType", "INTRADAY")),
            quantity=int(item.get("qty", 0)),
            price=float(item.get("limitPrice", 0)),
            trigger_price=float(item.get("stopPrice", 0)) if item.get("stopPrice") else None,
            status=self._map_status(item.get("status", 0)),
            filled_quantity=int(item.get("filledQty", 0)),
            average_price=float(item.get("tradedPrice", 0)),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_position(self, item: dict) -> Position:
        inst = self._parse_instrument(item.get("symbol", ""))
        return Position(
            symbol=item.get("symbol", ""),
            exchange=Exchange.NSE,
            quantity=int(item.get("netQty", 0)),
            buy_quantity=int(item.get("buyQty", 0)),
            sell_quantity=int(item.get("sellQty", 0)),
            average_buy_price=float(item.get("avgBuyPrice", 0)),
            average_sell_price=float(item.get("avgSellPrice", 0)),
            unrealised_pnl=float(item.get("unrealised", 0)),
            realised_pnl=float(item.get("realised", 0)),
            product=ProductType.INTRADAY,
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_holding(self, item: dict) -> Holding:
        return Holding(
            symbol=item.get("symbol", ""),
            exchange=Exchange.NSE,
            quantity=int(item.get("quantity", 0)),
            average_price=float(item.get("averagePrice", 0)),
            current_price=float(item.get("ltp", 0)),
            pnl=float(item.get("pnl", 0)),
            broker=self.broker_name,
        )

    def _normalize_quote(self, item: dict, symbol: str = "") -> Quote:
        v = item.get("v", {})
        sym = symbol or v.get("symbol") or item.get("n", "")
        inst = self._parse_instrument(sym)
        return Quote(
            symbol=sym,
            exchange=Exchange.NSE,
            last_price=float(v.get("lp", 0)),
            open=float(v.get("open_price", 0)),
            high=float(v.get("high_price", 0)),
            low=float(v.get("low_price", 0)),
            close=float(v.get("prev_close_price", 0)),
            volume=int(v.get("volume", 0)),
            bid=float(v.get("bid", 0)),
            ask=float(v.get("ask", 0)),
            timestamp=datetime.now(UTC),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    @staticmethod
    def _parse_instrument(symbol: str) -> dict:
        import re

        clean = symbol.split(":")[-1] if ":" in symbol else symbol
        m = re.match(r"^([A-Z]+)(\d{2})([A-Z]{3})(\d+)(CE|PE)$", clean.upper())
        if m:
            yy = int(m.group(2))
            month_code = m.group(3)
            months = {
                "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
                "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
            }
            month_num = months.get(month_code, 1)
            return {
                "instrument_type": InstrumentType.OPT,
                "strike_price": float(m.group(4)),
                "expiry_date": f"{2000 + yy}-{month_num:02d}",
                "option_type": OptionType(m.group(5)),
            }
        m = re.match(r"^([A-Z]+)(\d{2})([A-Z]{3})$", clean.upper())
        if m:
            return {"instrument_type": InstrumentType.FUT, "strike_price": None, "expiry_date": None, "option_type": None}
        return {"instrument_type": InstrumentType.EQ, "strike_price": None, "expiry_date": None, "option_type": None}

    @staticmethod
    def _map_order_type(ot: OrderType) -> int:
        mapping = {OrderType.MARKET: 1, OrderType.LIMIT: 2, OrderType.SL: 3, OrderType.SLM: 4}
        return mapping.get(ot, 1)

    @staticmethod
    def _rev_map_order_type(code: int) -> OrderType:
        mapping = {1: OrderType.MARKET, 2: OrderType.LIMIT, 3: OrderType.SL, 4: OrderType.SLM}
        return mapping.get(code, OrderType.MARKET)

    @staticmethod
    def _map_product(p: ProductType) -> str:
        mapping = {
            ProductType.INTRADAY: "INTRADAY",
            ProductType.DELIVERY: "DELIVERY",
            ProductType.MIS: "INTRADAY",
            ProductType.NRML: "CNC",
        }
        return mapping.get(p, "INTRADAY")

    @staticmethod
    def _rev_map_product(code: str) -> ProductType:
        mapping = {"INTRADAY": ProductType.INTRADAY, "DELIVERY": ProductType.DELIVERY, "MARGIN": ProductType.INTRADAY, "CNC": ProductType.NRML}
        return mapping.get(code, ProductType.INTRADAY)

    @staticmethod
    def _map_status(code: int) -> OrderStatus:
        mapping = {
            1: OrderStatus.OPEN,
            2: OrderStatus.PENDING,
            3: OrderStatus.FILLED,
            4: OrderStatus.CANCELLED,
            5: OrderStatus.REJECTED,
            6: OrderStatus.EXPIRED,
        }
        return mapping.get(code, OrderStatus.PENDING)
