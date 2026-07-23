import asyncio
import logging
import time

import httpx

from brokers import get_broker
from brokers.token_manager import TokenManager
from core.models import NormalizedOrder, OrderResult
from core.prometheus import record_broker_metrics
from core.resilience import _get_breaker
from execution.models import BrokerCapabilities

logger = logging.getLogger(__name__)


BROKER_CAPABILITIES: dict[str, BrokerCapabilities] = {
    "fyers": BrokerCapabilities(
        broker="fyers", supports_orders=True, supports_modify=True, supports_cancel=True,
        supports_bracket=True, supports_cover=False, supports_gtt=False,
        supports_websocket=True, supports_option_chain=True, supports_positions=True, supports_holdings=True,
    ),
    "dhan": BrokerCapabilities(
        broker="dhan", supports_orders=True, supports_modify=True, supports_cancel=True,
        supports_bracket=False, supports_cover=False, supports_gtt=True,
        supports_websocket=True, supports_option_chain=False, supports_positions=True, supports_holdings=True,
    ),
    "zerodha": BrokerCapabilities(
        broker="zerodha", supports_orders=True, supports_modify=True, supports_cancel=True,
        supports_bracket=True, supports_cover=True, supports_gtt=True,
        supports_websocket=False, supports_option_chain=False, supports_positions=True, supports_holdings=True,
    ),
    "angelone": BrokerCapabilities(
        broker="angelone", supports_orders=True, supports_modify=True, supports_cancel=True,
        supports_bracket=True, supports_cover=True, supports_gtt=True,
        supports_websocket=True, supports_option_chain=False, supports_positions=True, supports_holdings=True,
    ),
    "upstox": BrokerCapabilities(
        broker="upstox", supports_orders=True, supports_modify=True, supports_cancel=True,
        supports_bracket=True, supports_cover=True, supports_gtt=True,
        supports_websocket=True, supports_option_chain=False, supports_positions=True, supports_holdings=True,
    ),
    "fivepaisa": BrokerCapabilities(
        broker="fivepaisa", supports_orders=True, supports_modify=True, supports_cancel=True,
        supports_bracket=False, supports_cover=False, supports_gtt=False,
        supports_websocket=False, supports_option_chain=False, supports_positions=True, supports_holdings=True,
    ),
    "aliceblue": BrokerCapabilities(
        broker="aliceblue", supports_orders=True, supports_modify=True, supports_cancel=True,
        supports_bracket=False, supports_cover=False, supports_gtt=False,
        supports_websocket=True, supports_option_chain=False, supports_positions=True, supports_holdings=True,
    ),
    "finvasia": BrokerCapabilities(
        broker="finvasia", supports_orders=True, supports_modify=True, supports_cancel=True,
        supports_bracket=False, supports_cover=False, supports_gtt=False,
        supports_websocket=True, supports_option_chain=False, supports_positions=True, supports_holdings=True,
    ),
    "flattrade": BrokerCapabilities(
        broker="flattrade", supports_orders=True, supports_modify=True, supports_cancel=True,
        supports_bracket=False, supports_cover=False, supports_gtt=False,
        supports_websocket=True, supports_option_chain=False, supports_positions=True, supports_holdings=True,
    ),
    "kotakneo": BrokerCapabilities(
        broker="kotakneo", supports_orders=True, supports_modify=True, supports_cancel=True,
        supports_bracket=True, supports_cover=False, supports_gtt=True,
        supports_websocket=True, supports_option_chain=False, supports_positions=True, supports_holdings=True,
    ),
}


_TOKEN_EXPIRY_KEYWORDS = ("token", "expired", "unauthorized", "invalid session", "auth failed", "auth_error", "invalid_token")


def _is_token_expiry(error: Exception) -> bool:
    msg = str(error).lower()
    return any(kw in msg for kw in _TOKEN_EXPIRY_KEYWORDS)


class BrokerExecutionAdapter:
    def __init__(self, user_id: str, broker: str):
        self.user_id = user_id
        self.broker = broker
        self._adapter = None
        self._authenticated = False
        self._token_manager = TokenManager(user_id, broker)

    async def connect(self) -> bool:
        try:
            session = await self._token_manager.get_session()
            adapter_cls = get_broker(self.broker)
            self._adapter = adapter_cls()
            await self._adapter.authenticate(session)
            self._authenticated = True
            return True
        except Exception as e:
            logger.error("Broker %s connect failed for user %s: %s", self.broker, self.user_id, e)
            self._authenticated = False
            return False

    async def disconnect(self):
        self._authenticated = False
        if self._adapter:
            try:
                await self._adapter.disconnect()
            except Exception as e:
                logger.warning("Broker %s disconnect error: %s", self.broker, e)

    async def health(self) -> dict:
        return {
            "broker": self.broker,
            "authenticated": self._authenticated,
            "connected": self._adapter is not None,
        }

    def capabilities(self) -> BrokerCapabilities:
        return BROKER_CAPABILITIES.get(self.broker, BrokerCapabilities(broker=self.broker))

    async def _handle_token_expiry_and_retry(self, coro_fn):
        try:
            return await coro_fn()
        except Exception as e:
            if _is_token_expiry(e):
                logger.info("Token may be expired for %s — attempting refresh and retry", self._token_manager._lock_key)
                self._token_manager.invalidate_session()
                self._authenticated = False
                connected = await self.connect()
                if connected:
                    return await coro_fn()
            raise

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        if not self._adapter or not self._authenticated:
            return OrderResult(success=False, message="Broker not connected")
        breaker = _get_breaker(f"broker_{self.broker}")
        start = time.monotonic()
        result = None
        try:
            result = await self._handle_token_expiry_and_retry(
                lambda: breaker.call(self._adapter.place_order, order)
            )
            return result
        except (asyncio.TimeoutError, httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadTimeout) as e:
            logger.warning("Transient error in place_order for %s: %s", self.broker, e)
            raise
        except Exception as e:
            logger.error("place_order failed for %s: %s", self.broker, e)
            result = OrderResult(success=False, message=str(e))
            return result
        finally:
            elapsed = (time.monotonic() - start) * 1000
            if elapsed > 1000:
                logger.warning("place_order slow (%dms) for %s", elapsed, self.broker)
            record_broker_metrics(self.broker, "place_order", elapsed / 1000, isinstance(result, OrderResult) and result.success)

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        if not self._adapter or not self._authenticated:
            return OrderResult(success=False, message="Broker not connected")
        breaker = _get_breaker(f"broker_{self.broker}")
        start = time.monotonic()
        result = None
        try:
            result = await self._handle_token_expiry_and_retry(
                lambda: breaker.call(self._adapter.modify_order, order_id, changes)
            )
            return result
        except (asyncio.TimeoutError, httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadTimeout) as e:
            logger.warning("Transient error in modify_order for %s: %s", self.broker, e)
            raise
        except Exception as e:
            logger.error("modify_order failed for %s: %s", self.broker, e)
            result = OrderResult(success=False, message=str(e))
            return result
        finally:
            elapsed = (time.monotonic() - start) * 1000
            if elapsed > 1000:
                logger.warning("modify_order slow (%dms) for %s", elapsed, self.broker)
            record_broker_metrics(self.broker, "modify_order", elapsed / 1000, isinstance(result, OrderResult) and result.success)

    async def cancel_order(self, order_id: str) -> OrderResult:
        if not self._adapter or not self._authenticated:
            return OrderResult(success=False, message="Broker not connected")
        breaker = _get_breaker(f"broker_{self.broker}")
        start = time.monotonic()
        result = None
        try:
            result = await self._handle_token_expiry_and_retry(
                lambda: breaker.call(self._adapter.cancel_order, order_id)
            )
            return result
        except (asyncio.TimeoutError, httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadTimeout) as e:
            logger.warning("Transient error in cancel_order for %s: %s", self.broker, e)
            raise
        except Exception as e:
            logger.error("cancel_order failed for %s: %s", self.broker, e)
            result = OrderResult(success=False, message=str(e))
            return result
        finally:
            elapsed = (time.monotonic() - start) * 1000
            if elapsed > 1000:
                logger.warning("cancel_order slow (%dms) for %s", elapsed, self.broker)
            record_broker_metrics(self.broker, "cancel_order", elapsed / 1000, isinstance(result, OrderResult) and result.success)

    async def get_order(self, order_id: str) -> NormalizedOrder | None:
        orders = await self.get_orders()
        for o in orders:
            if o.id == order_id or o.broker_order_id == order_id:
                return o
        return None

    async def get_orders(self) -> list[NormalizedOrder]:
        if not self._adapter or not self._authenticated:
            return []
        try:
            return await self._adapter.get_orderbook()
        except Exception as e:
            logger.error("get_orders failed for %s: %s", self.broker, e)
            return []

    async def get_positions(self) -> list:
        if not self._adapter or not self._authenticated:
            return []
        try:
            return await self._adapter.get_positions()
        except Exception as e:
            logger.error("get_positions failed for %s: %s", self.broker, e)
            return []

    async def get_holdings(self) -> list:
        if not self._adapter or not self._authenticated:
            return []
        try:
            return await self._adapter.get_holdings()
        except Exception as e:
            logger.error("get_holdings failed for %s: %s", self.broker, e)
            return []

    async def get_funds(self):
        if not self._adapter or not self._authenticated:
            from core.models import Funds
            return Funds(broker=self.broker)
        try:
            return await self._adapter.get_funds()
        except Exception as e:
            logger.error("get_funds failed for %s: %s", self.broker, e)
            from core.models import Funds
            return Funds(broker=self.broker)

    async def validate_order(self, order: NormalizedOrder) -> dict:
        caps = self.capabilities()
        errors = []

        if not caps.supports_orders:
            errors.append({"field": "broker", "message": f"Broker {self.broker} does not support orders"})

        if not order.symbol:
            errors.append({"field": "symbol", "message": "Symbol is required"})
        if order.quantity <= 0:
            errors.append({"field": "quantity", "message": "Quantity must be positive"})
        if order.order_type in ("LIMIT", "SL", "SLM") and order.price <= 0:
            errors.append({"field": "price", "message": "Price is required for LIMIT/SL orders"})
        if order.product not in ("INTRADAY", "DELIVERY", "MIS", "NRML"):
            errors.append({"field": "product", "message": f"Invalid product: {order.product}"})
        if order.side not in ("BUY", "SELL"):
            errors.append({"field": "side", "message": "Side must be BUY or SELL"})

        return {"valid": len(errors) == 0, "errors": errors}
