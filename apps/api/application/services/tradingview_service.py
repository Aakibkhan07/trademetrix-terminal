import hashlib
import hmac
import json
import logging
import os

from core.models import Exchange, NormalizedOrder, OrderSide, OrderType, ProductType
from engine.gate import execute_order, get_mirror_recipients, scaled_qty

logger = logging.getLogger(__name__)

WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "")

if not WEBHOOK_SECRET:
    logger.warning("TRADINGVIEW_WEBHOOK_SECRET not set — webhook signatures NOT verified. Set this in production.")


class TradingViewService:
    def verify_signature(self, payload_bytes: bytes, signature: str) -> bool:
        if not WEBHOOK_SECRET:
            logger.warning("Webhook received without WEBHOOK_SECRET configured — allowing unverified request")
            return True
        expected = hmac.new(WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def execute_for_user(
        self,
        user_id: str,
        symbol: str,
        action: str,
        quantity: int,
        price: float,
        exchange: str,
        order_type: str,
        product: str,
        strategy_id: str,
        reason: str,
        source: str,
    ) -> dict:
        try:
            side = OrderSide.BUY if action in ("BUY", "LONG") else OrderSide.SELL
            scaled = await scaled_qty(user_id, quantity, price)
            if scaled != quantity:
                logger.info("Quantity scaled from %d to %d for user=%s", quantity, scaled, user_id)

            order = NormalizedOrder(
                symbol=symbol,
                exchange=Exchange(exchange),
                side=side,
                order_type=OrderType(order_type),
                product=ProductType(product),
                quantity=scaled,
                price=price if price else 0.0,
                strategy_id=strategy_id or None,
                reason=reason,
            )
            result = await execute_order(user_id, order, source=source)
            return {
                "user_id": user_id,
                "success": result.success,
                "broker_order_id": result.broker_order_id,
                "message": result.message,
                "status": result.status,
            }
        except Exception as e:
            logger.error("Execution error for user=%s: %s", user_id, e)
            return {"user_id": user_id, "success": False, "message": str(e), "status": "error"}

    async def handle_webhook(self, body_bytes: bytes, signature: str) -> dict:
        if not self.verify_signature(body_bytes, signature):
            raise ValueError("Invalid signature")

        try:
            data = json.loads(body_bytes)
        except Exception:
            raise ValueError("Invalid JSON body")

        symbol = data.get("symbol", "").upper()
        action = data.get("action", "").upper()
        quantity = int(data.get("quantity", 0))
        price = float(data.get("price", 0))
        exchange = data.get("exchange", "NSE").upper()
        order_type = data.get("order_type", "MARKET").upper()
        product = data.get("product", "INTRADAY").upper()
        strategy_id = data.get("strategy_id", "")
        user_id = data.get("user_id", "")
        reason = data.get("reason", "")

        if not symbol or not action or quantity <= 0:
            raise ValueError("symbol, action, and quantity are required")

        is_mirror = bool(strategy_id)

        if is_mirror and not user_id:
            recipients = await get_mirror_recipients(strategy_id)
            if not recipients:
                return {"results": [], "message": "No recipients found for this strategy"}

            results = []
            for r in recipients:
                uid = r["user_id"]
                res = await self.execute_for_user(
                    uid, symbol, action, quantity, price, exchange,
                    order_type, product, strategy_id, reason, source="mirror",
                )
                results.append(res)
            return {"results": results, "count": len(results)}

        if not user_id:
            raise ValueError("user_id is required when webhook secret is not configured")

        result = await self.execute_for_user(
            user_id, symbol, action, quantity, price, exchange,
            order_type, product, strategy_id, reason,
            source="mirror" if is_mirror else "manual",
        )
        return result
