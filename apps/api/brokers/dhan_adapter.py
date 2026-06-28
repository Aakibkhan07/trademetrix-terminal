from datetime import datetime
from typing import Callable, List

import httpx

from brokers.base import BaseBroker
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


class DhanAdapter(BaseBroker):
    broker_name = "dhan"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._access_token: str = ""
        self._client_id: str = ""
        self._base_url = "https://api.dhan.co/v2"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def authenticate(self, credentials: dict) -> Session:
        self._access_token = credentials.get("access_token", "")
        self._client_id = credentials.get("client_id", "")
        if not self._access_token:
            raise ValueError("access_token required for Dhan authentication")
        return Session(
            access_token=self._access_token,
            user_id=self._client_id,
            broker=self.broker_name,
            authenticated=True,
        )

    def _headers(self) -> dict:
        return {
            "access-token": self._access_token,
            "client-id": self._client_id,
        }

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        client = await self._get_client()
        payload = {
            "dhanClientId": self._client_id,
            "transactionType": self._map_side(order.side),
            "exchange": order.exchange.value,
            "segments": "EQ",
            "productType": self._map_product(order.product),
            "orderType": self._map_order_type(order.order_type),
            "securityId": order.symbol,
            "quantity": order.quantity,
            "price": order.price or 0,
            "triggerPrice": order.trigger_price or 0,
            "afterMarket": False,
            "validity": "DAY",
        }
        resp = await client.post(f"{self._base_url}/orders", json=payload, headers=self._headers())
        data = resp.json()
        success = data.get("status") == "success"
        return OrderResult(
            success=success,
            broker_order_id=data.get("orderId", ""),
            message=data.get("message", ""),
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        client = await self._get_client()
        payload = {"orderId": order_id, **changes}
        resp = await client.put(f"{self._base_url}/orders/{order_id}", json=payload, headers=self._headers())
        data = resp.json()
        return OrderResult(
            success=data.get("status") == "success",
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        client = await self._get_client()
        resp = await client.delete(f"{self._base_url}/orders/{order_id}", headers=self._headers())
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
        return [self._normalize_order(item) for item in data.get("data", [])]

    async def get_positions(self) -> List[Position]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/positions", headers=self._headers())
        data = resp.json()
        return [self._normalize_position(item) for item in data.get("data", [])]

    async def get_holdings(self) -> List[Holding]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/holdings", headers=self._headers())
        data = resp.json()
        return [self._normalize_holding(item) for item in data.get("data", [])]

    async def get_funds(self) -> Funds:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/funds", headers=self._headers())
        data = resp.json()
        fund_data = data.get("data", {})
        return Funds(
            total_margin=float(fund_data.get("totalBalance", 0)),
            used_margin=float(fund_data.get("usedBalance", 0)),
            available_margin=float(fund_data.get("availableBalance", 0)),
            broker=self.broker_name,
        )

    async def get_quotes(self, symbols: List[str]) -> List[Quote]:
        client = await self._get_client()
        resp = await client.get(
            f"{self._base_url}/quotes", params={"symbols": ",".join(symbols)}, headers=self._headers()
        )
        data = resp.json()
        quotes = []
        for item in data.get("data", []):
            quotes.append(self._normalize_quote(item))
        return quotes

    async def get_historical(
        self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None
    ) -> List[Candle]:
        client = await self._get_client()
        params = {"securityId": symbol, "exchangeSegment": "NSE", "interval": interval}
        if start:
            params["from"] = start
        if end:
            params["to"] = end
        resp = await client.get(f"{self._base_url}/charts/historical", params=params, headers=self._headers())
        data = resp.json()
        candles = []
        for item in data.get("data", []):
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
                    timestamp=datetime.fromisoformat(item.get("timestamp", "")),
                )
            )
        return candles

    async def stream(self, symbols: List[str], on_tick: Callable[[Tick], None]) -> None:
        raise NotImplementedError("Dhan WebSocket streaming not yet implemented")

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def _map_side(side: OrderSide) -> str:
        return "BUY" if side == OrderSide.BUY else "SELL"

    @staticmethod
    def _map_order_type(ot: OrderType) -> str:
        mapping = {OrderType.MARKET: "MARKET", OrderType.LIMIT: "LIMIT", OrderType.SL: "STOP_LOSS", OrderType.SLM: "STOP_LOSS_MARKET"}
        return mapping.get(ot, "MARKET")

    @staticmethod
    def _map_product(p: ProductType) -> str:
        mapping = {ProductType.INTRADAY: "INTRADAY", ProductType.DELIVERY: "DELIVERY", ProductType.MIS: "INTRADAY", ProductType.NRML: "DELIVERY"}
        return mapping.get(p, "INTRADAY")

    def _normalize_order(self, item: dict) -> NormalizedOrder:
        return NormalizedOrder(
            id=item.get("orderId", ""),
            broker_order_id=item.get("orderId", ""),
            symbol=item.get("securityId", ""),
            exchange=Exchange.NSE,
            side=OrderSide.BUY if item.get("transactionType") == "BUY" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            product=ProductType.INTRADAY,
            quantity=int(item.get("quantity", 0)),
            price=float(item.get("price", 0)),
            trigger_price=float(item.get("triggerPrice", 0)) if item.get("triggerPrice") else None,
            status=self._map_status(item.get("orderStatus", "")),
            filled_quantity=int(item.get("filledQuantity", 0)),
            average_price=float(item.get("averageTradedPrice", 0)),
            broker=self.broker_name,
        )

    def _normalize_position(self, item: dict) -> Position:
        return Position(
            symbol=item.get("securityId", ""),
            exchange=Exchange.NSE,
            quantity=int(item.get("netQty", 0)),
            buy_quantity=int(item.get("buyQty", 0)),
            sell_quantity=int(item.get("sellQty", 0)),
            average_buy_price=float(item.get("avgBuyPrice", 0)),
            average_sell_price=float(item.get("avgSellPrice", 0)),
            unrealised_pnl=float(item.get("unrealizedPnl", 0)),
            realised_pnl=float(item.get("realizedPnl", 0)),
            product=ProductType.INTRADAY,
            broker=self.broker_name,
        )

    def _normalize_holding(self, item: dict) -> Holding:
        return Holding(
            symbol=item.get("securityId", ""),
            exchange=Exchange.NSE,
            quantity=int(item.get("quantity", 0)),
            average_price=float(item.get("averagePrice", 0)),
            current_price=float(item.get("currentPrice", 0)),
            pnl=float(item.get("pnl", 0)),
            broker=self.broker_name,
        )

    def _normalize_quote(self, item: dict) -> Quote:
        return Quote(
            symbol=item.get("securityId", ""),
            exchange=Exchange.NSE,
            last_price=float(item.get("lastPrice", 0)),
            open=float(item.get("open", 0)),
            high=float(item.get("high", 0)),
            low=float(item.get("low", 0)),
            close=float(item.get("close", 0)),
            volume=int(item.get("volume", 0)),
            bid=float(item.get("bid", 0)),
            ask=float(item.get("ask", 0)),
            timestamp=datetime.utcnow(),
            broker=self.broker_name,
        )

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
