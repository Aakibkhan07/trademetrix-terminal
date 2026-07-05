import asyncio
import inspect
import json
import logging
import time
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

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._client_id: str = ""
        self._access_token: str = ""
        self._user_id: str = ""
        self._base_url = "https://api.fyers.in/api/v2"
        self._v3_url = "https://api.fyers.in/api/v3"
        self._ws_url = "wss://socket.fyers.in/socket"
        self._running = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = await get_http_client()
        return self._client

    def _headers(self) -> dict:
        return {
            "Authorization": f"{self._client_id}:{self._access_token}",
            "Content-Type": "application/json",
        }

    def _ensure_fyers_symbol(self, symbol: str) -> str:
        if ":" in symbol:
            return symbol.upper()
        if symbol.startswith("NSE:") or symbol.startswith("BSE:") or symbol.startswith("NFO:") or symbol.startswith("MCX:"):
            return symbol.upper()
        return f"NSE:{symbol.upper()}"

    async def authenticate(self, credentials: dict) -> Session:
        client_id = credentials.get("client_id", "")
        raw_token = credentials.get("access_token", "")

        self._client_id = client_id
        self._access_token = raw_token

        if raw_token:
            client = await self._get_client()
            resp = await client.get(
                f"{self._base_url}/profile",
                headers=self._headers(),
                timeout=httpx.Timeout(5, connect=3),
            )
            if resp.status_code == 401:
                raise ValueError("Fyers authentication failed — invalid access_token")
            data = resp.json()
            if data.get("s") != "ok":
                raise ValueError(f"Fyers auth validation failed: {data.get('message', 'unknown')}")
            self._user_id = data.get("data", {}).get("fy_id", "") or data.get("fy_id", "")
        else:
            auth_code = credentials.get("auth_code", "")
            app_secret = credentials.get("secret_key", "")
            if not auth_code or not app_secret:
                raise ValueError("auth_code and secret_key required for Fyers OAuth flow")
            client = await self._get_client()
            resp = await client.post(
                f"{self._base_url}/token",
                json={
                    "grant_type": "authorization_code",
                    "appIdHash": client_id,
                    "secret_key": app_secret,
                    "auth_code": auth_code,
                },
                timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
            )
            data = resp.json()
            if data.get("s") != "ok":
                raise ValueError(f"Fyers token exchange failed: {data.get('message', 'unknown')}")
            raw_token = data.get("access_token", "")
            self._access_token = raw_token

        return Session(
            access_token=raw_token,
            user_id=self._user_id or client_id,
            broker=self.broker_name,
            authenticated=True,
        )

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        client = await self._get_client()
        payload = {
            "symbol": self._ensure_fyers_symbol(order.symbol),
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
            "orderTag": order.client_order_id or "",
        }
        resp = await client.post(
            f"{self._base_url}/orders",
            json=payload,
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
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
        resp = await client.put(
            f"{self._base_url}/orders",
            json=payload,
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        return OrderResult(
            success=data.get("s") == "ok",
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
            success=data.get("s") == "ok",
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def get_orderbook(self) -> list[NormalizedOrder]:
        client = await self._get_client()
        resp = await client.get(
            f"{self._base_url}/orders",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        orders = []
        for item in data.get("orderBook", []):
            orders.append(self._normalize_order(item))
        return orders

    async def get_positions(self) -> list[Position]:
        client = await self._get_client()
        resp = await client.get(
            f"{self._base_url}/positions",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        positions = []
        for item in data.get("netPositions", []):
            positions.append(self._normalize_position(item))
        return positions

    async def get_holdings(self) -> list[Holding]:
        client = await self._get_client()
        resp = await client.get(
            f"{self._base_url}/holdings",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        holdings = []
        for item in data.get("holdings", []):
            holdings.append(self._normalize_holding(item))
        return holdings

    async def get_funds(self) -> Funds:
        client = await self._get_client()
        resp = await client.get(
            f"{self._base_url}/funds",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
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
        client = await self._get_client()
        resp = await client.post(
            f"{self._base_url}/quotes",
            json={"symbols": ",".join(self._ensure_fyers_symbol(s) for s in symbols)},
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        quotes = []
        for item in data.get("d", []):
            quotes.append(self._normalize_quote(item))
        return quotes

    async def get_historical(
        self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None
    ) -> list[Candle]:
        client = await self._get_client()
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
        resp = await client.post(
            f"{self._base_url}/history",
            json=params,
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
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

    async def stream(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        if not self._access_token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        self._running = True
        retry_delay = 1

        while self._running:
            try:
                async with httpx.AsyncClient() as client:
                    ws_url = f"{self._ws_url}?token={self._access_token}&client_id={self._client_id}"
                    async with client.stream("GET", ws_url) as resp:
                        if resp.status_code != 101:
                            logger.error("Fyers WS connect failed: %s", resp.status_code)
                            await asyncio.sleep(retry_delay)
                            retry_delay = min(retry_delay * 2, 30)
                            continue

                        retry_delay = 1
                        subscribe_msg = json.dumps({
                            "type": "subscribe",
                            "symbols": [self._ensure_fyers_symbol(s) for s in symbols],
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
                logger.error("Fyers WS error: %s, reconnecting in %ds", e, retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)

        retry_delay = 1
        while self._running:
            try:
                async with httpx.AsyncClient() as poll_client:
                    resp = await poll_client.post(
                        f"{self._base_url}/quotes",
                        json={"symbols": ",".join(self._ensure_fyers_symbol(s) for s in symbols)},
                        headers=self._headers(),
                        timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
                    )
                    data = resp.json()
                    for item in data.get("d", []):
                        v = item.get("v", {})
                        sym = v.get("symbol") or item.get("n", "")
                        lp = float(v.get("lp", 0))
                        change = float(v.get("ch", 0))
                        change_pct = float(v.get("chp", 0))
                        inst_type = InstrumentType.EQ
                        strike = None
                        expiry = None
                        opt_type = None
                        if ":" in sym:
                            parsed = self._parse_instrument(sym)
                            inst_type = parsed["instrument_type"]
                            strike = parsed["strike_price"]
                            expiry = parsed["expiry_date"]
                            opt_type = parsed["option_type"]
                        tick = Tick(
                            symbol=sym,
                            exchange=Exchange.NSE,
                            last_price=lp,
                            bid=float(v.get("bid", 0)),
                            ask=float(v.get("ask", 0)),
                            bid_qty=int(v.get("bid_size", 0)),
                            ask_qty=int(v.get("ask_size", 0)),
                            volume=int(v.get("volume", 0)),
                            oi=int(v.get("oi", 0)),
                            change=round(change, 2),
                            change_pct=round(change_pct, 2),
                            timestamp=datetime.now(UTC),
                            broker=self.broker_name,
                            instrument_type=inst_type,
                            strike_price=strike,
                            expiry_date=expiry,
                            option_type=opt_type,
                        )
                        if inspect.iscoroutinefunction(on_tick):
                            await on_tick(tick)
                        else:
                            on_tick(tick)
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Fyers polling error: %s", e)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)

    async def get_margin_estimate(self, legs: list[dict]) -> dict:
        if not self._access_token:
            return {"supported": False, "broker": self.broker_name}
        client = await self._get_client()
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
                resp = await client.post(
                    f"{self._v3_url}/span_margin",
                    json=payload,
                    headers=self._headers(),
                    timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
                )
                data = resp.json()
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
        self._client = None

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
        inst = self._parse_instrument(item.get("symbol", ""))
        return NormalizedOrder(
            id=item.get("id", ""),
            broker_order_id=item.get("id_fyers", ""),
            symbol=item.get("symbol", ""),
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
        inst = self._parse_instrument(item.get("symbol", ""))
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
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
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
        v = item.get("v", {})
        sym = v.get("symbol") or item.get("n", "")
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
        mapping = {OrderType.MARKET: 1, OrderType.LIMIT: 2, OrderType.SL: 3, OrderType.SLM: 4}
        return mapping.get(ot, 1)

    @staticmethod
    def _rev_map_order_type(code: int) -> OrderType:
        mapping = {1: OrderType.MARKET, 2: OrderType.LIMIT, 3: OrderType.SL, 4: OrderType.SLM}
        return mapping.get(code, OrderType.MARKET)

    @staticmethod
    def _map_product(p: ProductType) -> str:
        mapping = {
            ProductType.INTRADAY: "INTRADAY",
            ProductType.DELIVERY: "DELIVERY",
            ProductType.MIS: "INTRADAY",
            ProductType.NRML: "CNC",
        }
        return mapping.get(p, "INTRADAY")

    @staticmethod
    def _rev_map_product(code: str) -> ProductType:
        mapping = {"INTRADAY": ProductType.INTRADAY, "DELIVERY": ProductType.DELIVERY, "MARGIN": ProductType.INTRADAY, "CNC": ProductType.NRML}
        return mapping.get(code, ProductType.INTRADAY)

    @staticmethod
    def _map_status(code: int) -> OrderStatus:
        mapping = {
            1: OrderStatus.OPEN,
            2: OrderStatus.PENDING,
            3: OrderStatus.FILLED,
            4: OrderStatus.CANCELLED,
            5: OrderStatus.REJECTED,
            6: OrderStatus.EXPIRED,
        }
        return mapping.get(code, OrderStatus.PENDING)
