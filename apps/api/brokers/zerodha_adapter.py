import asyncio
import inspect
import json
import logging
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


class ZerodhaAdapter(BaseBroker):
    broker_name = "zerodha"

    KITE_WS_URL = "wss://ws.kite.trade"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._access_token: str = ""
        self._api_key: str = ""
        self._base_url = "https://api.kite.trade"
        self._running = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = await get_http_client()
        return self._client

    async def authenticate(self, credentials: dict) -> Session:
        self._api_key = credentials.get("client_id", "")
        self._access_token = credentials.get("access_token", "")

        if not self._api_key or not self._access_token:
            request_token = credentials.get("request_token", "")
            secret_key = credentials.get("secret_key", "")
            if request_token and secret_key:
                client = await get_http_client()
                resp = await client.post(
                    "https://api.kite.trade/session/token",
                    data={
                        "api_key": self._api_key,
                        "request_token": request_token,
                        "checksum": self._api_key + request_token + secret_key,
                    },
                    headers={"X-Kite-Version": "3"},
                    timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
                )
                data = resp.json()
                if data.get("status") == "error":
                    raise ValueError(f"Zerodha auth failed: {data.get('error_type', '')}")
                self._access_token = data.get("data", {}).get("access_token", "")

        if not self._access_token:
            raise ValueError("access_token required for Zerodha authentication")

        return Session(
            access_token=self._access_token,
            user_id=self._api_key,
            broker=self.broker_name,
            authenticated=True,
        )

    def _headers(self) -> dict:
        return {
            "X-Kite-Version": "3",
            "Authorization": f"token {self._api_key}:{self._access_token}",
        }

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        client = await self._get_client()
        params = {
            "tradingsymbol": order.symbol,
            "exchange": order.exchange.value,
            "transaction_type": self._map_side(order.side),
            "quantity": order.quantity,
            "price": order.price or 0,
            "product": self._map_product(order.product),
            "order_type": self._map_order_type(order.order_type),
            "validity": "DAY",
        }
        if order.client_order_id:
            params["order_tag"] = order.client_order_id
        if order.trigger_price:
            params["trigger_price"] = order.trigger_price

        resp = await client.post(
            f"{self._base_url}/orders/{order.exchange.value}",
            data=params,
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        success = data.get("status") == "success"
        return OrderResult(
            success=success,
            broker_order_id=data.get("data", {}).get("order_id", ""),
            message=data.get("message", ""),
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        client = await self._get_client()
        resp = await client.put(
            f"{self._base_url}/orders/{changes.get('exchange', 'NSE')}/{order_id}",
            data=changes,
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        return OrderResult(
            success=data.get("status") == "success",
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
        data = resp.json()
        return OrderResult(
            success=True,
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def get_orderbook(self) -> list[NormalizedOrder]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/orders", headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        return [self._normalize_order(o) for o in data.get("data", [])]

    async def get_positions(self) -> list[Position]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/portfolio/positions", headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        positions = []
        for item in data.get("data", {}).get("net", []):
            positions.append(self._normalize_position(item))
        return positions

    async def get_holdings(self) -> list[Holding]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/portfolio/holdings", headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        return [self._normalize_holding(h) for h in data.get("data", [])]

    async def get_funds(self) -> Funds:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/user/margins", headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        equity = data.get("data", {}).get("equity", {})
        return Funds(
            total_margin=float(equity.get("available", {}).get("live_balance", 0)) + float(equity.get("utilised", {}).get("debits", 0)),
            used_margin=float(equity.get("utilised", {}).get("debits", 0)),
            available_margin=float(equity.get("available", {}).get("live_balance", 0)),
            broker=self.broker_name,
        )

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        client = await self._get_client()
        resp = await client.get(
            f"{self._base_url}/quote",
            params={"i": ",".join(symbols)},
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
        resp = await client.get(
            f"{self._base_url}/instruments/historical/{symbol}/{interval}",
            params={"from": start, "to": end} if start and end else {},
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        candles = []
        for item in data.get("data", {}).get("candles", []):
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
                    timestamp=datetime.fromisoformat(item[0].replace("T", " ")) if isinstance(item[0], str) else datetime.fromtimestamp(item[0]),
                )
            )
        return candles

    async def stream(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        if not self._access_token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        self._running = True
        import websockets
        ws_url = f"{self.KITE_WS_URL}?api_key={self._api_key}&access_token={self._access_token}"
        while self._running:
            try:
                async with websockets.connect(ws_url, ping_interval=5, ping_timeout=3) as ws:
                    subscribe_msg = json.dumps({"a": "subscribe", "v": symbols})
                    await ws.send(subscribe_msg)
                    while self._running:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30)
                        if isinstance(raw, bytes):
                            ticks = self._parse_binary(raw)
                            for t in ticks:
                                if inspect.iscoroutinefunction(on_tick):
                                    await on_tick(t)
                                else:
                                    on_tick(t)
                        elif isinstance(raw, str):
                            try:
                                msg = json.loads(raw)
                                if "error" in msg or msg.get("type") == "error":
                                    logger.warning("Zerodha WS error: %s", msg)
                            except json.JSONDecodeError:
                                pass
            except asyncio.TimeoutError:
                logger.warning("Zerodha WS recv timeout, reconnecting...")
            except websockets.ConnectionClosed:
                logger.warning("Zerodha WS disconnected, reconnecting...")
            except Exception:
                logger.exception("Zerodha WS error")
            await asyncio.sleep(1.0)

    async def disconnect(self) -> None:
        self._running = False
        self._client = None

    def _parse_binary(self, data: bytes) -> list[Tick]:
        ticks = []
        try:
            offset = 0
            while offset + 4 <= len(data):
                token = struct.unpack(">I", data[offset : offset + 4])[0]
                offset += 4
                if offset + 28 > len(data):
                    break

                ltp = struct.unpack(">I", data[offset + 4 : offset + 8])[0] / 100.0
                ltt = struct.unpack(">I", data[offset + 8 : offset + 12])[0]
                oi = struct.unpack(">I", data[offset + 12 : offset + 16])[0]
                volume = struct.unpack(">I", data[offset + 16 : offset + 20])[0]
                bp = struct.unpack(">H", data[offset + 20 : offset + 22])[0] / 100.0
                bq = struct.unpack(">H", data[offset + 22 : offset + 24])[0]
                ap = struct.unpack(">H", data[offset + 24 : offset + 26])[0] / 100.0
                aq = struct.unpack(">H", data[offset + 26 : offset + 28])[0]
                offset += 28

                tick = Tick(
                    symbol=str(token),
                    exchange=Exchange.NSE,
                    last_price=ltp,
                    bid=bp,
                    ask=ap,
                    bid_qty=bq,
                    ask_qty=aq,
                    volume=volume,
                    oi=oi,
                    timestamp=datetime.fromtimestamp(ltt) if ltt else datetime.now(UTC),
                    broker=self.broker_name,
                )
                ticks.append(tick)
        except struct.error as e:
            logger.warning("Failed to parse Zerodha binary tick: %s", e)
        return ticks

    @staticmethod
    def _map_side(side: OrderSide) -> str:
        return "BUY" if side == OrderSide.BUY else "SELL"

    @staticmethod
    def _map_order_type(ot: OrderType) -> str:
        mapping = {OrderType.MARKET: "MARKET", OrderType.LIMIT: "LIMIT", OrderType.SL: "SL", OrderType.SLM: "SLM"}
        return mapping.get(ot, "MARKET")

    @staticmethod
    def _map_product(p: ProductType) -> str:
        mapping = {ProductType.INTRADAY: "MIS", ProductType.DELIVERY: "CNC", ProductType.MIS: "MIS", ProductType.NRML: "NRML"}
        return mapping.get(p, "MIS")

    def _normalize_order(self, item: dict) -> NormalizedOrder:
        inst = self._parse_instrument(item.get("tradingsymbol", ""))
        return NormalizedOrder(
            id=item.get("order_id", ""),
            broker_order_id=item.get("order_id", ""),
            symbol=item.get("tradingsymbol", ""),
            exchange=Exchange(item.get("exchange", "NSE")),
            side=OrderSide.BUY if item.get("transaction_type") == "BUY" else OrderSide.SELL,
            order_type=OrderType(item.get("order_type", "MARKET").upper()),
            product=ProductType.INTRADAY,
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
        inst = self._parse_instrument(item.get("tradingsymbol", ""))
        return Position(
            symbol=item.get("tradingsymbol", ""),
            exchange=Exchange(item.get("exchange", "NSE")),
            quantity=int(item.get("quantity", 0)),
            buy_quantity=int(item.get("buy_quantity", 0)) if item.get("buy_quantity") else 0,
            sell_quantity=int(item.get("sell_quantity", 0)) if item.get("sell_quantity") else 0,
            average_buy_price=float(item.get("average_price", 0)),
            unrealised_pnl=float(item.get("unrealised", 0)),
            realised_pnl=float(item.get("realised", 0)),
            m2m=float(item.get("m2m", 0)),
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
            exchange=Exchange(item.get("exchange", "NSE")),
            quantity=int(item.get("quantity", 0)),
            t1_quantity=int(item.get("t1_quantity", 0)),
            average_price=float(item.get("average_price", 0)),
            current_price=float(item.get("last_price", 0)),
            pnl=float(item.get("pnl", 0)),
            broker=self.broker_name,
        )

    def _normalize_quote(self, item: dict, symbol: str = "") -> Quote:
        ohlc = item.get("ohlc", {})
        sym = symbol or item.get("tradingsymbol", "")
        inst = self._parse_instrument(sym)
        return Quote(
            symbol=sym,
            exchange=Exchange(item.get("exchange", "NSE")),
            last_price=float(item.get("last_price", 0)),
            open=float(ohlc.get("open", 0)),
            high=float(ohlc.get("high", 0)),
            low=float(ohlc.get("low", 0)),
            close=float(ohlc.get("close", 0)),
            volume=int(item.get("volume", 0)),
            bid=float(item.get("depth", {}).get("buy", [{}])[0].get("price", 0)) if item.get("depth") else 0,
            ask=float(item.get("depth", {}).get("sell", [{}])[0].get("price", 0)) if item.get("depth") else 0,
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
            return {
                "instrument_type": InstrumentType.FUT,
                "strike_price": None, "expiry_date": None, "option_type": None,
            }
        return {
            "instrument_type": InstrumentType.EQ,
            "strike_price": None, "expiry_date": None, "option_type": None,
        }

    @staticmethod
    def _map_status(status: str) -> OrderStatus:
        mapping = {
            "PENDING": OrderStatus.PENDING,
            "OPEN": OrderStatus.OPEN,
            "COMPLETE": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
        }
        return mapping.get(status.upper(), OrderStatus.PENDING)
