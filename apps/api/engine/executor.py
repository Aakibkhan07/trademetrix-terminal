import logging
import time
from datetime import UTC, datetime

from brokers import get_broker
from brokers.token_manager import TokenManager
from core.audit import record_audit
from core.db import get_supabase
from core.models import (
    AuditLogEntry,
    NormalizedOrder,
    OrderResult,
    OrderStatus,
)
from market.symbol_master import symbol_master
from risk.riskguard import RiskGuard

logger = logging.getLogger(__name__)


class ExecutionEngine:
    def __init__(self, user_id: str, broker: str):
        self.user_id = user_id
        self.broker = broker
        self._riskguard = RiskGuard(user_id)
        self._token_manager = TokenManager(user_id, broker)
        self._adapter = None
        self._running = False

    async def start(self):
        self._running = True
        session = await self._token_manager.get_session()
        adapter_cls = get_broker(self.broker)
        self._adapter = adapter_cls()
        await self._adapter.authenticate(session)
        logger.info(f"Engine started for user={self.user_id} broker={self.broker}")

    async def stop(self):
        self._running = False
        if self._adapter:
            await self._adapter.disconnect()
        logger.info(f"Engine stopped for user={self.user_id}")

    async def execute_signal(self, signal: NormalizedOrder) -> OrderResult:
        if not self._adapter:
            return OrderResult(success=False, message="Engine not started")

        signal.signal_at = datetime.now(UTC)
        signal.user_id = self.user_id
        signal.broker = self.broker

        risk_check = await self._riskguard.check_order(signal)
        signal.risk_checked_at = datetime.now(UTC)

        if not risk_check["allowed"]:
            signal.status = OrderStatus.REJECTED
            signal.message = risk_check["reason"]
            self._log_order(signal)
            return OrderResult(success=False, message=risk_check["reason"])

        return await self._live_execute(signal)

    async def _live_execute(self, signal: NormalizedOrder) -> OrderResult:
        signal.sent_at = datetime.now(UTC)
        send_start = time.monotonic()

        broker_symbol = await symbol_master.resolve_symbol(signal.symbol, self.broker)
        signal.symbol = broker_symbol or signal.symbol

        result = await self._adapter.place_order(signal)

        send_end = time.monotonic()
        signal.latency_ms = round((send_end - send_start) * 1000, 2)

        if result.success and result.broker_order_id:
            signal.broker_order_id = result.broker_order_id
            signal.status = OrderStatus.OPEN
            signal.filled_at = datetime.now(UTC)
            signal.message = "Order placed successfully"

        self._log_order(signal)
        self._log_audit("place_order", signal)
        return result

    async def cancel_order(self, order_id: str) -> OrderResult:
        if not self._adapter:
            return OrderResult(success=False, message="Engine not started")

        result = await self._adapter.cancel_order(order_id)
        self._log_audit("cancel_order", None, extra={"order_id": order_id})
        return result

    async def get_positions(self):
        if not self._adapter:
            return []
        return await self._adapter.get_positions()

    async def get_orderbook(self):
        if not self._adapter:
            return []
        return await self._adapter.get_orderbook()

    async def get_funds(self):
        if not self._adapter:
            from core.models import Funds
            return Funds(broker=self.broker)
        return await self._adapter.get_funds()

    def _log_order(self, order: NormalizedOrder) -> None:
        try:
            supabase = get_supabase()
            data = order.model_dump(mode="json")
            for field in ("id", "strategy_id", "run_id", "signal_id", "validity", "disclosed_quantity"):
                if field in data and not data[field]:
                    del data[field]
            supabase.table("orders").insert(data).execute()
        except Exception as e:
            logger.error(f"Failed to log order: {e}")

    def _log_audit(self, action: str, order: NormalizedOrder | None = None, extra: dict | None = None) -> None:
        details = extra or {}
        if order:
            details.update({"symbol": order.symbol, "side": order.side.value, "quantity": order.quantity})
        record_audit(AuditLogEntry(
            user_id=self.user_id,
            action=action,
            resource="order",
            details=details,
        ))
