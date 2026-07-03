import logging
import time
from typing import Any

from core.db import async_supabase, get_supabase
from core.safe_query import async_safe_single, safe_single
from execution.event_bus import execution_event_bus, ExecutionEvent
from execution.models import ExecutionRequest
from risk.models import RiskConfig, RiskDecision, RiskEvalResult, RiskRuleResult
from risk.rules import (
    BrokerOfflineRule,
    DailyLossLimitRule,
    DailyProfitTargetRule,
    DuplicateOrderRule,
    EmergencyStopRule,
    KillSwitchRule,
    MarketClosedRule,
    MaxCapitalRule,
    MaxDrawdownRule,
    MaxExposureRule,
    MaxOpenPositionsRule,
    MaxOrdersPerMinuteRule,
    MaxQuantityRule,
    MaxSymbolExposureRule,
    MaxTradesPerDayRule,
    RiskRule,
    TradingWindowRule,
)

logger = logging.getLogger(__name__)

RISK_RULES: list[RiskRule] = [
    KillSwitchRule(),
    EmergencyStopRule(),
    BrokerOfflineRule(),
    MarketClosedRule(),
    TradingWindowRule(),
    DailyLossLimitRule(),
    DailyProfitTargetRule(),
    MaxTradesPerDayRule(),
    MaxOpenPositionsRule(),
    MaxQuantityRule(),
    MaxExposureRule(),
    MaxSymbolExposureRule(),
    MaxCapitalRule(),
    MaxDrawdownRule(),
    MaxOrdersPerMinuteRule(),
    DuplicateOrderRule(),
]


class RiskManager:
    def __init__(self):
        self._initialized = False
        self._config_cache: dict[str, RiskConfig] = {}

    async def initialize(self):
        if self._initialized:
            return
        self._initialized = True
        from risk.kill_switch import kill_switch
        await kill_switch.recover()
        logger.info("RiskManager initialized with %d rules", len(RISK_RULES))

    async def evaluate(self, req: ExecutionRequest) -> RiskEvalResult:
        start = time.monotonic()
        config = await self._load_config(req.user_id)
        results: list[RiskRuleResult] = []
        final_decision = RiskDecision.APPROVED
        warnings: list[str] = []

        for rule in RISK_RULES:
            try:
                result = await rule.evaluate(req, config)
                results.append(result)
                if result.decision == RiskDecision.REJECTED:
                    final_decision = RiskDecision.REJECTED
                    break
                if result.decision == RiskDecision.WARNING:
                    warnings.append(result.reason)
                    if not config.allow_warning and final_decision == RiskDecision.APPROVED:
                        final_decision = RiskDecision.WARNING
            except Exception as e:
                logger.error("Risk rule %s failed: %s", rule.rule_type, e)
                results.append(RiskRuleResult(
                    rule=rule.rule_type, decision=RiskDecision.REJECTED,
                    reason=f"Rule evaluation error: {e}",
                ))
                final_decision = RiskDecision.REJECTED
                break

        total_latency = (time.monotonic() - start) * 1000
        await self._publish_decision(req, final_decision, results, total_latency)
        await self._update_config_from_result(req, final_decision)

        return RiskEvalResult(
            decision=final_decision,
            results=results,
            warnings=warnings,
            message=self._build_message(final_decision, results),
        )

    async def _load_config(self, user_id: str) -> RiskConfig:
        cached = self._config_cache.get(user_id)
        if cached:
            return cached
        try:
            supabase = get_supabase()
            row = await async_safe_single(
                supabase.table("risk_settings")
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
            )
        except Exception as e:
            logger.error("Failed to load risk config for %s — applying fail-closed defaults: %s", user_id, e)
            return RiskConfig(
                user_id=user_id,
                kill_switch_enabled=True,
                max_open_positions=0,
                max_trades_per_day=0,
                daily_loss_limit=0,
                allow_warning=False,
            )

        if not row:
            return RiskConfig(user_id=user_id)
        return RiskConfig(
            user_id=user_id,
            daily_loss_limit=float(row.get("max_daily_loss", 0)),
            max_open_positions=int(row.get("max_open_positions", 10)),
            max_exposure=float(row.get("max_exposure", 0)),
            max_capital=float(row.get("max_capital", 0)),
            max_drawdown_pct=float(row.get("max_drawdown_pct", 0)),
            daily_profit_target=float(row.get("daily_profit_target", 0)),
            max_trades_per_day=int(row.get("max_trades_per_day", 0)),
            max_quantity=int(row.get("max_position_size", 0)),
            max_symbol_exposure=float(row.get("max_symbol_exposure", 0)),
            max_account_exposure=float(row.get("max_account_exposure", 0)),
            trading_start=str(row.get("trading_start", "09:15")),
            trading_end=str(row.get("trading_end", "15:30")),
            allow_warning=bool(row.get("allow_warning", True)),
            kill_switch_enabled=bool(row.get("kill_switch_enabled", False)),
            is_live=bool(row.get("is_live", False)),
            emergency_stop=False,
        )

    async def _publish_decision(self, req: ExecutionRequest, decision: RiskDecision, results: list[RiskRuleResult], latency_ms: float):
        try:
            await execution_event_bus.publish(ExecutionEvent(
                event_type="RiskDecision",
                user_id=req.user_id,
                broker=req.broker,
                payload={
                    "execution_request_id": req.execution_request_id,
                    "decision": decision,
                    "results": [r.model_dump() for r in results],
                    "latency_ms": round(latency_ms, 2),
                    "source": "risk_manager",
                },
            ))
        except Exception as e:
            logger.error("Failed to publish risk decision event: %s", e)

    async def _update_config_from_result(self, req: ExecutionRequest, decision: RiskDecision):
        if decision == RiskDecision.REJECTED:
            try:
                await execution_event_bus.publish(ExecutionEvent(
                    event_type="OrderRejected",
                    user_id=req.user_id,
                    broker=req.broker,
                    payload={
                        "execution_request_id": req.execution_request_id,
                        "reason": "Risk rejection",
                        "source": "risk_manager",
                    },
                ))
            except Exception as e:
                logger.warning("Risk audit record failed: %s", e)

    def _build_message(self, decision: RiskDecision, results: list[RiskRuleResult]) -> str:
        if decision == RiskDecision.APPROVED:
            return "All risk checks passed"
        rejected = [r for r in results if r.decision == RiskDecision.REJECTED]
        if rejected:
            return rejected[0].reason
        warned = [r for r in results if r.decision == RiskDecision.WARNING]
        if warned:
            return warned[0].reason
        return "Risk check completed"

    def get_config(self, user_id: str) -> RiskConfig | None:
        return self._config_cache.get(user_id)

    def invalidate_cache(self, user_id: str):
        self._config_cache.pop(user_id, None)


risk_manager = RiskManager()
