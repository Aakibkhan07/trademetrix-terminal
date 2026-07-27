import json
import logging

from fastapi import APIRouter, HTTPException, Request

from application.services.tradingview_service import TradingViewService
from execution.webhook_retry import enqueue_webhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tradingview", tags=["tradingview"])
service = TradingViewService()


@router.post("/webhook")
async def tradingview_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-TradingView-Signature", "")

    try:
        result = await service.handle_webhook(body, signature)
        return result
    except ValueError as e:
        if "signature" in str(e).lower():
            raise HTTPException(status_code=401, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.warning("Webhook execution failed, enqueuing for retry: %s", e)
        try:
            payload = json.loads(body)
            payload["_signature"] = signature
            await enqueue_webhook(payload)
        except Exception as enq_err:
            logger.exception("Failed to enqueue webhook for retry: %s", enq_err)
        raise HTTPException(status_code=502, detail=str(e))


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
            "user_id": "Required user ID",
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
