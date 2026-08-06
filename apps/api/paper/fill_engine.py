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
        if quote and self._quote_last_price(quote) > 0:
            fill_price = self._quote_last_price(quote)
        else:
            fill_price = self._get_fill_price(order)

        fill_price = self._apply_slippage(order, fill_price)
        qty = self._apply_partial_fill(order.quantity)
        return self._build_fill(order, qty, fill_price)

    async def _price_based_fill(self, order: NormalizedOrder) -> PaperFill:
        quote = market_cache.get_quote(order.symbol)
        last_price = self._quote_last_price(quote)
        if last_price <= 0:
            return await self._instant_fill(order)

        if order.order_type.value == "LIMIT":
            if order.side.value == "BUY" and last_price <= order.price:
                fill_price = min(last_price, order.price)
            elif order.side.value == "SELL" and last_price >= order.price:
                fill_price = max(last_price, order.price)
            else:
                return self._build_fill(order, 0, 0.0, PaperOrderStatus.PENDING)
        elif order.order_type.value in ("SL", "SLM") and order.trigger_price:
            if order.side.value == "BUY" and last_price >= order.trigger_price:
                fill_price = max(last_price, order.price or last_price)
            elif order.side.value == "SELL" and last_price <= order.trigger_price:
                fill_price = min(last_price, order.price or last_price)
            else:
                return self._build_fill(order, 0, 0.0, PaperOrderStatus.PENDING)
        else:
            fill_price = last_price

        fill_price = self._apply_slippage(order, fill_price)
        qty = self._apply_partial_fill(order.quantity)
        return self._build_fill(order, qty, fill_price)

    async def _volume_based_fill(self, order: NormalizedOrder) -> PaperFill:
        return await self._instant_fill(order)

    def _quote_last_price(self, quote) -> float:
        if quote is None:
            return 0.0
        if isinstance(quote, dict):
            return float(quote.get("last_price") or quote.get("ltp") or 0.0)
        return float(getattr(quote, "last_price", 0.0) or 0.0)

    def _get_fill_price(self, order: NormalizedOrder) -> float:
        quote = market_cache.get_quote(order.symbol)
        if self._quote_last_price(quote) > 0:
            return self._quote_last_price(quote)
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

        from backtest.costs import BacktestCostConfig, estimate_cost, segment_for

        gross_amount = quantity * price
        side = order.side.value if hasattr(order.side, "value") else str(order.side)
        cfg = BacktestCostConfig(
            commission_pct=self._config.commission_pct,
            commission_min=0.0,
            slippage_pct=self._config.slippage_pct,
            stt_pct_override=self._config.stt_pct,
            exchange_tc_pct_override=self._config.exchange_charges_pct,
            stamp_duty_pct_override=self._config.stamp_duty_pct,
            gst_enabled=False,
            sebi_fees_enabled=False,
        )
        est = estimate_cost(
            side=side,
            traded_value=gross_amount,
            segment=segment_for(str(getattr(order, "instrument_type", "") or "")),
            qty=quantity,
            price=price,
            slippage_value=0.0,
            config=cfg,
        )
        total_charges = est.total
        net_amount = gross_amount + total_charges if order.side.value == "BUY" else gross_amount - total_charges

        return PaperFill(
            order_id=order.client_order_id or order.id,
            symbol=order.symbol,
            side=order.side.value if hasattr(order.side, "value") else str(order.side),
            filled_quantity=quantity,
            filled_price=round(price, 2),
            commission=est.brokerage,
            exchange_charges=est.exchange_tc,
            stt=est.stt,
            stamp_duty=est.stamp_duty,
            net_amount=round(net_amount, 2),
        )

    async def can_fill(self, order: NormalizedOrder) -> bool:
        if order.order_type.value in ("LIMIT", "SL", "SLM"):
            return True
        return True
