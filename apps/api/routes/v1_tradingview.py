import hashlib
import hmac
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request

from core.db import get_supabase

from core.models import (
    Exchange, InstrumentType, NormalizedOrder, OptionType, OrderSide, OrderType, ProductType, UserProfile,
)
from core.safe_query import safe_single
from engine.gate import execute_order, get_mirror_recipients, scaled_qty

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tradingview", tags=["tradingview"])

WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "")

if not WEBHOOK_SECRET:
    logger.warning("TRADINGVIEW_WEBHOOK_SECRET not set — webhook signatures NOT verified. Set this in production.")


def _verify_signature(payload: bytes, signature: str) -> bool:
    if not WEBHOOK_SECRET:
        logger.warning("Webhook received without WEBHOOK_SECRET configured — allowing unverified request")
        return True
    expected = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _execute_for_user(
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
        scaled = scaled_qty(user_id, quantity, price)
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


@router.post("/webhook")
async def tradingview_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-TradingView-Signature", "")
    if not _verify_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        import json
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

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
        raise HTTPException(status_code=400, detail="symbol, action, and quantity are required")

    is_mirror = bool(strategy_id)

    if is_mirror and not user_id:
        recipients = await get_mirror_recipients(strategy_id)
        if not recipients:
            return {"results": [], "message": "No recipients found for this strategy"}

        results = []
        for r in recipients:
            uid = r["user_id"]
            res = await _execute_for_user(
                uid, symbol, action, quantity, price, exchange,
                order_type, product, strategy_id, reason, source="mirror",
            )
            results.append(res)
        return {"results": results, "count": len(results)}

    if not user_id:
        if not WEBHOOK_SECRET:
            creds = safe_single(
                get_supabase().table("broker_credentials")
                .select("user_id")
                .eq("is_active", True)
                .limit(1)
            )
            if not creds:
                raise HTTPException(status_code=400, detail="No active broker user found")
            user_id = creds["user_id"]
        else:
            raise HTTPException(status_code=400, detail="user_id is required for authenticated webhooks")

    result = await _execute_for_user(
        user_id, symbol, action, quantity, price, exchange,
        order_type, product, strategy_id, reason,
        source="mirror" if is_mirror else "manual",
    )
    return result


@router.get("/webhook-info")
async def webhook_info():
    return {
        "endpoint": "/api/v1/tradingview/webhook",
        "method": "POST",
        "content_type": "application/json",
        "signature_header": "X-TradingView-Signature",
        "fields": {
            "symbol": "Trading symbol (e.g. NIFTY, BANKNIFTY)",
            "action": "BUY/SELL or LONG/SHORT",
            "quantity": "Number of units/lots",
            "price": "Limit price (0 for market)",
            "exchange": "NSE/BSE/NFO",
            "order_type": "MARKET/LIMIT/SL",
            "product": "INTRADAY/DELIVERY",
            "strategy_id": "Optional strategy identifier",
            "user_id": "Optional user ID (auto-detected if omitted)",
            "reason": "Optional human-readable reason string",
        },
        "example_payload": {
            "symbol": "NIFTY",
            "action": "BUY",
            "quantity": 65,
            "price": 0,
            "exchange": "NSE",
            "order_type": "MARKET",
            "product": "INTRADAY",
        },
    }
