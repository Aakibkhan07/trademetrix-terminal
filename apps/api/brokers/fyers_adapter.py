import hmac
import hashlib
import json
import time
from datetime import datetime
from typing import Callable, List
from urllib.parse import urlencode

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


class FyersAdapter(BaseBroker):
    broker_name = "fyers"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._access_token: str = ""
        self._user_id: str = ""
        self._base_url = "https://api.fyers.in/api/v2"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = await get_http_client()
        return self._client

    async def authenticate(self, credentials: dict) -> Session:
        client_id = credentials.get("client_id", "")
        app_secret = credentials.get("secret_key", "")
        auth_code = credentials.get("auth_code", "")

        if not auth_code:
            raise ValueError("auth_code required for Fyers authentication")

        client = await get_http_client()
        resp = await client.post(
            f"{self._base_url}/validate-authcode",
            json={"client_id": client_id, "secret_key": app_secret, "auth_code": auth_code},
        )
            data = resp.json()
            if data.get("s") != "ok":
                raise ValueError(f"Fyers auth failed: {data.get('message', '')}")
            self._access_token = f"{client_id}:{data['access_token']}"
            self._user_id = data.get("user_profile", {}).get("fy_id", "")

        return Session(
            access_token=self._access_token,
            user_id=self._user_id,
            broker=self.broker_name,
            authenticated=True,
        )

    def _headers(self) -> dict:
        return {"Authorization": f"{self._access_token}"}

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        client = await self._get_client()
        payload = {
            "symbol": order.symbol,
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
        }
        resp = await client.post(f"{self._base_url}/orders", json=payload, headers=self._headers())
        data = resp.json()
        success = data.get("s") == "ok"
        return OrderResult(
            success=success,
            broker_order_id=data.get("id", ""),
            message=data.get("message", ""),
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        client = await self._get_client()
        payload = {"id": order_id, **changes}
        resp = await client.put(f"{self._base_url}/orders", json=payload, headers=self._headers())
        data = resp.json()
        return OrderResult(
            success=data.get("s") == "ok",
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        client = await self._get_client()
        resp = await client.delete(
            f"{self._base_url}/orders", params={"id": order_id}, headers=self._headers()
        )
        data = resp.json()
        return OrderResult(
            success=data.get("s") == "ok",
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def get_orderbook(self) -> List[NormalizedOrder]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/orders", headers=self._headers())
        data = resp.json()
        orders = []
        for item in data.get("orderBook", []):
            orders.append(self._normalize_order(item))
        return orders

    async def get_positions(self) -> List[Position]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/positions", headers=self._headers())
        data = resp.json()
        positions = []
        for item in data.get("netPositions", []):
            positions.append(self._normalize_position(item))
        return positions

    async def get_holdings(self) -> List[Holding]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/holdings", headers=self._headers())
        data = resp.json()
        holdings = []
        for item in data.get("holdings", []):
            holdings.append(self._normalize_holding(item))
        return holdings

    async def get_funds(self) -> Funds:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/funds", headers=self._headers())
        data = resp.json()
        funds = data.get("funds", {})
        return Funds(
            total_margin=float(funds.get("total_margin", 0)),
            used_margin=float(funds.get("used_margin", 0)),
            available_margin=float(funds.get("available_margin", 0)),
            broker=self.broker_name,
        )

    async def get_quotes(self, symbols: List[str]) -> List[Quote]:
        client = await self._get_client()
        resp = await client.post(
            f"{self._base_url}/quotes",
            json={"symbols": ",".join(symbols)},
            headers=self._headers(),
        )
        data = resp.json()
        quotes = []
        for item in data.get("d", []):
            quotes.append(self._normalize_quote(item))
        return quotes

    async def get_historical(
        self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None
    ) -> List[Candle]:
        client = await self._get_client()
        params = {"symbol": symbol, "resolution": interval, "date_format": "0"}
        if start:
            params["from"] = start
        if end:
            params["to"] = end
        if range:
            params["range"] = range
        resp = await client.get(f"{self._base_url}/historical", params=params, headers=self._headers())
        data = resp.json()
        candles = []
        for item in data.get("candles", []):
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
                    timestamp=datetime.fromtimestamp(item[0]),
                )
            )
        return candles

    async def stream(self, symbols: List[str], on_tick: Callable[[Tick], None]) -> None:
        raise NotImplementedError("Fyers WebSocket streaming not yet implemented")

    async def disconnect(self) -> None:
        self._client = None

    def _map_order_type(self, ot: OrderType) -> int:
        mapping = {OrderType.MARKET: 1, OrderType.LIMIT: 2, OrderType.SL: 3, OrderType.SLM: 4}
        return mapping.get(ot, 1)

    def _map_product(self, p: ProductType) -> str:
        mapping = {ProductType.INTRADAY: "INTRADAY", ProductType.DELIVERY: "DELIVERY", ProductType.MIS: "INTRADAY", ProductType.NRML: "DELIVERY"}
        return mapping.get(p, "INTRADAY")

    def _normalize_order(self, item: dict) -> NormalizedOrder:
        return NormalizedOrder(
            id=item.get("id", ""),
            broker_order_id=item.get("orderId", ""),
            symbol=item.get("symbol", ""),
            exchange=Exchange.NSE,
            side=OrderSide.BUY if item.get("side", 1) == 1 else OrderSide.SELL,
            order_type=OrderType.MARKET,
            product=ProductType.INTRADAY,
            quantity=int(item.get("qty", 0)),
            price=float(item.get("limitPrice", 0)),
            trigger_price=float(item.get("stopPrice", 0)) if item.get("stopPrice") else None,
            status=self._map_status(item.get("status", 0)),
            filled_quantity=int(item.get("filledQty", 0)),
            average_price=float(item.get("avgPrice", 0)),
            broker=self.broker_name,
        )

    def _normalize_position(self, item: dict) -> Position:
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

    def _normalize_quote(self, item: dict) -> Quote:
        return Quote(
            symbol=item.get("sym", ""),
            exchange=Exchange.NSE,
            last_price=float(item.get("ltp", 0)),
            open=float(item.get("open_price", 0)),
            high=float(item.get("high_price", 0)),
            low=float(item.get("low_price", 0)),
            close=float(item.get("prev_close_price", 0)),
            volume=int(item.get("vol_traded_today", 0)),
            bid=float(item.get("bid", 0)),
            ask=float(item.get("ask", 0)),
            timestamp=datetime.utcnow(),
            broker=self.broker_name,
        )

    @staticmethod
    def _map_status(code: int) -> OrderStatus:
        mapping = {1: OrderStatus.OPEN, 2: OrderStatus.PENDING, 3: OrderStatus.FILLED, 4: OrderStatus.CANCELLED, 5: OrderStatus.REJECTED, 6: OrderStatus.EXPIRED}
        return mapping.get(code, OrderStatus.PENDING)
