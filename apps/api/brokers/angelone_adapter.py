import asyncio
import inspect
import gzip
import json
import logging
import os
import re as _re
from collections.abc import Callable
from datetime import UTC, datetime

from brokers.base import BaseBroker
from core.config import settings
from core.http_client import get_http_client
import httpx
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
import pyotp

logger = logging.getLogger(__name__)

_SYMBOL_TOKEN_CACHE: dict[str, str] = {}

EXCHANGE_MAP = {"NSE": "NSE", "NFO": "NFO", "BSE": "BSE", "MCX": "MCX"}
EXCHANGE_SEGMENT = {"NSE": "NSE_EQ", "NFO": "NFO_FUT", "BSE": "BSE_EQ"}

_TOKEN_MAP: dict[str, str] = {}
_MAP_DIR = os.path.dirname(os.path.abspath(__file__))
_MAP_PATH = os.path.join(_MAP_DIR, "angel_tokens.json.gz")


def _load_token_map() -> dict[str, str]:
    if _TOKEN_MAP:
        return _TOKEN_MAP
    path = _MAP_PATH
    if not os.path.isfile(path):
        logger.warning("Token map not found at %s", path)
        return _TOKEN_MAP
    try:
        with gzip.open(path, "rt") as f:
            data = json.load(f)
        _TOKEN_MAP.update(data)
        logger.info("Loaded %d token mappings from %s", len(data), path)
    except Exception as e:
        logger.error("Failed to load token map: %s", e)
    return _TOKEN_MAP


_load_token_map()


def _dict_val(d: dict, *keys: str, default=None):
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return default


class AngelOneAdapter(BaseBroker):
    broker_name = "angelone"

    def __init__(self):
        self._api_key: str = ""
        self._client_code: str = ""
        self._auth_token: str = ""
        self._feed_token: str = ""
        self._refresh_token: str = ""
        self._base_url = "https://apiconnect.angelone.in"
        self._ws_url = "wss://smartapisocket.angelone.in/websocket"
        self._running = False
        self._client = None
        self._jwt: str = ""

    async def authenticate(self, credentials: dict) -> Session:
        self._api_key = credentials.get("api_key", credentials.get("client_id", ""))
        self._client_code = credentials.get("client_code", credentials.get("username", ""))
        if not self._client_code:
            self._client_code = credentials.get("client_id", credentials.get("api_key", ""))

        access_token = credentials.get("access_token", "")
        feed_token = credentials.get("feed_token", "")

        if access_token:
            self._jwt = access_token
            self._auth_token = access_token
            self._feed_token = feed_token
            return Session(
                access_token=access_token,
                user_id=self._client_code or self._api_key,
                broker=self.broker_name,
                authenticated=True,
                expires_at=None,
            )

        password = credentials.get("secret_key", "")
        totp_secret = credentials.get("totp_secret", "")

        if not all([self._api_key, password, totp_secret]):
            raise ValueError("Angel One requires api_key, secret_key (password), and totp_secret")

        totp_code = pyotp.TOTP(totp_secret).now()

        client = await get_http_client()

        login_payload = {
            "clientcode": self._client_code or self._api_key,
            "password": password,
            "totp": totp_code,
        }
        login_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "X-PrivateKey": self._api_key,
        }

        resp = await client.post(
            f"{self._base_url}/rest/auth/angelbroking/user/v1/loginByPassword",
            json=login_payload,
            headers=login_headers,
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = self._parse_response(resp)

        if not data or data.get("status") is not True:
            msg = data.get("message", "Authentication failed") if data else "No response from Angel One"
            raise ValueError(f"Angel One auth failed: {msg}")

        self._jwt = data["data"]["jwtToken"]
        self._auth_token = self._jwt
        self._refresh_token = data["data"]["refreshToken"]
        self._feed_token = data["data"].get("feedToken", "")

        return Session(
            access_token=self._jwt,
            user_id=self._client_code or self._api_key,
            broker=self.broker_name,
            authenticated=True,
        )

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._auth_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "X-PrivateKey": self._api_key,
        }

    @staticmethod
    def _parse_response(resp):
        try:
            data = resp.json()
        except Exception:
            data = {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                data = {}
        return data

    @staticmethod
    def _ensure_list(raw) -> list:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return []
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            return [raw]
        return []

    async def _resolve_symbol_token(self, symbol: str, exchange: str = "NSE") -> str:
        cache_key = f"{exchange}:{symbol}"
        cached = _SYMBOL_TOKEN_CACHE.get(cache_key)
        if cached:
            return cached

        if not _TOKEN_MAP:
            _load_token_map()

        candidates = [f"{exchange}:{symbol}"]
        if exchange == "NSE" and not symbol.endswith("-EQ"):
            candidates.insert(0, f"NSE:{symbol}-EQ")

        token = ""
        for key in candidates:
            t = _TOKEN_MAP.get(key)
            if t:
                token = t
                break

        if token:
            _SYMBOL_TOKEN_CACHE[cache_key] = token
            return token

        logger.warning("No token found for %s:%s in local map", exchange, symbol)
        return ""

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        symbol_token = await self._resolve_symbol_token(order.symbol, order.exchange.value)
        if not symbol_token:
            return OrderResult(
                success=False,
                broker_order_id="",
                message=f"Could not resolve symbol token for {order.symbol}",
            )
        exch = EXCHANGE_MAP.get(order.exchange.value, "NSE")

        payload = {
            "variety": "NORMAL",
            "tradingsymbol": order.symbol,
            "symboltoken": symbol_token,
            "transactiontype": "BUY" if order.side == OrderSide.BUY else "SELL",
            "exchange": exch,
            "ordertype": self._map_order_type(order.order_type),
            "producttype": self._map_product(order.product),
            "duration": "DAY",
            "price": str(order.price or 0),
            "squareoff": "0",
            "stoploss": "0",
            "quantity": str(order.quantity),
        }
        if order.trigger_price and order.trigger_price > 0:
            payload["triggerprice"] = str(order.trigger_price)

        client = await get_http_client()
        resp = await client.post(
            f"{self._base_url}/rest/secure/angelbroking/order/v1/placeOrder",
            json=payload,
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = self._parse_response(resp)
        success = data.get("status") is True
        order_data = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
        return OrderResult(
            success=success,
            broker_order_id=order_data.get("orderid", "") if success else "",
            message=data.get("message", order_data.get("message", "")),
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        client = await get_http_client()
        payload = {
            "variety": "NORMAL",
            "orderid": order_id,
            "ordertype": changes.get("order_type", "MARKET"),
            "producttype": changes.get("product", "INTRADAY"),
            "quantity": str(changes.get("quantity", 0)),
            "price": str(changes.get("price", 0)),
            "tradingsymbol": changes.get("symbol", ""),
            "symboltoken": changes.get("symbol_token", ""),
            "exchange": changes.get("exchange", "NSE"),
        }
        resp = await client.post(
            f"{self._base_url}/rest/secure/angelbroking/order/v1/modifyOrder",
            json=payload,
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = self._parse_response(resp)
        return OrderResult(
            success=data.get("status") is True,
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        client = await get_http_client()
        payload = {"variety": "NORMAL", "orderid": order_id}
        resp = await client.post(
            f"{self._base_url}/rest/secure/angelbroking/order/v1/cancelOrder",
            json=payload,
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = self._parse_response(resp)
        return OrderResult(
            success=data.get("status") is True,
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def get_orderbook(self) -> list[NormalizedOrder]:
        client = await get_http_client()
        resp = await client.get(
            f"{self._base_url}/rest/secure/angelbroking/order/v1/getOrderBook",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = self._parse_response(resp)
        items = self._ensure_list(data.get("data"))
        return [self._normalize_order(item) for item in items]

    async def get_positions(self) -> list[Position]:
        client = await get_http_client()
        resp = await client.get(
            f"{self._base_url}/rest/secure/angelbroking/position/v1/getPosition",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = self._parse_response(resp)
        items = self._ensure_list(data.get("data"))
        return [self._normalize_position(item) for item in items]

    async def get_holdings(self) -> list[Holding]:
        client = await get_http_client()
        resp = await client.get(
            f"{self._base_url}/rest/secure/angelbroking/portfolio/v1/getHolding",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = self._parse_response(resp)
        items = self._ensure_list(data.get("data"))
        return [self._normalize_holding(item) for item in items]

    async def get_funds(self) -> Funds:
        client = await get_http_client()
        resp = await client.get(
            f"{self._base_url}/rest/secure/angelbroking/user/v1/getRMS",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = self._parse_response(resp)
        d = data.get("data", {})
        if isinstance(d, str):
            try:
                d = json.loads(d)
            except (json.JSONDecodeError, TypeError):
                d = {}
        return Funds(
            total_margin=float(d.get("net", 0)),
            used_margin=float(d.get("utiliseddebits", 0)),
            available_margin=float(d.get("availablecash", 0)),
            broker=self.broker_name,
        )

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        client = await get_http_client()
        results = []
        for sym in symbols:
            token = await self._resolve_symbol_token(sym)
            if not token:
                continue
            payload = {"exchange": "NSE", "symboltoken": token}
            resp = await client.post(
                f"{self._base_url}/rest/secure/angelbroking/order/v1/getLtpData",
                json=payload,
                headers=self._headers(),
                timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
            )
            data = self._parse_response(resp)
            if data.get("status") and data.get("data"):
                results.append(self._normalize_quote(data["data"]))
        return results

    async def get_historical(
        self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None
    ) -> list[Candle]:
        client = await get_http_client()
        token = await self._resolve_symbol_token(symbol)
        if not token:
            return []
        interval_map = {"1m": "ONE_MINUTE", "5m": "FIVE_MINUTE", "15m": "FIFTEEN_MINUTE", "30m": "THIRTY_MINUTE", "1h": "ONE_HOUR", "1d": "ONE_DAY"}
        payload = {
            "exchange": "NSE",
            "symboltoken": token,
            "interval": interval_map.get(interval, "ONE_DAY"),
            "fromdate": start or "",
            "todate": end or "",
        }
        resp = await client.post(
            f"{self._base_url}/rest/secure/angelbroking/historical/v1/getCandleData",
            json=payload,
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = self._parse_response(resp)
        candles = []
        for item in self._ensure_list(data.get("data")):
            candles.append(
                Candle(
                    symbol=symbol,
                    exchange=Exchange.NSE,
                    interval=interval,
                    open=float(item.get("open", 0)),
                    high=float(item.get("high", 0)),
                    low=float(item.get("low", 0)),
                    close=float(item.get("close", 0)),
                    volume=int(item.get("volume", 0)),
                    timestamp=datetime.fromisoformat(item.get("timestamp", "")) if item.get("timestamp") else datetime.now(UTC),
                )
            )
        return candles

    async def stream(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        if not self._auth_token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        self._running = True

        try:
            await self._ws_stream(symbols, on_tick)
        except ImportError:
            logger.info("websockets library not available, falling back to 1s polling")
        except Exception as e:
            logger.warning("WebSocket stream failed (%s), falling back to 1s polling", e)

        _prev: dict[str, float] = {}
        while self._running:
            try:
                quotes = await self.get_quotes(symbols)
                for q in quotes:
                    prev = _prev.get(q.symbol)
                    change = (q.last_price - prev) if prev is not None else 0.0
                    change_pct = ((q.last_price - prev) / prev * 100) if prev and prev != 0 else 0.0
                    _prev[q.symbol] = q.last_price
                    tick = Tick(
                        symbol=q.symbol,
                        exchange=Exchange.NSE,
                        last_price=q.last_price,
                        bid=q.bid,
                        ask=q.ask,
                        bid_qty=q.bid_qty,
                        ask_qty=q.ask_qty,
                        volume=q.volume,
                        change=round(change, 2),
                        change_pct=round(change_pct, 2),
                        timestamp=datetime.now(UTC),
                        broker=self.broker_name,
                        instrument_type=q.instrument_type,
                        strike_price=q.strike_price,
                        expiry_date=q.expiry_date,
                        option_type=q.option_type,
                    )
                    if inspect.iscoroutinefunction(on_tick):
                        await on_tick(tick)
                    else:
                        on_tick(tick)
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Angel polling error: %s", e)
                await asyncio.sleep(5)

    async def _ws_stream(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        import websockets

        tokens_to_sub: list[str] = []
        for sym in symbols:
            t = await self._resolve_symbol_token(sym)
            if t:
                tokens_to_sub.append(t)
        if not tokens_to_sub:
            raise ValueError("No tokens resolved for WebSocket subscription")

        subscribe_msg = json.dumps({
            "action": 1,
            "params": {
                "mode": 2,
                "tokenList": [{"exchangeType": 1, "tokens": tokens_to_sub}],
            },
        })

        ws_headers = {
            "Authorization": f"Bearer {self._auth_token}",
            "x-api-key": self._api_key,
            "x-client-code": self._client_code,
            "x-feed-token": self._feed_token,
        }

        async for ws in websockets.connect(
            self._ws_url, additional_headers=ws_headers, ping_interval=30
        ):
            try:
                await ws.send(subscribe_msg)
                async for raw in ws:
                    if not self._running:
                        break
                    if isinstance(raw, bytes):
                        tick = self._parse_protobuf_tick(raw)
                    else:
                        data = json.loads(raw)
                        tick = self._parse_tick(data)
                    if tick:
                        if inspect.iscoroutinefunction(on_tick):
                            await on_tick(tick)
                        else:
                            on_tick(tick)
            except websockets.ConnectionClosed:
                logger.info("Angel WS disconnected, reconnecting...")
                continue

    def _parse_protobuf_tick(self, raw: bytes) -> Tick | None:
        try:
            idx = 0
            fields: dict[int, bytes] = {}
            while idx < len(raw):
                if idx + 1 > len(raw):
                    break
                key = raw[idx]
                wire = key & 0x07
                field_num = key >> 3
                idx += 1
                if wire == 0:
                    val = 0
                    shift = 0
                    while idx < len(raw):
                        byte = raw[idx]
                        idx += 1
                        val |= (byte & 0x7F) << shift
                        shift += 7
                        if not (byte & 0x80):
                            break
                    fields[field_num] = val
                elif wire == 1:
                    if idx + 8 <= len(raw):
                        val = int.from_bytes(raw[idx:idx + 8], "little", signed=False)
                        idx += 8
                        fields[field_num] = val
                elif wire == 2:
                    if idx + 4 <= len(raw):
                        length = int.from_bytes(raw[idx:idx + 4], "little")
                        idx += 4
                        if idx + length <= len(raw):
                            fields[field_num] = raw[idx:idx + length]
                            idx += length
                elif wire == 5:
                    if idx + 4 <= len(raw):
                        val = int.from_bytes(raw[idx:idx + 4], "little", signed=False)
                        idx += 4
                        fields[field_num] = val
                else:
                    break

            return Tick(
                symbol=str(fields.get(1, b"")),
                exchange=Exchange.NSE,
                last_price=float(fields.get(2, 0)),
                bid=float(fields.get(3, 0)),
                ask=float(fields.get(4, 0)),
                bid_qty=int(fields.get(5, 0)),
                ask_qty=int(fields.get(6, 0)),
                volume=int(fields.get(7, 0)),
                oi=int(fields.get(8, 0)),
                timestamp=datetime.now(UTC),
                broker=self.broker_name,
            )
        except Exception as e:
            logger.warning("Failed to parse Angel protobuf tick: %s", e)
            return None

    async def disconnect(self) -> None:
        self._running = False

    def _parse_tick(self, data: dict) -> Tick | None:
        try:
            return Tick(
                symbol=data.get("symbol", ""),
                exchange=Exchange.NSE,
                last_price=float(data.get("ltp", 0)),
                bid=float(data.get("bid", 0)),
                ask=float(data.get("ask", 0)),
                bid_qty=int(data.get("bid_qty", 0)),
                ask_qty=int(data.get("ask_qty", 0)),
                volume=int(data.get("vol", 0)),
                oi=int(data.get("oi", 0)),
                change=float(data.get("ch", 0)),
                change_pct=float(data.get("chp", 0)),
                timestamp=datetime.now(UTC),
                broker=self.broker_name,
            )
        except (ValueError, KeyError, TypeError) as e:
            logger.warning("Failed to parse Angel tick: %s", e)
            return None

    @staticmethod
    def _map_order_type(ot: OrderType) -> str:
        mapping = {OrderType.MARKET: "MARKET", OrderType.LIMIT: "LIMIT", OrderType.SL: "STOPLOSS_LIMIT", OrderType.SLM: "STOPLOSS_MARKET"}
        return mapping.get(ot, "MARKET")

    @staticmethod
    def _map_product(p: ProductType) -> str:
        mapping = {ProductType.INTRADAY: "INTRADAY", ProductType.DELIVERY: "DELIVERY", ProductType.MIS: "INTRADAY", ProductType.NRML: "DELIVERY"}
        return mapping.get(p, "INTRADAY")

    @staticmethod
    def _map_status(status: str) -> OrderStatus:
        mapping = {
            "PENDING": OrderStatus.PENDING,
            "OPEN": OrderStatus.OPEN,
            "TRIGGER_PENDING": OrderStatus.PENDING,
            "FILLED": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
        }
        return mapping.get(status.upper(), OrderStatus.PENDING)

    def _normalize_order(self, item: dict) -> NormalizedOrder:
        inst = self._parse_instrument(item.get("tradingsymbol", ""))
        return NormalizedOrder(
            id=_dict_val(item, "orderid", "orderId", default=""),
            broker_order_id=_dict_val(item, "orderid", "orderId", default=""),
            symbol=item.get("tradingsymbol", ""),
            exchange=Exchange(_dict_val(item, "exchange", default="NSE")),
            side=OrderSide.BUY if (_dict_val(item, "transactiontype", "transactionType", default="")) == "BUY" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            product=ProductType.INTRADAY,
            quantity=int(item.get("quantity", 0)),
            price=float(item.get("price", 0)),
            trigger_price=float(_dict_val(item, "triggerprice", "triggerPrice", default=0) or 0) or None,
            status=self._map_status(_dict_val(item, "orderstatus", "orderStatus", default="")),
            filled_quantity=int(_dict_val(item, "filledqty", "filledQty", default=0)),
            average_price=float(_dict_val(item, "averageprice", "averagePrice", default=0)),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_position(self, item: dict) -> Position:
        inst = self._parse_instrument(item.get("tradingsymbol", ""))
        return Position(
            symbol=item.get("tradingsymbol", ""),
            exchange=Exchange(item.get("exchange", "NSE")),
            quantity=int(item.get("netqty", 0)),
            buy_quantity=int(item.get("buyqty", 0)),
            sell_quantity=int(item.get("sellqty", 0)),
            average_buy_price=float(item.get("avgbuyprice", 0)),
            average_sell_price=float(item.get("avgsellprice", 0)),
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
            symbol=item.get("tradingsymbol", ""),
            exchange=Exchange.NSE,
            quantity=int(item.get("quantity", 0)),
            average_price=float(item.get("averageprice", 0)),
            current_price=float(item.get("ltp", 0)),
            pnl=float(item.get("pnl", 0)),
            broker=self.broker_name,
        )

    def _normalize_quote(self, item: dict) -> Quote:
        if isinstance(item, str):
            try:
                item = json.loads(item)
            except (json.JSONDecodeError, TypeError):
                item = {}
        sym = item.get("tradingsymbol", item.get("symbol", ""))
        inst = self._parse_instrument(sym)
        return Quote(
            symbol=sym,
            exchange=Exchange.NSE,
            last_price=float(item.get("ltp", item.get("lastprice", 0))),
            open=float(item.get("open", 0)),
            high=float(item.get("high", 0)),
            low=float(item.get("low", 0)),
            close=float(item.get("close", 0)),
            volume=int(item.get("volume", 0)),
            bid=float(item.get("bid", 0)),
            ask=float(item.get("ask", 0)),
            timestamp=datetime.now(UTC),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    @staticmethod
    def _parse_instrument(symbol: str) -> dict:
        m = _re.match(r'^([A-Z]+)(\d{2})([A-Z]{3})(\d+)(CE|PE)$', symbol.upper())
        if m:
            yy = int(m.group(2))
            month_code = m.group(3)
            months = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}
            month_num = months.get(month_code, 1)
            return {
                "instrument_type": InstrumentType.OPT,
                "strike_price": float(m.group(4)),
                "expiry_date": f"{2000 + yy}-{month_num:02d}",
                "option_type": OptionType(m.group(5)),
            }
        m = _re.match(r'^([A-Z]+)(\d{2})([A-Z]{3})$', symbol.upper())
        if m:
            return {"instrument_type": InstrumentType.FUT, "strike_price": None, "expiry_date": None, "option_type": None}
        return {"instrument_type": InstrumentType.EQ, "strike_price": None, "expiry_date": None, "option_type": None}
