import asyncio
import logging
import struct
from datetime import datetime
from typing import Callable, List

import httpx

from brokers.base import BaseBroker
from core.http_client import get_http_client
from core.models import (
    NormalizedOrder,
    OrderResult,
    Position,
    Holding,
    Funds,
    Quote,
    Candle,
    Tick,
    Session,
    OrderSide,
    OrderType,
    ProductType,
    OrderStatus,
    Exchange,
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
        if order.trigger_price:
            params["trigger_price"] = order.trigger_price

        resp = await client.post(
            f"{self._base_url}/orders/{order.exchange.value}",
            data=params,
            headers=self._headers(),
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
            f"{self._base_url}/orders/NSE/{order_id}",
            headers=self._headers(),
        )
        data = resp.json()
        return OrderResult(
            success=True,
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def get_orderbook(self) -> List[NormalizedOrder]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/orders", headers=self._headers())
        data = resp.json()
        return [self._normalize_order(o) for o in data.get("data", [])]

    async def get_positions(self) -> List[Position]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/portfolio/positions", headers=self._headers())
        data = resp.json()
        positions = []
        for item in data.get("data", {}).get("net", []):
            positions.append(self._normalize_position(item))
        return positions

    async def get_holdings(self) -> List[Holding]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/portfolio/holdings", headers=self._headers())
        data = resp.json()
        return [self._normalize_holding(h) for h in data.get("data", [])]

    async def get_funds(self) -> Funds:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/user/margins", headers=self._headers())
        data = resp.json()
        equity = data.get("data", {}).get("equity", {})
        return Funds(
            total_margin=float(equity.get("available", {}).get("live_balance", 0)) + float(equity.get("utilised", {}).get("debits", 0)),
            used_margin=float(equity.get("utilised", {}).get("debits", 0)),
            available_margin=float(equity.get("available", {}).get("live_balance", 0)),
            broker=self.broker_name,
        )

    async def get_quotes(self, symbols: List[str]) -> List[Quote]:
        client = await self._get_client()
        resp = await client.get(
            f"{self._base_url}/quote",
            params={"i": ",".join(symbols)},
            headers=self._headers(),
        )
        data = resp.json()
        quotes = []
        for sym, item in data.get("data", {}).items():
            quotes.append(self._normalize_quote(item, sym))
        return quotes

    async def get_historical(
        self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None
    ) -> List[Candle]:
        client = await self._get_client()
        params = {"from": start, "to": end, "interval": interval}
        resp = await client.get(
            f"{self._base_url}/instruments/historical/{symbol}/{interval}",
            params={"from": start, "to": end} if start and end else {},
            headers=self._headers(),
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

    async def stream(self, symbols: List[str], on_tick: Callable[[Tick], None]) -> None:
        if not self._access_token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        self._running = True
        retry_delay = 1

        while self._running:
            try:
                async with httpx.AsyncClient() as client:
                    ws_url = f"{self.KITE_WS_URL}?api_key={self._api_key}&access_token={self._access_token}"
                    async with client.stream("GET", ws_url) as resp:
                        if resp.status_code != 101:
                            logger.error("Zerodha WS connect failed: %s", resp.status_code)
                            await asyncio.sleep(retry_delay)
                            retry_delay = min(retry_delay * 2, 30)
                            continue

                        retry_delay = 1

                        async for chunk in resp.aiter_bytes():
                            if not self._running:
                                break
                            if len(chunk) < 4:
                                continue

                            ticks = self._parse_binary(chunk)
                            for tick in ticks:
                                if asyncio.iscoroutinefunction(on_tick):
                                    await on_tick(tick)
                                else:
                                    on_tick(tick)

            except Exception as e:
                logger.error("Zerodha WS error: %s, reconnecting in %ds", e, retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)

    async def disconnect(self) -> None:
        self._running = False
        self._client = None

    def _parse_binary(self, data: bytes) -> List[Tick]:
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
                    timestamp=datetime.fromtimestamp(ltt) if ltt else datetime.utcnow(),
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
        )

    def _normalize_position(self, item: dict) -> Position:
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
        return Quote(
            symbol=symbol or item.get("tradingsymbol", ""),
            exchange=Exchange.NSE,
            last_price=float(item.get("last_price", 0)),
            open=float(ohlc.get("open", 0)),
            high=float(ohlc.get("high", 0)),
            low=float(ohlc.get("low", 0)),
            close=float(ohlc.get("close", 0)),
            volume=int(item.get("volume", 0)),
            bid=float(item.get("depth", {}).get("buy", [{}])[0].get("price", 0)) if item.get("depth") else 0,
            ask=float(item.get("depth", {}).get("sell", [{}])[0].get("price", 0)) if item.get("depth") else 0,
            timestamp=datetime.utcnow(),
            broker=self.broker_name,
        )

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
