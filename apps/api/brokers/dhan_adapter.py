import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime

import httpx

from brokers.base import BaseBroker
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


class DhanAdapter(BaseBroker):
    broker_name = "dhan"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._access_token: str = ""
        self._client_id: str = ""
        self._base_url = "https://api.dhan.co/v2"
        self._ws_url = "wss://api.dhan.co/v2/ws"
        self._running = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = await get_http_client()
        return self._client

    async def authenticate(self, credentials: dict) -> Session:
        self._access_token = credentials.get("access_token") or credentials.get("secret_key") or ""
        self._client_id = credentials.get("client_id") or credentials.get("api_key") or credentials.get("dhanClientId") or ""
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
            "Content-Type": "application/json",
        }

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        client = await self._get_client()
        exchange_segment_map = {
            (Exchange.NSE, InstrumentType.EQ): "NSE_EQ",
            (Exchange.NFO, InstrumentType.FUT): "NSE_FNO",
            (Exchange.NFO, InstrumentType.OPT): "NSE_FNO",
            (Exchange.BSE, InstrumentType.EQ): "BSE_EQ",
        }
        seg = exchange_segment_map.get((order.exchange, order.instrument_type), "NSE_EQ")
        payload: dict = {
            "dhanClientId": self._client_id,
            "transactionType": self._map_side(order.side),
            "exchangeSegment": seg,
            "productType": self._map_product(order.product),
            "orderType": self._map_order_type(order.order_type),
            "validity": "DAY",
            "securityId": order.symbol,
            "quantity": order.quantity,
            "afterMarketOrder": False,
        }
        if order.price and order.price > 0:
            payload["price"] = order.price
        if order.trigger_price and order.trigger_price > 0:
            payload["triggerPrice"] = order.trigger_price
        if order.disclosed_quantity and order.disclosed_quantity > 0:
            payload["disclosedQuantity"] = order.disclosed_quantity
        if order.instrument_type in (InstrumentType.FUT, InstrumentType.OPT) and order.expiry_date:
            payload["drvExpiryDate"] = order.expiry_date
        if order.instrument_type == InstrumentType.OPT:
            if order.option_type:
                payload["drvOptionType"] = order.option_type.value
            if order.strike_price:
                payload["drvStrikePrice"] = order.strike_price
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
        payload = {
            "dhanClientId": self._client_id,
            "orderId": order_id,
            "orderType": changes.get("order_type", "LIMIT"),
            "productType": changes.get("product", "INTRADAY"),
            "validity": "DAY",
            "quantity": changes.get("quantity", 0),
            "price": changes.get("price", 0),
            "triggerPrice": changes.get("trigger_price", 0),
        }
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

    async def get_orderbook(self) -> list[NormalizedOrder]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/orders", headers=self._headers())
        data = resp.json()
        items = data if isinstance(data, list) else data.get("data", [])
        return [self._normalize_order(item) for item in items]

    async def get_positions(self) -> list[Position]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/positions", headers=self._headers())
        data = resp.json()
        items = data if isinstance(data, list) else data.get("data", [])
        return [self._normalize_position(item) for item in items]

    async def get_holdings(self) -> list[Holding]:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/holdings", headers=self._headers())
        data = resp.json()
        items = data if isinstance(data, list) else data.get("data", [])
        if not items and isinstance(data, dict) and "errorMessage" in data:
            return []
        return [self._normalize_holding(item) for item in items]

    async def get_funds(self) -> Funds:
        client = await self._get_client()
        resp = await client.get(f"{self._base_url}/fundlimit", headers=self._headers())
        data = resp.json()
        total = float(data.get("sodLimit", data.get("totalBalance", 0)))
        used = float(data.get("utilizedAmount", data.get("usedBalance", 0)))
        avail = float(data.get("availabelBalance", data.get("availableBalance", 0)))
        return Funds(
            total_margin=total,
            used_margin=used,
            available_margin=avail,
            broker=self.broker_name,
        )

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
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
    ) -> list[Candle]:
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

    async def stream(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        if not self._access_token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        self._running = True
        retry_delay = 1

        while self._running:
            try:
                async with httpx.AsyncClient() as client:
                    async with client.stream(
                        "GET",
                        self._ws_url,
                        headers={
                            "access-token": self._access_token,
                            "client-id": self._client_id,
                        },
                    ) as resp:
                        if resp.status_code != 200:
                            logger.error("Dhan WS connect failed: %s", resp.status_code)
                            await asyncio.sleep(retry_delay)
                            retry_delay = min(retry_delay * 2, 30)
                            continue

                        retry_delay = 1
                        subscribe_payload = {
                            "RequestCode": 1,
                            "ClientId": self._client_id,
                            "AuthToken": self._access_token,
                            "SymbolCount": len(symbols),
                            "SymbolList": [
                                {
                                    "ExchangeSegment": "NSE_EQ",
                                    "SecurityToken": sym,
                                }
                                for sym in symbols
                            ],
                        }

                        async with client.stream(
                            "POST",
                            f"{self._base_url}/feeds/ws",
                            json=subscribe_payload,
                            headers=self._headers(),
                        ) as ws:
                            async for line in ws.aiter_lines():
                                if not self._running:
                                    break
                                if not line.strip():
                                    continue
                                try:
                                    data = json.loads(line)
                                    tick = self._parse_tick(data)
                                    if tick:
                                        if asyncio.iscoroutinefunction(on_tick):
                                            await on_tick(tick)
                                        else:
                                            on_tick(tick)
                                except json.JSONDecodeError:
                                    continue

            except Exception as e:
                logger.error("Dhan WS error: %s, reconnecting in %ds", e, retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)

    async def disconnect(self) -> None:
        self._running = False
        self._client = None

    def _parse_tick(self, data: dict) -> Tick | None:
        try:
            return Tick(
                symbol=data.get("securityId", ""),
                exchange=Exchange.NSE,
                last_price=float(data.get("lastPrice", 0)),
                bid=float(data.get("bidPrice", 0)),
                ask=float(data.get("askPrice", 0)),
                bid_qty=int(data.get("bidQty", 0)),
                ask_qty=int(data.get("askQty", 0)),
                volume=int(data.get("volume", 0)),
                oi=int(data.get("openInterest", 0)),
                timestamp=datetime.utcnow(),
                broker=self.broker_name,
            )
        except (ValueError, KeyError, TypeError) as e:
            logger.warning("Failed to parse Dhan tick: %s", e)
            return None

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
        inst = self._parse_instrument(item.get("securityId", ""))
        return NormalizedOrder(
            id=item.get("orderId", ""),
            broker_order_id=item.get("orderId", ""),
            symbol=item.get("securityId", ""),
            exchange=Exchange(item.get("exchange", "NSE")),
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
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_position(self, item: dict) -> Position:
        inst = self._parse_instrument(item.get("securityId", ""))
        return Position(
            symbol=item.get("securityId", ""),
            exchange=Exchange(item.get("exchange", "NSE")),
            quantity=int(item.get("netQty", 0)),
            buy_quantity=int(item.get("buyQty", 0)),
            sell_quantity=int(item.get("sellQty", 0)),
            average_buy_price=float(item.get("avgBuyPrice", 0)),
            average_sell_price=float(item.get("avgSellPrice", 0)),
            unrealised_pnl=float(item.get("unrealizedPnl", 0)),
            realised_pnl=float(item.get("realizedPnl", 0)),
            product=ProductType.INTRADAY,
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
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
        inst = self._parse_instrument(item.get("securityId", ""))
        return Quote(
            symbol=item.get("securityId", ""),
            exchange=Exchange(item.get("exchange", "NSE")),
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
            return {"instrument_type": InstrumentType.FUT, "strike_price": None, "expiry_date": None, "option_type": None}
        return {"instrument_type": InstrumentType.EQ, "strike_price": None, "expiry_date": None, "option_type": None}

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
