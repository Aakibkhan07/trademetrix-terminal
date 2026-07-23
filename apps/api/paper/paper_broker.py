import asyncio
import logging
import time
from datetime import UTC, datetime

from core.db import get_supabase
from core.models import (
    Exchange, Funds, NormalizedOrder,
    OrderResult, OrderStatus, OrderType, Position, ProductType,
)
from execution.event_bus import execution_event_bus, ExecutionEvent, fire_and_forget
from execution.models import BrokerCapabilities
from paper.fill_engine import FillEngine
from paper.models import (
    PaperAccount,
    PaperConfig,
    PaperFill,
    PaperOrderStatus,
    PaperPosition,
)
from paper.observability import paper_metrics

logger = logging.getLogger(__name__)

PAPER_BROKER = "paper"


class PaperBroker:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.broker = PAPER_BROKER
        self._config = PaperConfig()
        self._fill_engine = FillEngine(self._config)
        self._orders: dict[str, dict] = {}
        self._positions: dict[str, PaperPosition] = {}
        self._account = PaperAccount(user_id=user_id)
        self._authenticated = False
        self._connected = False
        self._order_counter = 0

    async def connect(self) -> bool:
        self._authenticated = True
        self._connected = True
        self._account.initial_capital = self._config.initial_capital
        self._account.total_margin = self._config.initial_capital
        self._account.available_margin = self._config.initial_capital
        self._account.current_value = self._config.initial_capital
        logger.info("PaperBroker connected for user %s (capital: %.2f)", self.user_id, self._config.initial_capital)
        return True

    async def disconnect(self):
        self._authenticated = False
        self._connected = False
        logger.info("PaperBroker disconnected for user %s", self.user_id)

    async def health(self) -> dict:
        return {
            "broker": PAPER_BROKER,
            "authenticated": self._authenticated,
            "connected": self._connected,
            "paper": True,
            "capital": self._account.initial_capital,
            "available_margin": self._account.available_margin,
        }

    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            broker=PAPER_BROKER,
            supports_orders=True,
            supports_modify=True,
            supports_cancel=True,
            supports_bracket=False,
            supports_cover=False,
            supports_gtt=False,
            supports_websocket=False,
            supports_option_chain=False,
            supports_positions=True,
            supports_holdings=True,
        )

    async def place_order(self, order: NormalizedOrder) -> OrderResult:
        start = time.monotonic()
        self._order_counter += 1
        order_id = f"paper_{self._order_counter}_{int(time.time())}"
        order.broker_order_id = order_id
        order.broker = PAPER_BROKER

        await asyncio.sleep(self._config.broker_delay_ms / 1000)

        if not await self._check_margin(order):
            paper_metrics.record_rejected()
            return OrderResult(
                success=False, broker_order_id=order_id, order=order,
                message="Insufficient margin", status="rejected",
            )

        fill = await self._fill_engine.simulate_fill(order, self.user_id)

        if fill.filled_quantity <= 0:
            self._orders[order_id] = {
                "order": order, "status": PaperOrderStatus.PENDING, "fills": [],
                "created_at": datetime.now(UTC),
            }
            paper_metrics.record_order()
            self._publish_event("PaperOrderPending", order, order_id, fill)
            return OrderResult(
                success=True, broker_order_id=order_id, order=order,
                message="Order pending (limit/stop not triggered)", status="pending",
            )

        self._update_position(order, fill)
        self._update_account(order, fill)
        self._orders[order_id] = {
            "order": order, "status": PaperOrderStatus.FILLED, "fills": [fill],
            "created_at": datetime.now(UTC),
        }

        order.status = OrderStatus.FILLED
        order.filled_quantity = fill.filled_quantity
        order.average_price = fill.filled_price
        order.filled_at = datetime.now(UTC)

        self._persist_order(order, fill)
        paper_metrics.record_fill()

        elapsed_ms = (time.monotonic() - start) * 1000
        self._publish_event("PaperOrderFilled", order, order_id, fill)

        return OrderResult(
            success=True, broker_order_id=order_id, order=order,
            message=f"Paper order filled {fill.filled_quantity} @ {fill.filled_price:.2f}",
            status="filled", filled_qty=fill.filled_quantity, avg_price=fill.filled_price,
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        existing = self._orders.get(order_id)
        if not existing:
            return OrderResult(success=False, message="Order not found")

        order = existing["order"]
        if "quantity" in changes:
            order.quantity = changes["quantity"]
        if "price" in changes:
            order.price = changes["price"]
        if "trigger_price" in changes:
            order.trigger_price = changes["trigger_price"]

        return OrderResult(success=True, broker_order_id=order_id, order=order, message="Order modified")

    async def cancel_order(self, order_id: str) -> OrderResult:
        existing = self._orders.get(order_id)
        if not existing:
            return OrderResult(success=False, message="Order not found")

        existing["status"] = PaperOrderStatus.CANCELLED
        paper_metrics.record_cancelled()
        self._publish_event("PaperOrderRejected", existing["order"], order_id)
        return OrderResult(success=True, broker_order_id=order_id, message="Order cancelled")

    async def get_order(self, order_id: str) -> NormalizedOrder | None:
        existing = self._orders.get(order_id)
        return existing["order"] if existing else None

    async def get_orders(self) -> list[NormalizedOrder]:
        return [o["order"] for o in self._orders.values()]

    async def get_positions(self) -> list:
        positions = []
        for symbol, pos in self._positions.items():
            positions.append(self._to_position_model(pos))
        return positions

    async def get_holdings(self) -> list:
        return []

    async def get_funds(self) -> Funds:
        return Funds(
            total_margin=self._account.total_margin,
            used_margin=self._account.used_margin,
            available_margin=self._account.available_margin,
            payin=self._account.payin,
            payout=self._account.payout,
            broker=PAPER_BROKER,
        )

    async def validate_order(self, order: NormalizedOrder) -> dict:
        errors = []
        if not order.symbol:
            errors.append({"field": "symbol", "message": "Symbol is required"})
        if order.quantity <= 0:
            errors.append({"field": "quantity", "message": "Quantity must be positive"})
        if order.order_type in (OrderType.LIMIT, OrderType.SL, OrderType.SLM) and order.price <= 0:
            errors.append({"field": "price", "message": "Price required for LIMIT/SL orders"})
        return {"valid": len(errors) == 0, "errors": errors}

    def update_config(self, config: PaperConfig) -> None:
        self._config = config
        self._fill_engine = FillEngine(config)
        self._account.initial_capital = config.initial_capital
        self._account.total_margin = config.initial_capital
        self._account.available_margin = config.initial_capital
        self._account.current_value = config.initial_capital

    def get_config(self) -> PaperConfig:
        return self._config

    def get_metrics(self) -> dict:
        return paper_metrics.stats

    def _update_position(self, order: NormalizedOrder, fill: PaperFill) -> None:
        symbol = order.symbol
        pos = self._positions.get(symbol)
        if not pos:
            pos = PaperPosition(symbol=symbol, product=order.product.value if hasattr(order.product, "value") else "INTRADAY")
            self._positions[symbol] = pos

        side = order.side.value if hasattr(order.side, "value") else str(order.side)
        qty = fill.filled_quantity
        price = fill.filled_price

        if side == "BUY":
            new_buy_qty = pos.buy_quantity + qty
            pos.average_buy_price = ((pos.average_buy_price * pos.buy_quantity) + (price * qty)) / max(new_buy_qty, 1)
            pos.buy_quantity = new_buy_qty
            pos.quantity = pos.buy_quantity - pos.sell_quantity
        else:
            new_sell_qty = pos.sell_quantity + qty
            pos.average_sell_price = ((pos.average_sell_price * pos.sell_quantity) + (price * qty)) / max(new_sell_qty, 1)
            pos.sell_quantity = new_sell_qty
            pos.quantity = pos.buy_quantity - pos.sell_quantity

        if pos.quantity == 0:
            pos.realised_pnl += (pos.average_sell_price - pos.average_buy_price) * min(pos.buy_quantity, pos.sell_quantity)
            pos.buy_quantity = 0
            pos.sell_quantity = 0

        pos.last_price = price
        pos.unrealised_pnl = pos.quantity * (price - pos.average_buy_price) if pos.quantity > 0 else \
                             abs(pos.quantity) * (pos.average_sell_price - price) if pos.quantity < 0 else 0.0
        pos.m2m = pos.realised_pnl + pos.unrealised_pnl

        self._publish_event("PaperPositionUpdated", order, fill.order_id)

    def _update_account(self, order: NormalizedOrder, fill: PaperFill) -> None:
        gross = fill.filled_quantity * fill.filled_price
        self._account.used_margin += gross
        self._account.available_margin = self._account.total_margin - self._account.used_margin
        self._account.m2m_unrealised = sum(p.unrealised_pnl for p in self._positions.values())
        self._account.current_value = self._account.total_margin + self._account.m2m_unrealised

    async def _check_margin(self, order: NormalizedOrder) -> bool:
        required = order.quantity * (order.price or 0)
        if required > self._account.available_margin:
            logger.warning("Insufficient paper margin: need %.2f, have %.2f", required, self._account.available_margin)
            return False
        return True

    def _to_position_model(self, pos: PaperPosition) -> Position:
        return Position(
            symbol=pos.symbol,
            exchange=Exchange.NSE,
            quantity=pos.quantity,
            buy_quantity=pos.buy_quantity,
            sell_quantity=pos.sell_quantity,
            average_buy_price=pos.average_buy_price,
            average_sell_price=pos.average_sell_price,
            unrealised_pnl=pos.unrealised_pnl,
            realised_pnl=pos.realised_pnl,
            m2m=pos.m2m,
            product=ProductType.INTRADAY,
            multiplier=pos.multiplier,
            broker=PAPER_BROKER,
        )

    def _persist_order(self, order: NormalizedOrder, fill: PaperFill) -> None:
        try:
            supabase = get_supabase()
            data = order.model_dump(mode="json")
            for field in ("id", "run_id", "signal_id", "validity", "disclosed_quantity"):
                if field in data and not data[field]:
                    del data[field]
            supabase.table("orders").insert(data).execute()
        except Exception as e:
            logger.error("Failed to persist paper order: %s", e)

    def _publish_event(self, event_type: str, order: NormalizedOrder, order_id: str, fill: PaperFill | None = None):
        try:
            payload = {
                "order_id": order_id,
                "symbol": order.symbol,
                "side": order.side.value if hasattr(order.side, "value") else "",
                "quantity": order.quantity,
                "price": order.price,
                "broker": PAPER_BROKER,
                "paper": True,
            }
            if fill:
                payload["fill"] = fill.model_dump()
            event = ExecutionEvent(
                event_type=event_type,
                execution_request_id=order_id,
                user_id=self.user_id,
                broker=PAPER_BROKER,
                symbol=order.symbol,
                side=order.side.value if hasattr(order.side, "value") else "",
                payload=payload,
            )
            fire_and_forget(execution_event_bus.publish(event))
        except Exception as e:
            logger.error("Failed to publish paper event: %s", e)
