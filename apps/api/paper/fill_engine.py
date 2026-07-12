import logging
import random

from core.models import NormalizedOrder
from market.cache import market_cache
from paper.models import FillType, PaperConfig, PaperFill, PaperOrderStatus

logger = logging.getLogger(__name__)


class FillEngine:
    def __init__(self, config: PaperConfig):
        self._config = config

    async def simulate_fill(self, order: NormalizedOrder, user_id: str) -> PaperFill:
        fill_type = self._config.fill_type
        if fill_type == FillType.INSTANT:
            return await self._instant_fill(order)
        elif fill_type == FillType.NEXT_TICK:
            return await self._next_tick_fill(order)
        elif fill_type == FillType.PRICE_BASED:
            return await self._price_based_fill(order)
        elif fill_type == FillType.VOLUME_BASED:
            return await self._volume_based_fill(order)
        return await self._instant_fill(order)

    async def _instant_fill(self, order: NormalizedOrder) -> PaperFill:
        fill_price = self._get_fill_price(order)
        fill_price = self._apply_slippage(order, fill_price)
        qty = self._apply_partial_fill(order.quantity)
        return self._build_fill(order, qty, fill_price)

    async def _next_tick_fill(self, order: NormalizedOrder) -> PaperFill:
        quote = market_cache.get_quote(order.symbol)
        if quote:
            if hasattr(quote, "last_price") and quote.last_price > 0:
                fill_price = quote.last_price
            else:
                fill_price = self._get_fill_price(order)
        else:
            fill_price = self._get_fill_price(order)

        fill_price = self._apply_slippage(order, fill_price)
        qty = self._apply_partial_fill(order.quantity)
        return self._build_fill(order, qty, fill_price)

    async def _price_based_fill(self, order: NormalizedOrder) -> PaperFill:
        quote = market_cache.get_quote(order.symbol)
        if not quote:
            return await self._instant_fill(order)

        if order.order_type.value == "LIMIT":
            if order.side.value == "BUY" and quote.last_price <= order.price:
                fill_price = min(quote.last_price, order.price)
            elif order.side.value == "SELL" and quote.last_price >= order.price:
                fill_price = max(quote.last_price, order.price)
            else:
                return self._build_fill(order, 0, 0.0, PaperOrderStatus.PENDING)
        elif order.order_type.value in ("SL", "SLM") and order.trigger_price:
            if order.side.value == "BUY" and quote.last_price >= order.trigger_price:
                fill_price = max(quote.last_price, order.price or quote.last_price)
            elif order.side.value == "SELL" and quote.last_price <= order.trigger_price:
                fill_price = min(quote.last_price, order.price or quote.last_price)
            else:
                return self._build_fill(order, 0, 0.0, PaperOrderStatus.PENDING)
        else:
            fill_price = quote.last_price

        fill_price = self._apply_slippage(order, fill_price)
        qty = self._apply_partial_fill(order.quantity)
        return self._build_fill(order, qty, fill_price)

    async def _volume_based_fill(self, order: NormalizedOrder) -> PaperFill:
        return await self._instant_fill(order)

    def _get_fill_price(self, order: NormalizedOrder) -> float:
        quote = market_cache.get_quote(order.symbol)
        if quote and hasattr(quote, "last_price") and quote.last_price > 0:
            return quote.last_price
        return order.price or 0.0

    def _apply_slippage(self, order: NormalizedOrder, price: float) -> float:
        if self._config.slippage_pct <= 0 or price <= 0:
            return price
        slippage = price * self._config.slippage_pct / 100
        if order.side.value == "BUY":
            return price + slippage
        return price - slippage

    def _apply_partial_fill(self, quantity: int) -> int:
        if not self._config.enable_partial_fill:
            return quantity
        if random.random() > self._config.min_fill_probability:
            fill_pct = random.uniform(0.1, 0.9)
            return max(1, int(quantity * fill_pct))
        return quantity

    def _build_fill(self, order: NormalizedOrder, quantity: int, price: float, status: PaperOrderStatus = PaperOrderStatus.FILLED) -> PaperFill:
        if quantity <= 0:
            return PaperFill(
                order_id=order.client_order_id or order.id,
                symbol=order.symbol,
                side=order.side.value if hasattr(order.side, "value") else str(order.side),
                filled_quantity=0,
                filled_price=0.0,
                net_amount=0.0,
            )

        gross_amount = quantity * price
        commission = gross_amount * self._config.commission_pct / 100
        exchange_charges = gross_amount * self._config.exchange_charges_pct / 100
        stt = gross_amount * self._config.stt_pct / 100
        stamp_duty = gross_amount * self._config.stamp_duty_pct / 100
        total_charges = commission + exchange_charges + stt + stamp_duty
        net_amount = gross_amount + total_charges if order.side.value == "BUY" else gross_amount - total_charges

        return PaperFill(
            order_id=order.client_order_id or order.id,
            symbol=order.symbol,
            side=order.side.value if hasattr(order.side, "value") else str(order.side),
            filled_quantity=quantity,
            filled_price=round(price, 2),
            commission=round(commission, 2),
            exchange_charges=round(exchange_charges, 2),
            stt=round(stt, 2),
            stamp_duty=round(stamp_duty, 2),
            net_amount=round(net_amount, 2),
        )

    async def can_fill(self, order: NormalizedOrder) -> bool:
        if order.order_type.value in ("LIMIT", "SL", "SLM"):
            return True
        return True
