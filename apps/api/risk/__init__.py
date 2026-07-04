import importlib
from risk.models import RiskDecision, RiskConfig, RiskEvalResult, RiskRuleResult, RiskRuleType


def __getattr__(name):
    if name == "risk_manager":
        mod = importlib.import_module("risk.manager")
        return mod.risk_manager
    raise AttributeError(f"module risk has no attribute {name}")


__all__ = [
    "risk_manager",
    "RiskDecision",
    "RiskConfig",
    "RiskEvalResult",
    "RiskRuleResult",
    "RiskRuleType",
]
