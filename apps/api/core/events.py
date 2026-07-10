from enum import StrEnum


class EventType(StrEnum):
    AUDIT_LOG = "audit.log"
    ORDER_REJECTED = "order.rejected"
    ORDER_PLACED = "order.placed"
    RISK_DECISION = "risk.decision"
    BROKER_AUTH = "broker.auth"
    NOTIFICATION = "notification"
    KILL_SWITCH = "kill_switch"
    BACKTEST_COMPLETE = "backtest.complete"
    STRATEGY_DEPLOYED = "strategy.deployed"
