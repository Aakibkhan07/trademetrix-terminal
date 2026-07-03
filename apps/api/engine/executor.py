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
from engine.gate import execute_order as gate_execute_order
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
        return await gate_execute_order(self.user_id, signal, source="manual")

    async def cancel_order(self, order_id: str) -> OrderResult:
        from execution import execution_manager
        from execution.models import ExecutionRequest

        req = ExecutionRequest(
            user_id=self.user_id,
            broker=self.broker,
            symbol="",
            side="",
            quantity=0,
            source="cancel",
        )
        result = await execution_manager.cancel_order(req, order_id)
        return OrderResult(
            success=result.success,
            broker_order_id=order_id,
            message=result.message,
            status="cancelled" if result.success else "failed",
        )

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
