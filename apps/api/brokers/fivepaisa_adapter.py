import asyncio
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


class FivePaisaAdapter(BaseBroker):
    broker_name = "fivepaisa"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._access_token: str = ""
        self._client_code: str = ""
        self._app_name = "TradeMetrix"
        self._base_url = "https://Openapi.5paisa.com/Vendors"
        self._running = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = await get_http_client()
        return self._client

    async def authenticate(self, credentials: dict) -> Session:
        self._access_token = credentials.get("access_token") or credentials.get("secret_key") or ""
        self._client_code = credentials.get("client_code") or credentials.get("client_id") or credentials.get("api_key") or ""

        if not self._access_token and self._client_code:
            pin = credentials.get("additional_params", {}).get("pin", "")
            totp = credentials.get("additional_params", {}).get("totp_secret", "")
            app_key = credentials.get("api_key", "")
            if pin and totp and app_key:
                client = await self._get_client()
                payload = {
                    "head": {
                        "AppName": self._app_name,
                        "AppVer": "1.0.0",
                        "Key": app_key,
                        "OSName": "Web",
                        "RequestCode": "5PaisaClientLogin",
                        "UserID": self._client_code,
                    },
                    "body": {
                        "ClientCode": self._client_code,
                        "TOTP": totp,
                        "PIN": pin,
                    },
                }
                resp = await client.post(f"{self._base_url}/Login", json=payload, timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
                data = resp.json()
                body = data.get("body", {})
                self._access_token = body.get("JWTToken", "")
                if not self._access_token:
                    raise ValueError(f"5Paisa login failed: {data.get('message', '')}")

        if not self._access_token:
            raise ValueError("access_token required for 5Paisa authentication")

        return Session(
            access_token=self._access_token,
            user_id=self._client_code,
            broker=self.broker_name,
            authenticated=True,
        )

    def _headers(self) -> dict:
        headers = {
            "Authorization": f"bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        if self._client_code:
            headers["ClientCode"] = self._client_code
        return headers

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        client = await self._get_client()
        payload = {
            "head": {
                "AppName": self._app_name,
                "AppVer": "1.0.0",
                "Key": "",
                "OSName": "Web",
                "RequestCode": "PlaceOrderRequest",
                "UserID": self._client_code,
            },
            "body": {
                "ClientCode": self._client_code,
                "Qty": order.quantity,
                "OrderType": self._map_order_type(order.order_type),
                "Price": order.price or 0,
                "TriggerPrice": order.trigger_price or 0,
                "Exchange": self._map_exchange(order.exchange),
                "ExchangeType": "C",
                "ScripCode": self._extract_scripcode(order.symbol),
                "IsIntraday": order.product in (ProductType.INTRADAY, ProductType.MIS),
                "RemoteOrderID": f"TM{int(datetime.now(UTC).timestamp())}",
            },
        }
        resp = await client.post(f"{self._base_url}/PlaceOrder", json=payload, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        body = data.get("body", {})
        success = body.get("Message", "").lower() == "success"
        return OrderResult(
            success=success,
            broker_order_id=str(body.get("OrderNo", "")),
            message=body.get("Message", ""),
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        client = await self._get_client()
        payload = {
            "head": {
                "AppName": self._app_name,
                "AppVer": "1.0.0",
                "Key": "",
                "OSName": "Web",
                "RequestCode": "ModifyOrderRequest",
                "UserID": self._client_code,
            },
            "body": {
                "ClientCode": self._client_code,
                "OrderNo": int(order_id),
                "Qty": changes.get("quantity", 0),
                "OrderType": self._map_order_type_str(changes.get("order_type", "MARKET")),
                "Price": changes.get("price", 0),
                "TriggerPrice": changes.get("trigger_price", 0),
                "IsIntraday": changes.get("product", "INTRADAY") in ("INTRADAY", "MIS"),
            },
        }
        resp = await client.put(f"{self._base_url}/ModifyOrder", json=payload, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        body = data.get("body", {})
        return OrderResult(
            success=body.get("Message", "").lower() == "success",
            broker_order_id=order_id,
            message=body.get("Message", ""),
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        client = await self._get_client()
        payload = {
            "head": {
                "AppName": self._app_name,
                "AppVer": "1.0.0",
                "Key": "",
                "OSName": "Web",
                "RequestCode": "CancelOrderRequest",
                "UserID": self._client_code,
            },
            "body": {
                "ClientCode": self._client_code,
                "OrderNo": int(order_id),
            },
        }
        resp = await client.post(f"{self._base_url}/CancelOrder", json=payload, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        return OrderResult(
            success=True,
            broker_order_id=order_id,
            message=data.get("body", {}).get("Message", ""),
        )

    async def get_orderbook(self) -> list[NormalizedOrder]:
        client = await self._get_client()
        payload = {
            "head": {
                "AppName": self._app_name,
                "AppVer": "1.0.0",
                "Key": "",
                "OSName": "Web",
                "RequestCode": "OrderBookRequest",
                "UserID": self._client_code,
            },
            "body": {"ClientCode": self._client_code},
        }
        resp = await client.post(f"{self._base_url}/OrderBook", json=payload, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        items = data.get("body", {}).get("OrderBookDetail", [])
        return [self._normalize_order(item) for item in items]

    async def get_positions(self) -> list[Position]:
        client = await self._get_client()
        payload = {
            "head": {
                "AppName": self._app_name,
                "AppVer": "1.0.0",
                "Key": "",
                "OSName": "Web",
                "RequestCode": "PositionBookRequest",
                "UserID": self._client_code,
            },
            "body": {"ClientCode": self._client_code},
        }
        resp = await client.post(f"{self._base_url}/PositionBook", json=payload, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        items = data.get("body", {}).get("PositionBookDetail", [])
        return [self._normalize_position(item) for item in items]

    async def get_holdings(self) -> list[Holding]:
        return []

    async def get_funds(self) -> Funds:
        client = await self._get_client()
        payload = {
            "head": {
                "AppName": self._app_name,
                "AppVer": "1.0.0",
                "Key": "",
                "OSName": "Web",
                "RequestCode": "MarginRequest",
                "UserID": self._client_code,
            },
            "body": {"ClientCode": self._client_code},
        }
        resp = await client.post(f"{self._base_url}/Margin", json=payload, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
        data = resp.json()
        body = data.get("body", {})
        return Funds(
            total_margin=float(body.get("TotalMargin", 0)),
            used_margin=float(body.get("AmountUsed", 0)),
            available_margin=float(body.get("AvailableMargin", 0)),
            broker=self.broker_name,
        )

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        if not symbols or not self._access_token:
            return []
        client = await self._get_client()
        scrap_codes = [self._extract_scripcode(s) for s in symbols]
        payload = {
            "head": {
                "AppName": self._app_name,
                "AppVer": "1.0.0",
                "Key": "",
                "OSName": "Web",
                "RequestCode": "GetMarketFeed",
                "UserID": self._client_code,
            },
            "body": {
                "ClientCode": self._client_code,
                "Count": len(scrap_codes),
                "MarketFeedData": [
                    {"Exchange": "N", "ScripCode": sc, "ScripType": 1 if sc < 99999 else 2}
                    for sc in scrap_codes if sc > 0
                ],
            },
        }
        if not payload["body"]["MarketFeedData"]:
            return []
        try:
            resp = await client.post(f"{self._base_url}/MarketFeed", json=payload, headers=self._headers(), timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout))
            data = resp.json()
            items = data.get("body", {}).get("Data", [])
            quotes = []
            for item in items:
                ltp = float(item.get("LastTradedPrice", item.get("LTP", 0)))
                quotes.append(Quote(
                    symbol=str(item.get("ScripCode", "")),
                    last_price=ltp,
                    change=float(item.get("NetPriceChange", 0)),
                    change_percent=float(item.get("PercentageChange", 0)),
                    volume=item.get("Volume", 0),
                    bid=float(item.get("BuyPrice", item.get("Bid", 0))),
                    ask=float(item.get("SellPrice", item.get("Ask", 0))),
                    high=float(item.get("High", 0)),
                    low=float(item.get("Low", 0)),
                    open=float(item.get("Open", 0)),
                    close=float(item.get("PreviousClose", 0)),
                ))
            return quotes
        except Exception:
            logger.exception("5Paisa get_quotes failed")
            return []

    async def get_historical(
        self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None
    ) -> list[Candle]:
        return []

    async def stream(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        if not symbols:
            return
        self._running = True
        while self._running:
            try:
                quotes = await self.get_quotes(symbols)
                for q in quotes:
                    tick = Tick(
                        symbol=q.symbol,
                        price=q.last_price,
                        change=q.change,
                        change_percent=q.change_percent,
                        volume=q.volume,
                        bid=q.bid,
                        ask=q.ask,
                        high=q.high,
                        low=q.low,
                        open=q.open,
                        close=q.close,
                    )
                    on_tick(tick)
            except Exception:
                logger.exception("5Paisa stream polling error")
            await asyncio.sleep(1.0)

    async def disconnect(self) -> None:
        self._running = False
        self._client = None

    @staticmethod
    def _extract_scripcode(symbol: str) -> int:
        try:
            return int(re.sub(r'\D', '', symbol.split('|')[0] if '|' in symbol else symbol))
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _map_side(side: OrderSide) -> str:
        return "B" if side == OrderSide.BUY else "S"

    @staticmethod
    def _map_order_type(ot: OrderType) -> int:
        mapping = {OrderType.MARKET: 1, OrderType.LIMIT: 2, OrderType.SL: 4, OrderType.SLM: 5}
        return mapping.get(ot, 1)

    @staticmethod
    def _map_order_type_str(ot: str) -> int:
        mapping = {"MARKET": 1, "LIMIT": 2, "SL": 4, "SLM": 5}
        return mapping.get(ot, 1)

    @staticmethod
    def _map_product(p: ProductType) -> str:
        return "I" if p in (ProductType.INTRADAY, ProductType.MIS) else "D"

    @staticmethod
    def _map_exchange(exchange: Exchange) -> str:
        mapping = {Exchange.NSE: "N", Exchange.BSE: "B", Exchange.NFO: "N", Exchange.MCX: "M"}
        return mapping.get(exchange, "N")

    def _normalize_order(self, item: dict) -> NormalizedOrder:
        return NormalizedOrder(
            id=str(item.get("OrderNo", "")),
            broker_order_id=str(item.get("OrderNo", "")),
            symbol=str(item.get("ScripName", item.get("ScripCode", ""))),
            exchange=Exchange.NSE,
            side=OrderSide.BUY if item.get("BuySell", "") == "B" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            product=ProductType.INTRADAY if item.get("Intraday", "") == "Y" else ProductType.DELIVERY,
            quantity=int(item.get("Qty", 0)),
            price=float(item.get("Rate", 0)),
            trigger_price=float(item.get("TriggerPrice", 0)) if item.get("TriggerPrice") else None,
            status=self._map_status(item.get("OrderStatus", "")),
            filled_quantity=int(item.get("FillQty", 0)),
            average_price=float(item.get("AvgRate", 0)),
            broker=self.broker_name,
            instrument_type=InstrumentType.EQ,
            strike_price=None,
            expiry_date=None,
            option_type=None,
        )

    def _normalize_position(self, item: dict) -> Position:
        qty = int(item.get("NetQty", item.get("Qty", 0)))
        buy_qty = int(item.get("BuyQty", 0))
        sell_qty = int(item.get("SellQty", 0))
        if not buy_qty and not sell_qty and qty != 0:
            buy_qty = qty if qty > 0 else 0
            sell_qty = abs(qty) if qty < 0 else 0
        return Position(
            symbol=str(item.get("ScripName", item.get("ScripCode", ""))),
            exchange=Exchange.NSE,
            quantity=qty,
            buy_quantity=buy_qty,
            sell_quantity=sell_qty,
            average_buy_price=float(item.get("BuyAvgRate", item.get("Rate", 0))),
            unrealised_pnl=float(item.get("MTM", 0)),
            realised_pnl=float(item.get("RealizedPL", 0)),
            product=ProductType.INTRADAY,
            broker=self.broker_name,
            instrument_type=InstrumentType.EQ,
            strike_price=None,
            expiry_date=None,
            option_type=None,
        )

    @staticmethod
    def _map_status(status: str) -> OrderStatus:
        mapping = {
            "1": OrderStatus.PENDING,
            "2": OrderStatus.FILLED,
            "3": OrderStatus.CANCELLED,
            "4": OrderStatus.REJECTED,
            "5": OrderStatus.PENDING,
        }
        return mapping.get(str(status).strip(), OrderStatus.PENDING)
