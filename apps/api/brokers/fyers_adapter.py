import asyncio
import hashlib
import inspect
import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx

from brokers.base import BaseBroker
from brokers.fyers_http import FyersWAFError, FyersResponse, get_transport
from core.config import settings
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
    MAX_RECONNECT_SEC = 60
    MAX_RECONNECT_ATTEMPTS = 10
    TOKEN_REFRESH_MARGIN_SEC = 300

    def __init__(self):
        self._http = get_transport()
        self._access_token: str = ""
        self._client_id: str = ""
        self._user_id: str = ""
        self._base_url = "https://api-t1.fyers.in/api/v3"
        self._data_url = "https://api-t1.fyers.in/data"
        self._v3_url = "https://api-t1.fyers.in/api/v3"
        self._running = False
        self._symbol_reverse_map: dict[str, str] = {}
        self._token_expires_at: float | None = None
        self._ws_instance = None
        self._subscribed_symbols: list[str] = []
        self._reconnect_attempts = 0
        self._ws_lock = threading.Lock()

    async def _get_client(self):
        """Back-compat stub: transport owns the HTTP client now."""
        return self._http

    def _headers(self) -> dict:
        return {
            "Authorization": f"{self._client_id}:{self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://myapi.fyers.in",
            "Referer": "https://myapi.fyers.in/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }

    def _ensure_fyers_symbol(self, symbol: str) -> str:
        if ":" in symbol:
            s = symbol.upper()
        else:
            s = f"NSE:{symbol.upper()}"
        if s.endswith("-EQ"):
            s = s[:-3]
        return s

    @staticmethod
    def _ws_symbol(symbol: str) -> str:
        import re
        s = symbol.upper()
        if not s.startswith("NSE:"):
            s = f"NSE:{s}"
        rest = s[4:]
        if rest.endswith("-EQ") or rest.endswith("-INDEX") or re.search(r"\d", rest):
            return s
        return f"{s}-EQ"

    def _decode_token_expiry(self, token: str) -> None:
        try:
            parts = token.split(".")
            if len(parts) == 3:
                import base64
                import json
                padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
                payload = json.loads(base64.urlsafe_b64decode(padded))
                exp = payload.get("exp", 0)
                self._token_expires_at = float(exp)
            else:
                logger.warning("Fyers token is not a standard JWT — cannot decode expiry")
        except Exception as e:
            logger.debug("Could not decode Fyers token expiry: %s", e)

    def _needs_token_refresh(self) -> bool:
        if self._token_expires_at is None:
            return False
        return time.time() >= self._token_expires_at - self.TOKEN_REFRESH_MARGIN_SEC

    def unsubscribe_symbols(self, symbols: list[str] | None = None) -> None:
        ws = self._ws_instance
        if ws is None:
            return
        try:
            if symbols:
                ws.unsubscribe(symbols=symbols)
            else:
                ws.unsubscribe(symbols=self._subscribed_symbols)
            for s in (symbols or self._subscribed_symbols):
                self._symbol_reverse_map.pop(s, None)
            if symbols:
                self._subscribed_symbols = [s for s in self._subscribed_symbols if s not in symbols]
            else:
                self._subscribed_symbols = []
            logger.info("Unsubscribed %d symbols from Fyers WS", len(symbols or self._subscribed_symbols))
        except Exception as e:
            logger.warning("Fyers unsubscribe error: %s", e)

    @staticmethod
    def _safe_json(resp) -> dict:
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
        self._http = get_transport(client_id, raw_token)

        if raw_token:
            self._user_id = client_id
            self._decode_token_expiry(raw_token)
            if self._token_expires_at is not None and time.time() >= self._token_expires_at:
                raise ValueError("Fyers access token has expired — user must re-authenticate via OAuth")
            logger.info("Fyers authenticate using existing access_token (skipping profile validation)")
        else:
            auth_code = credentials.get("auth_code", "")
            app_secret = credentials.get("secret_key", "")
            if not auth_code or not app_secret:
                raise ValueError("auth_code and secret_key required for Fyers OAuth flow")
            app_id_hash = hashlib.sha256(f"{client_id}:{app_secret}".encode()).hexdigest()
            resp = await self._http.request(
                "POST",
                "/api/v3/validate-authcode",
                json_body={
                    "grant_type": "authorization_code",
                    "appIdHash": app_id_hash,
                    "code": auth_code,
                },
                cache_ttl=0.0,
                retries=2,
                caller="authenticate",
                authenticated=False,
            )
            data = self._safe_json(resp)
            if data.get("s") != "ok":
                raise ValueError(f"Fyers token exchange failed: {data.get('message', 'unknown')}")
            raw_token = data.get("access_token", "")
            self._access_token = raw_token
            self._http.set_token(client_id, raw_token)
            self._decode_token_expiry(raw_token)

        expires_at = None
        if self._token_expires_at is not None:
            expires_at = datetime.fromtimestamp(self._token_expires_at, tz=UTC)

        return Session(
            access_token=raw_token,
            user_id=self._user_id or client_id,
            broker=self.broker_name,
            authenticated=True,
            expires_at=expires_at,
        )

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        from core.constants import format_fyers_option_symbol
        import re

        order_tag = re.sub(r"[^a-zA-Z0-9]", "", order.client_order_id or "")[:20]

        symbol_is_full = str(int(order.strike_price)) in order.symbol.upper() if order.strike_price else False
        if order.option_type and order.strike_price and order.expiry_date and not symbol_is_full:
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
            "orderTag": order_tag,
        }
        logger.info("Fyers order payload: %s", payload)
        try:
            resp = await self._http.request(
                "POST",
                "/api/v3/orders/sync",
                json_body=payload,
                cache_ttl=0.0,
                dedup=False,
                retries=0,
                caller="place_order",
            )
        except FyersWAFError as e:
            raise ValueError(str(e)) from e
        data = self._safe_json(resp)
        success = data.get("s") == "ok"
        logger.info("Fyers place_order response: %s", data)
        return OrderResult(
            success=success,
            broker_order_id=data.get("id", ""),
            message=data.get("message", ""),
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        existing = None
        for _ in range(3):
            book = await self.get_orderbook()
            existing = next((o for o in book if str(o.broker_order_id) == str(order_id)), None)
            if existing is not None:
                break
            await asyncio.sleep(1.0)
        if existing is None:
            return OrderResult(success=False, broker_order_id=order_id, message="Order not found for modify")
        payload = {
            "id": order_id,
            "type": self._map_order_type(existing.order_type),
            "limitPrice": existing.price or 0,
            "stopPrice": existing.trigger_price or 0,
            "qty": existing.quantity,
        }
        if "quantity" in changes:
            payload["qty"] = changes["quantity"]
        if "price" in changes:
            payload["limitPrice"] = changes["price"]
        if "trigger_price" in changes:
            payload["stopPrice"] = changes["trigger_price"]
        if "order_type" in changes:
            payload["type"] = self._map_order_type(OrderType(changes["order_type"]))
        if "product" in changes:
            payload["productType"] = self._map_product(ProductType(changes["product"]))
        try:
            resp = await self._http.request(
                "PATCH",
                "/api/v3/orders/sync",
                json_body=payload,
                cache_ttl=0.0,
                dedup=False,
                retries=0,
                caller="modify_order",
            )
        except FyersWAFError as e:
            raise ValueError(str(e)) from e
        data = self._safe_json(resp)
        return OrderResult(
            success=data.get("s") == "ok",
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        try:
            resp = await self._http.request(
                "DELETE",
                "/api/v3/orders/sync",
                json_body={"id": order_id},
                cache_ttl=0.0,
                dedup=False,
                retries=0,
                caller="cancel_order",
            )
        except FyersWAFError as e:
            raise ValueError(str(e)) from e
        data = self._safe_json(resp)
        return OrderResult(
            success=data.get("s") == "ok",
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def get_orderbook(self) -> list[NormalizedOrder]:
        try:
            resp = await self._http.request(
                "GET", "/api/v3/orders",
                cache_ttl=3.0, caller="get_orderbook",
            )
        except FyersWAFError:
            return []
        data = self._safe_json(resp)
        orders = []
        for item in data.get("orderBook", []):
            orders.append(self._normalize_order(item))
        return orders

    async def get_positions(self) -> list[Position]:
        try:
            resp = await self._http.request(
                "GET", "/api/v3/positions",
                cache_ttl=5.0, caller="get_positions",
            )
        except FyersWAFError:
            return []
        data = self._safe_json(resp)
        positions = []
        for item in data.get("netPositions", []):
            positions.append(self._normalize_position(item))
        return positions

    async def get_holdings(self) -> list[Holding]:
        try:
            resp = await self._http.request(
                "GET", "/api/v3/holdings",
                cache_ttl=10.0, caller="get_holdings",
            )
        except FyersWAFError:
            return []
        data = self._safe_json(resp)
        holdings = []
        for item in data.get("holdings", []):
            holdings.append(self._normalize_holding(item))
        return holdings

    async def get_funds(self) -> Funds:
        try:
            resp = await self._http.request(
                "GET", "/api/v3/funds",
                cache_ttl=5.0, caller="get_funds",
            )
        except FyersWAFError:
            return Funds(total_margin=0.0, used_margin=0.0, available_margin=0.0, broker=self.broker_name)
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
        try:
            fyers_symbols = [self._ensure_fyers_symbol(s) for s in symbols]
            fyers_to_orig = dict(zip(fyers_symbols, symbols))
            resp = await self._http.request(
                "GET",
                "/data/quotes",
                params={"symbols": ",".join(fyers_symbols)},
                cache_ttl=0.5,
                caller="get_quotes",
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
                resp = await self._http.request(
                    "POST",
                    url,
                    json_body=params,
                    cache_ttl=0.0,
                    dedup=False,
                    retries=1,
                    caller="get_historical",
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
        self._subscribed_symbols = list(symbols)
        self._reconnect_attempts = 0

        while self._running:
            try:
                await self._run_fyers_stream(symbols, on_tick)
                break
            except Exception as e:
                if not self._running:
                    break
                self._reconnect_attempts += 1
                if self._reconnect_attempts > self.MAX_RECONNECT_ATTEMPTS:
                    logger.warning("Fyers WS reconnect limit reached — falling back to Yahoo")
                    await self._stream_yahoo(symbols, on_tick)
                    return
                delay = min(2 ** self._reconnect_attempts, self.MAX_RECONNECT_SEC)
                logger.info("Fyers WS reconnect in %ds (attempt %d/%d)", delay, self._reconnect_attempts, self.MAX_RECONNECT_ATTEMPTS)
                await asyncio.sleep(delay)

        self._ws_instance = None

    async def _run_fyers_stream(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:

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
        errors_lock = threading.Lock()
        loop = asyncio.get_running_loop()
        connected = asyncio.Event()

        def on_message(msg: dict):
            loop.call_soon_threadsafe(queue.put_nowait, msg)

        def on_error(err):
            with errors_lock:
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
            self._ws_instance = ws

            await loop.run_in_executor(None, ws.connect)

            ws_ok = True
            try:
                await asyncio.wait_for(connected.wait(), timeout=12)
            except asyncio.TimeoutError:
                ws.close_connection()
                ws_ok = False

            with errors_lock:
                has_errors = bool(errors)
            if has_errors or not ws_ok:
                ws.close_connection()
                ws_ok = False
        except Exception as e:
            logger.warning("Fyers DataSocket init failed (%s)", e)
            ws_ok = False

        if not ws_ok:
            raise ConnectionError("Fyers DataSocket failed to connect")

        fyers_symbols = [self._ensure_fyers_symbol(s) for s in symbols]
        ws_symbols = [self._ws_symbol(s) for s in symbols]
        self._symbol_reverse_map = dict(zip(ws_symbols, symbols))
        VALID_FYERS_INDICES = {"NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX", "NSE:FINNIFTY-INDEX", "NSE:MIDCPNIFTY-INDEX", "NSE:SENSEX-INDEX"}
        filtered = []
        yahoo_fallback_symbols = []
        for orig, fs in zip(symbols, ws_symbols):
            if fs.endswith("-INDEX") and fs not in VALID_FYERS_INDICES:
                logger.info("Fyers does not support %s — will use Yahoo fallback", fs)
                yahoo_fallback_symbols.append(orig)
                continue
            filtered.append(fs)
        if not filtered:
            logger.info("No Fyers-compatible symbols — using Yahoo fallback for all")
            await self._stream_yahoo(symbols, on_tick)
            return
        ws.subscribe(symbols=filtered)
        logger.info("Fyers DataSocket subscribed to %d symbols (filtered from %d)", len(filtered), len(fyers_symbols))

        async def run_yahoo_fallback():
            if yahoo_fallback_symbols:
                logger.info("Starting Yahoo fallback for %d unsupported indices", len(yahoo_fallback_symbols))
                await self._stream_yahoo(yahoo_fallback_symbols, on_tick)

        yahoo_task = asyncio.create_task(run_yahoo_fallback())

        try:
            while self._running:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                    tick = self._parse_sdk_tick(msg)
                    if tick:
                        orig_symbol = self._symbol_reverse_map.get(tick.symbol, tick.symbol)
                        tick.symbol = orig_symbol
                        if inspect.iscoroutinefunction(on_tick):
                            await on_tick(tick)
                        else:
                            on_tick(tick)
                except asyncio.TimeoutError:
                    continue
        finally:
            yahoo_task.cancel()
            try:
                await yahoo_task
            except (asyncio.CancelledError, Exception):
                pass
            try:
                ws.close_connection()
            except Exception:
                pass
            logger.info("Fyers DataSocket closed")

    async def _stream_yahoo(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        self._running = True
        yahoo_interval = 2.0
        consecutive_failures = 0
        last_prices: dict[str, float] = {}
        from providers.yahoo import _to_yahoo
        yahoo_symbols = [_to_yahoo(s) for s in symbols]
        async with httpx.AsyncClient(timeout=5) as client:
            while self._running:
                try:
                    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={','.join(yahoo_symbols)}"
                    resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                    if resp.status_code != 200:
                        consecutive_failures += 1
                        delay = min(2.0 * (2 ** min(consecutive_failures - 1, 4)), 30.0)
                        await asyncio.sleep(delay)
                        continue
                    consecutive_failures = 0
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
                resp = await self._http.request(
                    "POST",
                    "/api/v3/span_margin",
                    json_body=payload,
                    cache_ttl=60.0,
                    caller="get_margin_estimate",
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
        raw_symbol = item.get("symbol", "")
        inst = self._parse_instrument(raw_symbol)
        clean_symbol = raw_symbol.split(":")[-1]
        return NormalizedOrder(
            id=item.get("id", ""),
            broker_order_id=item.get("id", ""),
            symbol=clean_symbol,
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
        raw_symbol = item.get("symbol", "")
        inst = self._parse_instrument(raw_symbol)
        clean_symbol = raw_symbol.split(":")[-1]
        return Position(
            symbol=clean_symbol,
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
        raw_symbol = item.get("symbol", "")
        clean_symbol = raw_symbol.split(":")[-1]
        return Holding(
            symbol=clean_symbol,
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
        mapping = {OrderType.MARKET: 2, OrderType.LIMIT: 1, OrderType.SL: 4, OrderType.SLM: 3}
        return mapping.get(ot, 2)

    @staticmethod
    def _rev_map_order_type(code: int) -> OrderType:
        mapping = {2: OrderType.MARKET, 1: OrderType.LIMIT, 4: OrderType.SL, 3: OrderType.SLM}
        return mapping.get(code, OrderType.MARKET)

    @staticmethod
    def _map_product(p: ProductType) -> str:
        mapping = {
            ProductType.INTRADAY: "INTRADAY",
            ProductType.DELIVERY: "CNC",
            ProductType.MIS: "INTRADAY",
            ProductType.NRML: "MARGIN",
        }
        return mapping.get(p, "INTRADAY")

    @staticmethod
    def _rev_map_product(code: str) -> ProductType:
        mapping = {"INTRADAY": ProductType.INTRADAY, "CNC": ProductType.DELIVERY, "MARGIN": ProductType.NRML}
        return mapping.get(code, ProductType.INTRADAY)

    @staticmethod
    def _map_status(code: int) -> OrderStatus:
        mapping = {
            1: OrderStatus.CANCELLED,
            2: OrderStatus.FILLED,
            4: OrderStatus.PENDING,
            5: OrderStatus.REJECTED,
            6: OrderStatus.OPEN,
            7: OrderStatus.EXPIRED,
        }
        return mapping.get(code, OrderStatus.PENDING)
