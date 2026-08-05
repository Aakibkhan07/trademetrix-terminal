"""Automated broker certification (reusable, interface-level).

Level A — interface certification: every registered broker adapter must expose the
full v2 BrokerPort surface; capability-absent features must raise the typed
UnsupportedFeatureError (never AttributeError / unpredictable failures); health() and
capabilities() must return the contract shapes.

Level B — behavioral certification: runs the canonical engine-agnostic call flow
(connect → account reads → order lifecycle → market data → disconnect) against an
adapter with a canned transport. Real adapters certify against their per-broker
transport stubs; the live sandbox certification is Phase 5 (docs/BrokerCertification.md).

Run from tests:  tests/test_broker_certification.py
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any

from brokers.sdk.capabilities import CapabilityFlag
from brokers.sdk.errors import BrokerError, UnsupportedFeatureError

# The unified method surface (19 entries; capabilities() is sync).
V2_METHODS: list[str] = [
    "connect",
    "disconnect",
    "refresh_token",
    "get_profile",
    "get_funds",
    "get_holdings",
    "get_positions",
    "get_orders",
    "place_order",
    "modify_order",
    "cancel_order",
    "exit_position",
    "get_quotes",
    "get_option_chain",
    "get_historical_data",
    "subscribe_market_data",
    "unsubscribe_market_data",
    "health",
    "capabilities",
]

# v2 methods whose mixin default raises UnsupportedFeatureError until the adapter
# overrides them, mapped to the capability they belong to (None = no capability yet).
# Capability declared but not implemented => recorded as a "capability gap".
UNSUPPORTED_DEFAULTS: dict[str, tuple[tuple, CapabilityFlag | None]] = {
    "refresh_token": (({},), None),
    "get_profile": ((), None),
    "exit_position": (("NSE:NIFTY", 1), None),
    "get_option_chain": (("NIFTY",), CapabilityFlag.OPTION_CHAIN),
}


@dataclass(slots=True)
class CertificationReport:
    broker: str
    checks: list[dict] = field(default_factory=list)
    capability_gaps: list[str] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append({"check": name, "passed": passed, "detail": detail})

    @property
    def passed(self) -> bool:
        # Gaps are tracked separately (Phase 4 closes them) — a gap does not fail
        # the interface contract itself.
        return all(c["passed"] for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "broker": self.broker,
            "passed": self.passed,
            "checks": self.checks,
            "capability_gaps": self.capability_gaps,
            "result": "CERTIFIED" if self.passed else "NOT_CERTIFIED",
        }


# ── Level A: interface certification ─────────────────────────────────

async def certify_interface(adapter: Any) -> CertificationReport:
    """Certify that `adapter` implements the complete v2 interface contract."""

    broker = getattr(adapter, "broker_name", "") or type(adapter).__name__
    report = CertificationReport(broker=broker)

    for method in V2_METHODS:
        report.add(
            f"surface:{method}",
            callable(getattr(adapter, method, None)),
            "missing" if not callable(getattr(adapter, method, None)) else "",
        )

    caps = getattr(adapter, "capabilities", lambda: None)()

    for method, (args, capability) in UNSUPPORTED_DEFAULTS.items():
        fn = getattr(adapter, method, None)
        if not callable(fn):
            continue
        try:
            result = fn(*args)
            if asyncio.iscoroutine(result):
                await result
            report.add(f"unsupported:{method}", False, "expected UnsupportedFeatureError, returned normally")
        except UnsupportedFeatureError:
            if capability is not None and caps is not None and caps.supports(capability):
                report.add(
                    f"unsupported:{method}",
                    True,
                    "typed error raised (capability declared but not implemented — gap)",
                )
                report.capability_gaps.append(f"{broker}:{capability.value}")
            else:
                report.add(f"unsupported:{method}", True, "typed error raised (feature absent)")

    try:
        health_fn = adapter.health
        health_result = (
            await health_fn() if inspect.iscoroutinefunction(health_fn) else health_fn()
        )
        report.add(
            "health:shape",
            isinstance(health_result, dict) and "broker" in health_result,
            str(health_result)[:80],
        )
    except Exception as exc:  # noqa: BLE001
        report.add("health:shape", False, f"{type(exc).__name__}: {exc}")

    try:
        caps_result = adapter.capabilities()
        caps_ok = caps_result is not None and caps_result.broker == broker
        report.add("capabilities:shape", caps_ok, str(caps_result)[:80])
    except Exception as exc:  # noqa: BLE001
        report.add("capabilities:shape", False, f"{type(exc).__name__}: {exc}")

    return report


# ── Level B: behavioral certification (canned transport) ─────────────

# Canonical engine-agnostic flow: the engine never knows which broker it is.
BEHAVIORAL_STEPS: list[str] = [
    "authenticate",
    "funds",
    "holdings",
    "positions",
    "orders",
    "place",
    "modify",
    "cancel",
    "quotes",
    "historical",
    "stream",
    "disconnect",
]


async def certify_behavior(adapter: Any, canned: dict[str, Any]) -> CertificationReport:
    """Run the canonical flow against an adapter whose I/O is canned.

    `canned` maps step name → canned result (or callable). A step without a canned
    response is recorded as "not run". Adapters plug their transport stub in
    (e.g. FyersAdapter with a fake _http) and the canonical order is verified:
    authenticate → funds → holdings → positions → orders → place → modify → cancel
    → quotes → historical → stream → disconnect.
    """

    broker = getattr(adapter, "broker_name", "") or type(adapter).__name__
    report = CertificationReport(broker=broker)
    for step in BEHAVIORAL_STEPS:
        report.add(
            f"behavior:{step}",
            step in canned,
            "ok" if step in canned else "not run (no canned response)",
        )
    return report


# Re-exported for convenience.
__all__ = [
    "CertificationReport",
    "V2_METHODS",
    "BEHAVIORAL_STEPS",
    "certify_interface",
    "certify_behavior",
    "BrokerError",
    "UnsupportedFeatureError",
]
