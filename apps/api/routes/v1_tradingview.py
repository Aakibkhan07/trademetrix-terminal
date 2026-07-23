import logging

from fastapi import APIRouter, HTTPException, Request

from application.services.tradingview_service import TradingViewService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tradingview", tags=["tradingview"])
service = TradingViewService()


@router.post("/webhook")
async def tradingview_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-TradingView-Signature", "")

    try:
        result = await service.handle_webhook(body, signature)
    except ValueError as e:
        if "signature" in str(e).lower():
            raise HTTPException(status_code=401, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))

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
