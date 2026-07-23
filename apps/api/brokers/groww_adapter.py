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


def _dict_val(d: dict, *keys: str, default=None):
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return default


class GrowwAdapter(BaseBroker):
    broker_name = "groww"

    def __init__(self):
        self._base_url = "https://api.groww.in/v1/api"
        self._token: str = ""
        self._user_id: str = ""
        self._user_name: str = ""
        self._running = False

    async def authenticate(self, credentials: dict) -> Session:
        token = credentials.get("access_token", "")
        user_id = credentials.get("client_code", "") or credentials.get("client_id", "") or credentials.get("user_id", "")

        if token:
            self._token = token
            self._user_id = user_id
            return Session(
                access_token=token,
                user_id=user_id or "groww_user",
                broker=self.broker_name,
                authenticated=True,
            )

        phone = credentials.get("phone", "") or credentials.get("username", "")
        otp = credentials.get("otp", "") or credentials.get("secret_key", "")
        password = credentials.get("password", "") or credentials.get("secret_key", "")

        client = await get_http_client()
        headers = self._headers()
        headers.pop("Authorization", None)

        if phone and not otp:
            resp = await client.post(
                f"{self._base_url}/groww/login/v2/login_via_otp",
                json={"phone": phone},
                headers=headers,
                timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
            )
            data = resp.json()
            if data.get("status") == "success":
                logger.info("OTP sent to %s", phone[-4:])
                return Session(
                    access_token="",
                    user_id=phone,
                    broker=self.broker_name,
                    authenticated=False,
                    message="OTP sent. Provide otp to complete login.",
                )
            raise ValueError(f"Groww OTP request failed: {data.get('message', data.get('error', 'unknown'))}")

        if phone and otp:
            resp = await client.post(
                f"{self._base_url}/groww/login/v2/verify_otp",
                json={"phone": phone, "otp": otp},
                headers=headers,
                timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
            )
            data = resp.json()
            token = data.get("data", {}).get("token") or data.get("token", "")
            uid = data.get("data", {}).get("userId") or data.get("userId", "") or phone
            if token:
                self._token = token
                self._user_id = uid
                return Session(
                    access_token=token,
                    user_id=uid,
                    broker=self.broker_name,
                    authenticated=True,
                )
            raise ValueError(f"Groww OTP verification failed: {data.get('message', data.get('error', 'unknown'))}")

        raise ValueError(
            "Groww requires phone + otp (for first-time login), "
            "or an already-obtained access_token. "
            "Call authenticate with phone first to receive OTP, then with phone + otp."
        )

    def _headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
            "Origin": "https://groww.in",
            "Referer": "https://groww.in/",
        }
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        if not self._token:
            return OrderResult(success=False, broker_order_id="", message="Not authenticated")

        client = await get_http_client()
        payload = {
            "qty": order.quantity,
            "price": order.price or 0,
            "tradingSymbol": order.symbol,
            "exchange": order.exchange.value,
            "transactionType": "BUY" if order.side == OrderSide.BUY else "SELL",
            "orderType": self._map_order_type(order.order_type),
            "productType": self._map_product(order.product),
            "validity": "DAY",
        }

        resp = await client.post(
            f"{self._base_url}/groww/orders/v1/place",
            json=payload,
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        success = data.get("status") == "success" or data.get("success") is True
        return OrderResult(
            success=success,
            broker_order_id=str(data.get("data", {}).get("orderId", data.get("orderId", ""))),
            message=data.get("message", data.get("error", "")),
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        if not self._token:
            return OrderResult(success=False, broker_order_id=order_id, message="Not authenticated")

        client = await get_http_client()
        payload = {
            "orderId": order_id,
            "qty": changes.get("quantity", 0),
            "price": changes.get("price", 0),
            "orderType": self._map_order_type_str(changes.get("order_type", "MARKET")),
        }

        resp = await client.put(
            f"{self._base_url}/groww/orders/v1/modify",
            json=payload,
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        return OrderResult(
            success=data.get("status") == "success" or data.get("success") is True,
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def cancel_order(self, order_id: str) -> OrderResult:
        if not self._token:
            return OrderResult(success=False, broker_order_id=order_id, message="Not authenticated")

        client = await get_http_client()
        resp = await client.delete(
            f"{self._base_url}/groww/orders/v1/cancel/{order_id}",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        return OrderResult(
            success=data.get("status") == "success" or data.get("success") is True,
            broker_order_id=order_id,
            message=data.get("message", ""),
        )

    async def get_orderbook(self) -> list[NormalizedOrder]:
        if not self._token:
            return []
        client = await get_http_client()
        resp = await client.get(
            f"{self._base_url}/groww/orders/v1/orders",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        items = data.get("data", data.get("orders", data.get("result", [])))
        if isinstance(items, dict):
            items = items.get("orders", [])
        return [self._normalize_order(item) for item in (items or [])]

    async def get_positions(self) -> list[Position]:
        if not self._token:
            return []
        client = await get_http_client()
        resp = await client.get(
            f"{self._base_url}/groww/portfolio/v1/positions",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        items = data.get("data", data.get("positions", data.get("result", [])))
        if isinstance(items, dict):
            items = items.get("positions", [])
        return [self._normalize_position(item) for item in (items or [])]

    async def get_holdings(self) -> list[Holding]:
        if not self._token:
            return []
        client = await get_http_client()
        resp = await client.get(
            f"{self._base_url}/groww/holdings/v2/holdings",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        items = data.get("data", data.get("holdings", data.get("result", [])))
        if isinstance(items, dict):
            items = items.get("holdings", [])
        return [self._normalize_holding(item) for item in (items or [])]

    async def get_funds(self) -> Funds:
        if not self._token:
            return Funds(total_margin=0, used_margin=0, available_margin=0, broker=self.broker_name)
        client = await get_http_client()
        resp = await client.get(
            f"{self._base_url}/groww/user/v2/get_user_limits",
            headers=self._headers(),
            timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
        )
        data = resp.json()
        d = data.get("data", data.get("result", data))
        if isinstance(d, list) and d:
            d = d[0]
        return Funds(
            total_margin=float(_dict_val(d, "totalMargin", "total_limit", "totalLimit", default=0)),
            used_margin=float(_dict_val(d, "usedMargin", "used_limit", "usedLimit", default=0)),
            available_margin=float(_dict_val(d, "availableMargin", "available_limit", "availableLimit", default=0)),
            broker=self.broker_name,
        )

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        if not self._token or not symbols:
            return []
        client = await get_http_client()
        results = []
        for sym in symbols:
            try:
                resp = await client.post(
                    f"{self._base_url}/groww/marketdata/v1/quote",
                    json={"symbols": [sym]},
                    headers=self._headers(),
                    timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
                )
                data = resp.json()
                items = data.get("data", data.get("quotes", [data.get("quote", data)]))
                if isinstance(items, dict):
                    items = [items]
                for item in items:
                    results.append(self._normalize_quote(item, sym))
            except Exception as e:
                logger.warning("Groww quote failed for %s: %s", sym, e)
        return results

    async def get_historical(
        self, symbol: str, interval: str, start: str | None = None, end: str | None = None, range: str | None = None
    ) -> list[Candle]:
        if not self._token:
            return []
        client = await get_http_client()
        interval_map = {
            "1m": "ONE_MINUTE", "5m": "FIVE_MINUTE", "10m": "TEN_MINUTE",
            "15m": "FIFTEEN_MINUTE", "30m": "THIRTY_MINUTE",
            "1h": "ONE_HOUR", "1d": "ONE_DAY", "1w": "ONE_WEEK", "1M": "ONE_MONTH",
        }
        mapped = interval_map.get(interval, interval)
        params = {"interval": mapped}
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        try:
            resp = await client.get(
                f"{self._base_url}/groww/marketdata/v1/historical/{symbol}",
                params=params,
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
                    ts_str = item[0]
                    if isinstance(ts_str, str):
                        ts_str = ts_str.replace("T", " ").split("+")[0].split(".")[0]
                        try:
                            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S") if " " in ts_str else datetime.strptime(ts_str, "%Y-%m-%d")
                        except ValueError:
                            ts = datetime.now(UTC)
                    else:
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
                elif isinstance(item, dict):
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
        except Exception as e:
            logger.warning("Groww historical data failed for %s: %s", symbol, e)
            return []

    async def stream(self, symbols: list[str], on_tick: Callable[[Tick], None]) -> None:
        if not self._token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        self._running = True
        logger.info("Groww stream: polling quotes every 1s")

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
                        oi=q.oi,
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
                logger.error("Groww stream polling error: %s", e)
                await asyncio.sleep(5)

    async def disconnect(self) -> None:
        self._running = False

    @staticmethod
    def _map_order_type(ot: OrderType) -> str:
        mapping = {
            OrderType.MARKET: "MARKET",
            OrderType.LIMIT: "LIMIT",
            OrderType.SL: "STOPLOSS_LIMIT",
            OrderType.SLM: "STOPLOSS_MARKET",
        }
        return mapping.get(ot, "MARKET")

    @staticmethod
    def _map_order_type_str(ot: str) -> str:
        mapping = {
            "MARKET": "MARKET",
            "LIMIT": "LIMIT",
            "SL": "STOPLOSS_LIMIT",
            "SLM": "STOPLOSS_MARKET",
        }
        return mapping.get(ot, "MARKET")

    @staticmethod
    def _map_product(p: ProductType) -> str:
        mapping = {
            ProductType.INTRADAY: "INTRADAY",
            ProductType.DELIVERY: "DELIVERY",
            ProductType.MIS: "INTRADAY",
            ProductType.NRML: "DELIVERY",
        }
        return mapping.get(p, "INTRADAY")

    @staticmethod
    def _map_side(side: OrderSide) -> str:
        return "BUY" if side == OrderSide.BUY else "SELL"

    @staticmethod
    def _map_status(status: str) -> OrderStatus:
        mapping = {
            "PENDING": OrderStatus.PENDING,
            "OPEN": OrderStatus.OPEN,
            "COMPLETE": OrderStatus.FILLED,
            "FILLED": OrderStatus.FILLED,
            "EXECUTED": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "CANCELED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "TRIGGER_PENDING": OrderStatus.PENDING,
        }
        return mapping.get(status.upper(), OrderStatus.PENDING)

    @staticmethod
    def _parse_instrument(symbol: str) -> dict:
        m = re.match(r'^([A-Z]+)(\d{2})([A-Z]{3})(\d+)(CE|PE)$', symbol.upper())
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
        m = re.match(r'^([A-Z]+)(\d{2})([A-Z]{3})$', symbol.upper())
        if m:
            return {"instrument_type": InstrumentType.FUT, "strike_price": None, "expiry_date": None, "option_type": None}
        return {"instrument_type": InstrumentType.EQ, "strike_price": None, "expiry_date": None, "option_type": None}

    def _normalize_order(self, item: dict) -> NormalizedOrder:
        inst = self._parse_instrument(item.get("tradingSymbol", item.get("symbol", "")))
        return NormalizedOrder(
            id=str(_dict_val(item, "orderId", "order_id", default="")),
            broker_order_id=str(_dict_val(item, "orderId", "order_id", default="")),
            symbol=item.get("tradingSymbol", item.get("symbol", "")),
            exchange=Exchange(item.get("exchange", "NSE")),
            side=OrderSide.BUY if item.get("transactionType", "").upper() == "BUY" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            product=ProductType.INTRADAY,
            quantity=int(_dict_val(item, "qty", "quantity", default=0)),
            price=float(item.get("price", 0)),
            trigger_price=float(item.get("triggerPrice", 0)) if item.get("triggerPrice") else None,
            status=self._map_status(_dict_val(item, "orderStatus", "status", default="")),
            filled_quantity=int(_dict_val(item, "filledQty", "filledQuantity", default=0)),
            average_price=float(_dict_val(item, "averagePrice", "avgPrice", default=0)),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )

    def _normalize_position(self, item: dict) -> Position:
        inst = self._parse_instrument(item.get("tradingSymbol", item.get("symbol", "")))
        return Position(
            symbol=item.get("tradingSymbol", item.get("symbol", "")),
            exchange=Exchange(item.get("exchange", "NSE")),
            quantity=int(_dict_val(item, "netQty", "quantity", default=0)),
            buy_quantity=int(_dict_val(item, "buyQty", "buyQuantity", default=0)),
            sell_quantity=int(_dict_val(item, "sellQty", "sellQuantity", default=0)),
            average_buy_price=float(_dict_val(item, "buyAvgPrice", "avgBuyPrice", default=0)),
            average_sell_price=float(_dict_val(item, "sellAvgPrice", "avgSellPrice", default=0)),
            unrealised_pnl=float(_dict_val(item, "unrealisedPL", "unrealizedPL", "mtm", default=0)),
            realised_pnl=float(_dict_val(item, "realisedPL", "realizedPL", default=0)),
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
            quantity=int(_dict_val(item, "qty", "quantity", default=0)),
            t1_quantity=int(_dict_val(item, "t1Qty", "t1Quantity", default=0)),
            average_price=float(_dict_val(item, "averagePrice", "avgPrice", default=0)),
            current_price=float(_dict_val(item, "ltp", "lastPrice", default=0)),
            pnl=float(_dict_val(item, "pnl", "profitLoss", default=0)),
            broker=self.broker_name,
        )

    def _normalize_quote(self, item: dict, symbol: str = "") -> Quote:
        sym = symbol or item.get("tradingSymbol", item.get("symbol", ""))
        inst = self._parse_instrument(sym)
        ohlc = item.get("ohlc", {})
        return Quote(
            symbol=sym,
            exchange=Exchange(item.get("exchange", "NSE")),
            last_price=float(item.get("ltp", item.get("lastPrice", 0))),
            open=float(ohlc.get("open", item.get("open", 0))),
            high=float(ohlc.get("high", item.get("high", 0))),
            low=float(ohlc.get("low", item.get("low", 0))),
            close=float(ohlc.get("close", item.get("close", 0))),
            volume=int(item.get("volume", item.get("vol", 0))),
            bid=float(item.get("bid", item.get("bidPrice", 0))),
            ask=float(item.get("ask", item.get("askPrice", 0))),
            bid_qty=int(item.get("bidQty", item.get("bidQuantity", 0))),
            ask_qty=int(item.get("askQty", item.get("askQuantity", 0))),
            oi=int(item.get("oi", item.get("openInterest", 0))),
            timestamp=datetime.now(UTC),
            broker=self.broker_name,
            instrument_type=inst["instrument_type"],
            strike_price=inst["strike_price"],
            expiry_date=inst["expiry_date"],
            option_type=inst["option_type"],
        )
