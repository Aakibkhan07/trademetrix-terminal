import asyncio
import inspect
import hashlib
import json
import logging
import re
import struct
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


class AliceBlueAdapter(BaseBroker):
    broker_name = "aliceblue"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._access_token: str = ""
        self._user_id: str = ""
        self._base_url = "https://ant.aliceblueonline.com/rest/AliceBlueAPIService"
        self._ws_url = "wss://wsfeed.aliceblueonline.com/ws"
        self._running = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = await get_http_client()
        return self._client

    async def authenticate(self, credentials: dict) -> Session:
        self._access_token = credentials.get("access_token") or ""
        self._user_id = credentials.get("client_code") or credentials.get("client_id") or credentials.get("api_key") or ""

        if not self._access_token and self._user_id:
            api_key = credentials.get("secret_key", "")
            totp_secret = credentials.get("additional_params", {}).get("totp_secret", "")
            if api_key and totp_secret:
                client = await self._get_client()
                import pyotp
                totp = pyotp.TOTP(totp_secret).now()
                checksum = hashlib.sha256(f"{self._user_id}{api_key}{totp}".encode()).hexdigest()
                payload = {
                    "userId": self._user_id,
                    "userData": f"{self._user_id}|{api_key}|{totp}|{checksum}",
                }
                resp = await client.post(f"{self._base_url}/api/customer/account/login", json=payload, timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
                data = resp.json()
                self._access_token = data.get("token", data.get("accessToken", data.get("sessionToken", "")))
                if not self._access_token:
                    raise ValueError(f"Alice Blue login failed: {data.get('message', data.get('error', ''))}")

        if not self._access_token:
            raise ValueError("access_token required for Alice Blue authentication")

        return Session(
            access_token=self._access_token,
            user_id=self._user_id,
            broker=self.broker_name,
            authenticated=True,
        )

    def _headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        client = await self._get_client()
        payload = {
            "userId": self._user_id,
            "tradingSymbol": order.symbol,
            "exchange": order.exchange.value,
            "transactionType": self._map_side(order.side),
            "orderType": self._map_order_type(order.order_type),
            "productType": self._map_product(order.product),
            "quantity": str(order.quantity),
            "price": str(order.price or 0),
            "triggerPrice": str(order.trigger_price or 0),
            "validity": "DAY",
        }
        resp = await client.post(f"{self._base_url}/api/order/place", json=payload, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        success = data.get("success", data.get("status", "") == "success")
        return OrderResult(
            success=success,
            broker_order_id=str(data.get("orderId", data.get("OrderID", data.get("nOrdNo", "")))),
            message=data.get("message", data.get("msg", "")),
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        client = await self._get_client()
        payload = {
            "userId": self._user_id,
            "orderId": order_id,
            "quantity": str(changes.get("quantity", 0)),
            "price": str(changes.get("price", 0)),
            "triggerPrice": str(changes.get("trigger_price", 0)),
            "orderType": self._map_order_type_str(changes.get("order_type", "MARKET")),
            "validity": "DAY",
        }
        resp = await client.post(f"{self._base_url}/api/order/modify", json=payload, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        return OrderResult(
            success=data.get("success", data.get("status", "") == "success"),
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        client = await self._get_client()
        payload = {"userId": self._user_id, "orderId": order_id}
        resp = await client.post(f"{self._base_url}/api/order/cancel", json=payload, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        return OrderResult(
            success=data.get("success", data.get("status", "") == "success"),
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def get_orderbook(self) -> list[NormalizedOrder]:
        client = await self._get_client()
        payload = {"userId": self._user_id}
        resp = await client.post(f"{self._base_url}/api/order/book", json=payload, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        items = data.get("data", data.get("result", data.get("orderBook", [])))
        if isinstance(items, dict):
            items = items.get("orderBook", [])
        return [self._normalize_order(item) for item in (items or [])]

    async def get_positions(self) -> list[Position]:
        client = await self._get_client()
        payload = {"userId": self._user_id}
        resp = await client.post(f"{self._base_url}/api/position/getPosition", json=payload, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        items = data.get("data", data.get("result", data.get("positionBook", [])))
        if isinstance(items, dict):
            items = items.get("positionBook", [])
        return [self._normalize_position(item) for item in (items or [])]

    async def get_holdings(self) -> list[Holding]:
        client = await self._get_client()
        payload = {"userId": self._user_id}
        resp = await client.post(f"{self._base_url}/api/holding/getHolding", json=payload, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        items = data.get("data", data.get("result", data.get("holdingBook", [])))
        if isinstance(items, dict):
            items = items.get("holdingBook", [])
        return [self._normalize_holding(item) for item in (items or [])]

    async def get_funds(self) -> Funds:
        client = await self._get_client()
        payload = {"userId": self._user_id}
        resp = await client.post(f"{self._base_url}/api/limits/getLimits", json=payload, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        limits = data.get("data", data.get("result", {}))
        if isinstance(limits, list) and limits:
            limits = limits[0]
        return Funds(
            total_margin=float(limits.get("totalMargin", limits.get("TotalMargin", 0))),
            used_margin=float(limits.get("usedMargin", limits.get("UsedMargin", 0))),
            available_margin=float(limits.get("availableMargin", limits.get("AvailableMargin", 0))),
            broker=self.broker_name,
        )

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        if not symbols:
            return []
        client = await self._get_client()
        quotes = []
        for sym in symbols:
            try:
                resp = await client.post(
                    f"{self._base_url}/api/v2/market/quotes",
                    json={"userId": self._user_id, "tradingSymbol": sym, "exchange": "NSE"},
                    headers=self._headers(),
                    timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
                )
                data = resp.json()
                items = data.get("data", data.get("result", []))
                if isinstance(items, list):
                    for item in items:
                        quotes.append(self._normalize_quote(item, sym))
                elif isinstance(items, dict):
                    quotes.append(self._normalize_quote(items, sym))
            except Exception as e:
                logger.warning("Alice Blue get_quotes failed for %s: %s", sym, e)
        return quotes

    async def get_historical(
        self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None
    ) -> list[Candle]:
        client = await self._get_client()
        interval_map = {
            "1minute": "1", "5minute": "5", "10minute": "10",
            "15minute": "15", "30minute": "30", "1hour": "60",
            "1day": "1D", "1week": "1W", "1month": "1M",
        }
        mapped = interval_map.get(interval, interval)
        if not end:
            end = datetime.now(UTC).strftime("%Y-%m-%d")
        if not start:
            start = datetime.now(UTC).replace(day=1).strftime("%Y-%m-%d")
        try:
            resp = await client.post(
                f"{self._base_url}/api/v2/chart/history",
                json={
                    "userId": self._user_id,
                    "tradingSymbol": symbol,
                    "exchange": "NSE",
                    "resolution": mapped,
                    "from": start,
                    "to": end,
                },
                headers=self._headers(),
                timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
            )
            data = resp.json()
            candles = []
            items = data.get("data", data.get("candles", data.get("result", [])))
            if isinstance(items, dict):
                items = items.get("candles", [])
            for item in items:
                if isinstance(item, list):
                    ts = item[0]
                    if isinstance(ts, str):
                        ts = ts.replace("T", " ").split("+")[0].split(".")[0]
                        try:
                            ts = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S") if " " in ts else datetime.strptime(ts, "%Y-%m-%d")
                        except ValueError:
                            ts = datetime.now(UTC)
                    candles.append(
                        Candle(
                            symbol=symbol,
                            exchange=Exchange.NSE,
                            interval=interval,
                            open=float(item[1]),
                            high=float(item[2]),
                            low=float(item[3]),
                            close=float(item[4]),
                            volume=int(item[5]) if len(item) > 5 else 0,
                            timestamp=ts,
                        )
                    )
            return candles
        except Exception as e:
            logger.warning("Alice Blue get_historical failed: %s", e)
            return []

    async def stream(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        import websockets

        if not self._access_token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        self._running = True
        retry_delay = 1

        while self._running:
            try:
                ws_url = f"{self._ws_url}?token={self._access_token}&userId={self._user_id}"
                async for ws in websockets.connect(ws_url, ping_interval=30):
                    retry_delay = 1

                    # Subscribe to symbols
                    sub_msg = json.dumps({"action": "subscribe", "symbols": symbols})
                    await ws.send(sub_msg)

                    async for raw in ws:
                        if not self._running:
                            break
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8")
                        line = raw.strip()
                        if not line:
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
                logger.error("Alice Blue WS error: %s, reconnecting in %ds", e, retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)

    async def disconnect(self) -> None:
        self._running = False
        self._client = None

    def _parse_tick(self, data: dict) -> Tick | None:
        try:
            return Tick(
                symbol=data.get("tradingSymbol", data.get("symbol", "")),
                exchange=Exchange(data.get("exchange", "NSE")),
                last_price=float(data.get("ltp", data.get("lastPrice", 0))),
                bid=float(data.get("bidPrice", data.get("bp", 0))),
                ask=float(data.get("askPrice", data.get("sp", 0))),
                bid_qty=int(data.get("bidQty", data.get("bc", 0))),
                ask_qty=int(data.get("askQty", data.get("sc", 0))),
                volume=int(data.get("volume", data.get("v", 0))),
                oi=int(data.get("openInterest", data.get("oi", 0))),
                timestamp=datetime.now(UTC),
                broker=self.broker_name,
            )
        except (ValueError, KeyError, TypeError) as e:
            logger.warning("Failed to parse Alice Blue tick: %s", e)
            return None

    @staticmethod
    def _map_side(side: OrderSide) -> str:
        return "BUY" if side == OrderSide.BUY else "SELL"

    @staticmethod
    def _map_order_type(ot: OrderType) -> str:
        mapping = {OrderType.MARKET: "MARKET", OrderType.LIMIT: "LIMIT", OrderType.SL: "STOPLOSS", OrderType.SLM: "SL-M"}
        return mapping.get(ot, "MARKET")

    @staticmethod
    def _map_order_type_str(ot: str) -> str:
        mapping = {"MARKET": "MARKET", "LIMIT": "LIMIT", "SL": "STOPLOSS", "SLM": "SL-M"}
        return mapping.get(ot, "MARKET")

    @staticmethod
    def _map_product(p: ProductType) -> str:
        mapping = {ProductType.INTRADAY: "INTRADAY", ProductType.DELIVERY: "DELIVERY", ProductType.MIS: "INTRADAY", ProductType.NRML: "DELIVERY"}
        return mapping.get(p, "INTRADAY")

    def _normalize_quote(self, item: dict, symbol: str = "") -> Quote:
        ohlc = item.get("ohlc", {})
        sym = symbol or item.get("tradingSymbol", item.get("symbol", ""))
        inst = self._parse_instrument(sym)
        return Quote(
            symbol=sym,
            exchange=Exchange(item.get("exchange", "NSE")),
            last_price=float(item.get("ltp", item.get("lastPrice", 0))),
            open=float(ohlc.get("open", item.get("open", 0))),
            high=float(ohlc.get("high", item.get("high", 0))),
            low=float(ohlc.get("low", item.get("low", 0))),
            close=float(ohlc.get("close", item.get("close", 0))),
            volume=int(item.get("volume", item.get("v", 0))),
            bid=float(item.get("bidPrice", item.get("bp", 0))),
            ask=float(item.get("askPrice", item.get("sp", 0))),
            timestamp=datetime.now(UTC),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_order(self, item: dict) -> NormalizedOrder:
        inst = self._parse_instrument(item.get("tradingSymbol", item.get("symbol", "")))
        return NormalizedOrder(
            id=str(item.get("orderId", item.get("OrderID", item.get("nOrdNo", "")))),
            broker_order_id=str(item.get("orderId", item.get("OrderID", ""))),
            symbol=item.get("tradingSymbol", item.get("symbol", "")),
            exchange=Exchange(item.get("exchange", "NSE")),
            side=OrderSide.BUY if item.get("transactionType", "").upper() == "BUY" else OrderSide.SELL,
            order_type=OrderType(item.get("orderType", "MARKET").upper()),
            product=ProductType.INTRADAY,
            quantity=int(item.get("quantity", item.get("qty", 0))),
            price=float(item.get("price", 0)),
            trigger_price=float(item.get("triggerPrice", 0)) if item.get("triggerPrice") else None,
            status=self._map_status(item.get("orderStatus", item.get("status", ""))),
            filled_quantity=int(item.get("filledQuantity", item.get("fillQty", 0))),
            average_price=float(item.get("averagePrice", item.get("avgPrice", 0))),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_position(self, item: dict) -> Position:
        inst = self._parse_instrument(item.get("tradingSymbol", item.get("symbol", "")))
        qty = int(item.get("netQty", item.get("quantity", 0)))
        buy_qty = int(item.get("buyQty", 0))
        sell_qty = int(item.get("sellQty", 0))
        return Position(
            symbol=item.get("tradingSymbol", item.get("symbol", "")),
            exchange=Exchange(item.get("exchange", "NSE")),
            quantity=qty,
            buy_quantity=buy_qty,
            sell_quantity=sell_qty,
            average_buy_price=float(item.get("buyAvgPrice", item.get("avgPrice", 0))),
            average_sell_price=float(item.get("sellAvgPrice", 0)),
            unrealised_pnl=float(item.get("unrealizedPL", item.get("mtm", 0))),
            realised_pnl=float(item.get("realizedPL", item.get("realizedPL", 0))),
            product=ProductType.INTRADAY,
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_holding(self, item: dict) -> Holding:
        return Holding(
            symbol=item.get("tradingSymbol", item.get("symbol", "")),
            exchange=Exchange.NSE,
            quantity=int(item.get("quantity", item.get("holdQty", 0))),
            average_price=float(item.get("averagePrice", item.get("avgPrice", 0))),
            current_price=float(item.get("lastPrice", item.get("ltp", 0))),
            pnl=float(item.get("pnl", item.get("profitLoss", 0))),
            broker=self.broker_name,
        )

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
        m = re.match(r'^([A-Z]+)(\d{2})([A-Z]{3})$', symbol.upper())
        if m:
            return {"instrument_type": InstrumentType.FUT, "strike_price": None, "expiry_date": None, "option_type": None}
        return {"instrument_type": InstrumentType.EQ, "strike_price": None, "expiry_date": None, "option_type": None}

    @staticmethod
    def _map_status(status: str) -> OrderStatus:
        mapping = {
            "PENDING": OrderStatus.PENDING,
            "OPEN": OrderStatus.OPEN,
            "COMPLETE": OrderStatus.FILLED,
            "FILLED": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "CANCELED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "TRIGGER_PENDING": OrderStatus.PENDING,
        }
        return mapping.get(status.upper(), OrderStatus.PENDING)
