"""
Trading adapters. The engine calls place_order(intent, access_token).

  - PaperTradingAdapter: fully working simulated fill. The engine runs
    end-to-end in PAPER mode with zero broker setup.
  - FyersLiveAdapter: reference shape for a real Fyers v3 order. RECONCILE with
    your existing working Fyers v3 order code (symbol formatting, product codes,
    bracket/TP-SL handling) before flipping anyone to LIVE.

Symbol formatting is each adapter's job — that's where broker-specific syntax
(e.g. NSE:RELIANCE-EQ, NSE:NIFTY25...CE) lives. Fix it once per broker here.
"""

from __future__ import annotations

import uuid

import httpx

from .models import OrderIntent, ExecutionResult, ResultStatus, Mode, OrderType, Product, Side

FYERS_API = "https://api-t1.fyers.in/api/v3"


# ---------------------------------------------------------------------------
# PAPER — simulated fill
# ---------------------------------------------------------------------------
class PaperTradingAdapter:
    def __init__(self, broker: str):
        self.broker = broker

    async def place_order(self, intent: OrderIntent, access_token: str) -> ExecutionResult:
        return ExecutionResult(
            user_id=intent.user_id,
            broker=self.broker,
            status=ResultStatus.PLACED,
            broker_order_id=f"PAPER-{uuid.uuid4().hex[:12]}",
            qty=intent.qty,
            reason="paper_fill",
        )


# ---------------------------------------------------------------------------
# LIVE — Fyers v3 (reference; reconcile with your adapter)
# ---------------------------------------------------------------------------
_FYERS_SIDE = {Side.BUY: 1, Side.SELL: -1}
_FYERS_TYPE = {OrderType.LMT: 1, OrderType.MKT: 2, OrderType.SL: 4, OrderType.SL_M: 3}
_FYERS_PRODUCT = {Product.INTRADAY: "INTRADAY", Product.MARGIN: "MARGIN", Product.CNC: "CNC"}


class FyersLiveAdapter:
    broker = "fyers"

    def __init__(self, app_id: str):
        self._app_id = app_id  # header is "{app_id}:{access_token}"

    async def place_order(self, intent: OrderIntent, access_token: str) -> ExecutionResult:
        payload = {
            "symbol": intent.broker_symbol,          # already Fyers-formatted
            "qty": intent.qty,
            "type": _FYERS_TYPE.get(intent.order_type, 2),
            "side": _FYERS_SIDE[intent.side],
            "productType": _FYERS_PRODUCT.get(intent.product, "INTRADAY"),
            "limitPrice": intent.limit_price or 0,
            "stopPrice": intent.trigger_price or 0,
            "validity": "DAY",
            "offlineOrder": False,
            # bracket-style protection if provided
            "takeProfit": intent.target or 0,
            "stopLoss": intent.stoploss or 0,
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{FYERS_API}/orders/sync",
                    headers={"Authorization": f"{self._app_id}:{access_token}"},
                    json=payload,
                )
                data = resp.json()
            if data.get("s") == "ok" and data.get("id"):
                return ExecutionResult(
                    user_id=intent.user_id, broker=self.broker,
                    status=ResultStatus.PLACED, broker_order_id=str(data["id"]),
                    qty=intent.qty,
                )
            return ExecutionResult(
                user_id=intent.user_id, broker=self.broker,
                status=ResultStatus.REJECTED, qty=intent.qty,
                reason=str(data.get("message") or data),
            )
        except Exception as e:
            return ExecutionResult(
                user_id=intent.user_id, broker=self.broker,
                status=ResultStatus.ERROR, qty=intent.qty, reason=str(e),
            )


# ---------------------------------------------------------------------------
# Factory — pick adapter by (broker, mode)
# ---------------------------------------------------------------------------
def get_trading_adapter(broker: str, mode: Mode):
    if mode == Mode.PAPER:
        return PaperTradingAdapter(broker)

    key = broker.lower()
    if key == "fyers":
        from ..config import get_settings
        s = get_settings()
        app_id = s.fyers.app_id if s.fyers else ""
        return FyersLiveAdapter(app_id)

    # dhan / zerodha / upstox / angel -> add live adapters here.
    # Until then, LIVE for an unbuilt broker falls back to PAPER for safety.
    return PaperTradingAdapter(broker)
