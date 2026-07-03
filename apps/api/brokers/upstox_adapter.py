import asyncio
import inspect
import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime

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


class UpstoxAdapter(BaseBroker):
    broker_name = "upstox"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._access_token: str = ""
        self._client_id: str = ""
        self._base_url = "https://api.upstox.com/v2"
        self._ws_url = "wss://ws.upstox.com/v2/feed/feeds"
        self._running = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = await get_http_client()
        return self._client

    async def authenticate(self, credentials: dict) -> Session:
        access_token = credentials.get("access_token", "")
        refresh_token = credentials.get("refresh_token", "")
        api_key = credentials.get("client_id") or credentials.get("api_key", "")
        secret_key = credentials.get("secret_key", "")

        if not access_token and api_key and secret_key:
            try:
                return await self._login(api_key, secret_key)
            except Exception as e:
                raise ValueError(f"Upstox login failed: {e}")

        self._access_token = access_token
        self._client_id = api_key

        if not self._access_token:
            raise ValueError("access_token required for Upstox authentication")

        client = await self._get_client()
        resp = await client.get(
            f"{self._base_url}/user/profile",
            headers=self._headers(),
            timeout=httpx.Timeout(10, connect=5),
        )
        if resp.status_code == 401 and refresh_token:
            return await self._refresh_login(refresh_token)
        if resp.status_code == 401:
            raise ValueError("Upstox authentication failed — invalid access_token")
        profile = resp.json().get("data", {}) or {}
        self._client_id = self._client_id or profile.get("user_id", "")

        return Session(
            access_token=self._access_token,
            user_id=self._client_id,
            broker=self.broker_name,
            authenticated=True,
        )

    async def _login(self, api_key: str, secret_key: str) -> Session:
        client = await self._get_client()
        resp = await client.post(
            f"{self._base_url}/login/authorization/token",
            data={
                "client_id": api_key,
                "client_secret": secret_key,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        if resp.status_code != 200 or not data.get("access_token"):
            raise ValueError(f"Upstox login failed: {data.get('message', resp.status_code)}")
        self._access_token = data["access_token"]
        self._client_id = api_key
        return Session(
            access_token=self._access_token,
            user_id=api_key,
            broker=self.broker_name,
            authenticated=True,
        )

    async def _refresh_login(self, refresh_token: str) -> Session:
        client = await self._get_client()
        resp = await client.post(
            f"{self._base_url}/login/authorization/token",
            data={
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        if resp.status_code != 200 or not data.get("access_token"):
            raise ValueError(f"Upstox token refresh failed: {data.get('message', resp.status_code)}")
        self._access_token = data["access_token"]
        return Session(
            access_token=self._access_token,
            user_id=self._client_id,
            broker=self.broker_name,
            authenticated=True,
            expires_at=data.get("expires_in"),
        )

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }

    def _ensure_upstox_key(self, symbol: str) -> str:
        if ":" not in symbol and "|" not in symbol:
            return f"NSE_EQ|{symbol}"
        return symbol

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        client = await self._get_client()
        payload: dict = {
            "quantity": order.quantity,
            "product": self._map_product(order.product),
            "validity": "DAY",
            "price": order.price or 0,
            "tag": order.client_order_id or "TradeMetrix",
            "instrument_token": self._ensure_upstox_key(order.symbol),
            "order_type": self._map_order_type(order.order_type),
            "transaction_type": self._map_side(order.side),
            "is_amo": False,
        }
        if order.disclosed_quantity and order.disclosed_quantity > 0:
            payload["disclosed_quantity"] = order.disclosed_quantity
        if order.trigger_price and order.trigger_price > 0:
            payload["trigger_price"] = order.trigger_price

        resp = await client.post(f"{self._base_url}/order/place", json=payload, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        success = data.get("status") == "success"
        return OrderResult(
            success=success,
            broker_order_id=data.get("data", {}).get("order_id", ""),
            message=data.get("message", ""),
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        client = await self._get_client()
        payload = {
            "order_id": order_id,
            "quantity": changes.get("quantity", 0),
            "price": changes.get("price", 0),
            "trigger_price": changes.get("trigger_price", 0),
            "validity": "DAY",
        }
        resp = await client.put(f"{self._base_url}/order/modify", json=payload, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        return OrderResult(
            success=data.get("status") == "success",
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        client = await self._get_client()
        resp = await client.delete(
            f"{self._base_url}/order/cancel",
            params={"order_id": order_id},
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        success = data.get("status") == "success"
        return OrderResult(
            success=success,
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def get_orderbook(self) -> list[NormalizedOrder]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/order/retrieve-all", headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        items = data.get("data", []) if isinstance(data.get("data"), list) else []
        return [self._normalize_order(item) for item in items]

    async def get_positions(self) -> list[Position]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/portfolio/short-term-positions", headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        items = data.get("data", []) if isinstance(data.get("data"), list) else []
        return [self._normalize_position(item) for item in items]

    async def get_holdings(self) -> list[Holding]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/portfolio/long-term-holdings", headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        items = data.get("data", []) if isinstance(data.get("data"), list) else []
        return [self._normalize_holding(item) for item in items]

    async def get_funds(self) -> Funds:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/user/get-funds-and-margin", headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        equity = data.get("data", {}).get("equity", {}) or {}
        return Funds(
            total_margin=float(equity.get("total_margin", 0)),
            used_margin=float(equity.get("utilised_margin", 0)),
            available_margin=float(equity.get("available_margin", 0)),
            broker=self.broker_name,
        )

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        client = await self._get_client()
        keys = ",".join(self._ensure_upstox_key(s) for s in symbols)
        resp = await client.get(
            f"{self._base_url}/market-quote/quotes",
            params={"instrument_key": keys},
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        quotes = []
        for sym, item in data.get("data", {}).items():
            quotes.append(self._normalize_quote(item, sym))
        return quotes

    async def get_historical(
        self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None
    ) -> list[Candle]:
        client = await self._get_client()
        key = self._ensure_upstox_key(symbol)
        interval_map = {
            "1minute": "1minute", "5minute": "5minute", "10minute": "10minute",
            "15minute": "15minute", "30minute": "30minute", "1hour": "60minute",
            "4hour": "240minute", "1day": "day", "1week": "week", "1month": "month",
        }
        mapped = interval_map.get(interval, interval)
        if not end:
            end = datetime.now(UTC).strftime("%Y-%m-%d")
        if not start:
            start = datetime.now(UTC).replace(day=1).strftime("%Y-%m-%d")
        url = f"{self._base_url}/historical-candle/{key}/{mapped}/{end}/{start}"
        resp = await client.get(url, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        candles = []
        for item in data.get("data", {}).get("candles", []):
            ts = item[0] if isinstance(item[0], str) else datetime.fromisoformat(item[0])
            if isinstance(ts, str):
                ts = ts.replace("T", " ").split("+")[0].split(".")[0]
                ts = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S") if " " in ts else datetime.strptime(ts, "%Y-%m-%d")
            candles.append(
                Candle(
                    symbol=symbol,
                    exchange=Exchange.NSE,
                    interval=interval,
                    open=float(item[1]),
                    high=float(item[2]),
                    low=float(item[3]),
                    close=float(item[4]),
                    volume=int(item[5]),
                    timestamp=ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts)),
                )
            )
        return candles

    async def stream(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        if not self._access_token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        self._running = True
        retry_delay = 1

        while self._running:
            try:
                async with httpx.AsyncClient() as client:
                    ws_url = f"{self._ws_url}?access_token={self._access_token}&api_version=2"
                    async with client.stream(
                        "GET",
                        ws_url,
                        headers={"Accept": "application/json"},
                    ) as resp:
                        if resp.status_code != 101:
                            logger.error("Upstox WS connect failed: %s", resp.status_code)
                            await asyncio.sleep(retry_delay)
                            retry_delay = min(retry_delay * 2, 30)
                            continue

                        retry_delay = 1
                        subscribe_msg = json.dumps({
                            "guid": "feeds_sub",
                            "method": "sub",
                            "data": {
                                "instrumentKeys": [self._ensure_upstox_key(s) for s in symbols],
                            },
                        })
                        async with client.stream("POST", ws_url, content=subscribe_msg) as ws:
                            async for line in ws.aiter_lines():
                                if not self._running:
                                    break
                                if not line.strip():
                                    continue
                                try:
                                    data = json.loads(line)
                                    tick = self._parse_tick(data)
                                    if tick:
                                        if inspect.iscoroutinefunction(on_tick):
                                            await on_tick(tick)
                                        else:
                                            on_tick(tick)
                                except json.JSONDecodeError:
                                    continue

            except Exception as e:
                logger.error("Upstox WS error: %s, reconnecting in %ds", e, retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)

    async def disconnect(self) -> None:
        self._running = False
        self._client = None

    def _parse_tick(self, data: dict) -> Tick | None:
        try:
            fe = data.get("feeds", {})
            for key, feed in fe.items():
                ff = feed.get("ff", {})
                ltp = ff.get("ltpc", {}).get("ltp", 0)
                return Tick(
                    symbol=key,
                    exchange=Exchange.NSE,
                    last_price=float(ltp),
                    bid=float(ff.get("bp", 0)),
                    ask=float(ff.get("sp", 0)),
                    bid_qty=int(ff.get("bc", 0)),
                    ask_qty=int(ff.get("sc", 0)),
                    volume=int(ff.get("v", 0)),
                    oi=int(ff.get("oi", 0)),
                    timestamp=datetime.now(UTC),
                    broker=self.broker_name,
                )
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            logger.warning("Failed to parse Upstox tick: %s", e)
            return None

    @staticmethod
    def _map_side(side: OrderSide) -> str:
        return "BUY" if side == OrderSide.BUY else "SELL"

    @staticmethod
    def _map_order_type(ot: OrderType) -> str:
        mapping = {
            OrderType.MARKET: "MARKET",
            OrderType.LIMIT: "LIMIT",
            OrderType.SL: "SL",
            OrderType.SLM: "SL-M",
        }
        return mapping.get(ot, "MARKET")

    @staticmethod
    def _map_product(p: ProductType) -> str:
        mapping = {
            ProductType.INTRADAY: "I",
            ProductType.DELIVERY: "D",
            ProductType.MIS: "I",
            ProductType.NRML: "M",
        }
        return mapping.get(p, "I")

    def _normalize_order(self, item: dict) -> NormalizedOrder:
        inst = self._parse_instrument(item.get("tradingsymbol", item.get("instrument_token", "")))
        return NormalizedOrder(
            id=item.get("order_id", ""),
            broker_order_id=item.get("order_id", ""),
            symbol=item.get("tradingsymbol", item.get("instrument_token", "")),
            exchange=Exchange(item.get("exchange", "NSE")),
            side=OrderSide.BUY if item.get("transaction_type") == "BUY" else OrderSide.SELL,
            order_type=OrderType(item.get("order_type", "MARKET")),
            product=self._unmap_product(item.get("product", "I")),
            quantity=int(item.get("quantity", 0)),
            price=float(item.get("price", 0)),
            trigger_price=float(item.get("trigger_price", 0)) if item.get("trigger_price") else None,
            status=self._map_status(item.get("status", "")),
            filled_quantity=int(item.get("filled_quantity", 0)),
            average_price=float(item.get("average_price", 0)),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_position(self, item: dict) -> Position:
        inst = self._parse_instrument(item.get("tradingsymbol", item.get("instrument_token", "")))
        return Position(
            symbol=item.get("tradingsymbol", item.get("instrument_token", "")),
            exchange=Exchange(item.get("exchange", "NSE")),
            quantity=int(item.get("quantity", 0)) - int(item.get("sell_quantity", 0)),
            buy_quantity=int(item.get("buy_quantity", 0)),
            sell_quantity=int(item.get("sell_quantity", 0)),
            average_buy_price=float(item.get("buy_price", 0)),
            average_sell_price=float(item.get("sell_price", 0)),
            unrealised_pnl=float(item.get("unrealised_pnl", 0)),
            realised_pnl=float(item.get("realised_pnl", 0)),
            product=self._unmap_product(item.get("product", "I")),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_holding(self, item: dict) -> Holding:
        return Holding(
            symbol=item.get("tradingsymbol", item.get("instrument_token", "")),
            exchange=Exchange.NSE,
            quantity=int(item.get("quantity", 0)),
            t1_quantity=int(item.get("t1_quantity", 0)),
            average_price=float(item.get("average_price", 0)),
            current_price=float(item.get("last_price", 0)),
            pnl=float(item.get("pnl", 0)),
            broker=self.broker_name,
        )

    def _normalize_quote(self, item: dict, symbol: str = "") -> Quote:
        ohlc = item.get("ohlc", {})
        sym = symbol or item.get("instrument_key", "") or item.get("tradingsymbol", "")
        inst = self._parse_instrument(sym)
        depth = item.get("depth", {})
        bid = 0.0
        ask = 0.0
        if depth:
            bids = depth.get("buy", [])
            if bids:
                bid = float(bids[0].get("price", 0))
            asks = depth.get("sell", [])
            if asks:
                ask = float(asks[0].get("price", 0))
        return Quote(
            symbol=sym,
            exchange=Exchange.NSE,
            last_price=float(item.get("last_price", 0)),
            open=float(ohlc.get("open", 0)),
            high=float(ohlc.get("high", 0)),
            low=float(ohlc.get("low", 0)),
            close=float(ohlc.get("close", 0)),
            volume=int(item.get("volume", 0)),
            bid=bid,
            ask=ask,
            timestamp=datetime.now(UTC),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    @staticmethod
    def _unmap_product(prod: str) -> ProductType:
        mapping = {"I": ProductType.INTRADAY, "D": ProductType.DELIVERY, "M": ProductType.NRML, "H": ProductType.NRML}
        return mapping.get(prod, ProductType.INTRADAY)

    @staticmethod
    def _parse_instrument(symbol: str) -> dict:
        m = re.match(r'^([A-Z]+)(\d{2})([A-Z]{3})(\d+)(CE|PE)$', symbol.upper())
        if m:
            yy = int(m.group(2))
            month_code = m.group(3)
            months = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
            month_num = months.get(month_code, 1)
            return {
                "instrument_type": InstrumentType.OPT,
                "strike_price": float(m.group(4)),
                "expiry_date": f"{2000+yy}-{month_num:02d}",
                "option_type": OptionType(m.group(5)),
            }
        m2 = re.match(r'^([A-Z]+)(\d{2})([A-Z]{3})$', symbol.upper())
        if m2:
            return {"instrument_type": InstrumentType.FUT, "strike_price": None, "expiry_date": None, "option_type": None}
        return {"instrument_type": InstrumentType.EQ, "strike_price": None, "expiry_date": None, "option_type": None}

    @staticmethod
    def _map_status(status: str) -> OrderStatus:
        mapping = {
            "open": OrderStatus.OPEN,
            "pending": OrderStatus.PENDING,
            "confirmed": OrderStatus.PENDING,
            "filled": OrderStatus.FILLED,
            "complete": OrderStatus.FILLED,
            "cancelled": OrderStatus.CANCELLED,
            "canceled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
            "trigger_pending": OrderStatus.PENDING,
            "triggered": OrderStatus.OPEN,
        }
        return mapping.get(status.lower(), OrderStatus.PENDING)
