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
from engine.executor import ExecutionEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tradingview", tags=["tradingview"])

WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "")


def _verify_signature(payload: bytes, signature: str) -> bool:
    if not WEBHOOK_SECRET:
        return True
    expected = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


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

    if not symbol or not action or quantity <= 0:
        raise HTTPException(status_code=400, detail="symbol, action, and quantity are required")

    side = OrderSide.BUY if action in ("BUY", "LONG") else OrderSide.SELL

    if not user_id:
        creds = safe_single(
            get_supabase().table("broker_credentials")
            .select("user_id, broker")
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if not creds:
            raise HTTPException(status_code=400, detail="No active broker user found")
        user_id = creds["user_id"]

    creds = safe_single(
        get_supabase().table("broker_credentials")
        .select("broker")
        .eq("user_id", user_id)
        .eq("is_active", True)
    )
    if not creds:
        raise HTTPException(status_code=400, detail="No active broker configured")

    try:
        engine = ExecutionEngine(user_id, creds["broker"])
        await engine.start()

        order = NormalizedOrder(
            symbol=symbol,
            exchange=Exchange(exchange),
            side=side,
            order_type=OrderType(order_type),
            product=ProductType(product),
            quantity=quantity,
            price=price if price else 0.0,
            strategy_id=strategy_id or None,
        )

        result = await engine.execute_signal(order)
        await engine.stop()

        return {
            "success": result.success,
            "broker_order_id": result.broker_order_id,
            "message": result.message,
        }
    except Exception as e:
        logger.error("TradingView webhook execution error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
