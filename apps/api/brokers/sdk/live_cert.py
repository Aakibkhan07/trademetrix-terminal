"""Live broker certification (SDK v2 Phase 4).

Runs the canonical engine workflow *live* (against a real, authenticated broker
transport) and generates a structured certification report. Unlike the
interface (canned) certifications, every check here hits the live transport and
production credentials, so the report reflects the real broker.

Destructive order lifecycle steps (place/modify/cancel) are opt-in via
``allow_orders=True``. Live orchestration and report writing live in
``brokers/live_cert.py``.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from brokers.sdk.errors import UnsupportedFeatureError

LIVE_STEPS: list[str] = [
    "login",
    "token_refresh",
    "quotes",
    "history",
    "option_chain",
    "websocket",
    "positions",
    "holdings",
    "funds",
    "disconnect",
    "reconnect",
    "token_expiry",
    "circuit_recovery",
    "place_order",
    "modify_order",
    "cancel_order",
]

OPT_IN_STEPS = ("place_order", "modify_order", "cancel_order")
ORDER_STEPS = OPT_IN_STEPS


@dataclass(slots=True)
class LiveCertResult:
    broker: str
    steps: dict[str, dict[str, Any]] = field(default_factory=dict)
    elapsed: float = 0.0
    warning: str = ""

    def add(self, step: str, passed: bool, detail: str = "", error: str = "", ms: float = 0.0, skipped: bool = False) -> None:
        self.steps[step] = {
            "check": step,
            "passed": passed,
            "detail": detail,
            "error": error,
            "ms": round(ms, 1),
            "skipped": skipped,
        }

    @property
    def ran(self) -> list[dict[str, Any]]:
        return [v for v in self.steps.values() if not v.get("skipped") and (v.get("error") or v.get("passed") is True)]

    @property
    def passed(self) -> bool:
        executed = [s for s in self.steps.values() if not s.get("skipped")]
        return bool(executed) and all(s["passed"] for s in executed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "broker": self.broker,
            "passed": self.passed,
            "steps": list(self.steps.values()),
            "elapsed_s": round(self.elapsed, 2),
            "result": "LIVE_CERTIFIED" if self.passed else "LIVE_NOT_CERTIFIED",
            "warning": self.warning,
        }


# ── driver helpers ────────────────────────────────────────────────────────


async def _call_live(adapter: Any, method: str, kwargs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Invoke ``adapter.method(**kwargs)`` (sync or async) and describe outcome.

    A completed call without an exception is a passing probe — adapters
    legitimately return ``None`` for fire-and-forget operations (disconnect,
    subscribe), so certification scores completion, not truthiness.
    """
    try:
        fn = getattr(adapter, method, None)
        if not callable(fn):
            return {"passed": False, "error": f"adapter has no {method}", "skipped": True}
        result = fn(**(kwargs or {}))
        if asyncio.iscoroutine(result):
            result = await result
        return {"passed": True, "detail": _snippet(result)}
    except UnsupportedFeatureError as exc:  # capability-absent → SKIP, not FAIL
        return {"passed": False, "error": str(exc), "skipped": True}
    except Exception as exc:  # noqa: BLE001
        return {"passed": False, "error": f"{type(exc).__name__}: {exc}"}


async def _websocket_driver(adapter: Any) -> dict[str, Any]:
    if not (callable(getattr(adapter, "subscribe_market_data", None))):
        return {"passed": False, "error": "adapter lacks subscribe_market_data"}
    try:
        res = adapter.subscribe_market_data(["NSE:NIFTY"])
        if asyncio.iscoroutine(res):
            await res
        return {"passed": True, "detail": "market-data subscription accepted"}
    except Exception as exc:  # noqa: BLE001
        return {"passed": False, "error": f"{type(exc).__name__}: {exc}"}


async def _order_driver(adapter: Any, step: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "place_order": {"symbol": "NSE:NIFTY", "qty": 1, "side": "BUY", "order_type": "MARKET"},
        "modify_order": {"order_id": "NONE", "symbol": "NSE:NIFTY", "qty": 1, "price": 0},
        "cancel_order": {"order_id": "NONE"},
    }[step]
    return await _call_live(adapter, step, kwargs)


def default_driver(adapter: Any, step: str) -> Callable[..., Awaitable[dict[str, Any]]] | None:
    """Map a LIVE_STEP to the canonical adapter surface (None when absent)."""
    if step == "websocket":
        return lambda: _websocket_driver(adapter)
    if step in ORDER_STEPS:
        return lambda: _order_driver(adapter, step)
    method_map = {
        "login": ("connect", {}),
        "token_refresh": ("refresh_token", {"token": "expired"}),
        "quotes": ("get_quotes", {"symbols": ["NSE:NIFTY"]}),
        "history": ("get_historical_data", {"symbol": "NSE:NIFTY", "interval": "5m", "limit": 5}),
        "option_chain": ("get_option_chain", {"underlying": "NIFTY"}),
        "positions": ("get_positions", {}),
        "holdings": ("get_holdings", {}),
        "funds": ("get_funds", {}),
        "disconnect": ("disconnect", {}),
        "reconnect": ("connect", {}),
        "token_expiry": ("refresh_token", {"token": {"access_token": "stale-token", "expires_at": 0}}),
        "circuit_recovery": ("connect", {}),
    }
    entry = method_map.get(step)
    if entry is None:
        return None
    method, kwargs = entry
    return lambda: _call_live(adapter, method, kwargs)


# ── runner ─────────────────────────────────────────────────────────────────


async def run_live_certification(
    adapter: Any,
    *,
    broker: str = "",
    allow_orders: bool = False,
    step_drivers: dict[str, Callable[..., Awaitable[dict[str, Any]]]] | None = None,
    timeout: float = 20.0,
) -> LiveCertResult:
    """Execute every live step against a broker adapter, timing each one.

    ``step_drivers`` overrides per-step runners (tests + provider-specific
    transports); defaults come from :func:`default_driver`. Order steps record
    as skipped unless ``allow_orders=True``.
    """
    name = broker or getattr(adapter, "broker_name", "") or type(adapter).__name__
    result = LiveCertResult(broker=name)
    started = time.monotonic()

    for step in LIVE_STEPS:
        if step in ORDER_STEPS and not allow_orders:
            result.add(step, False, "skipped (opt-in: allow_orders=True)", skipped=True)
            continue
        if step_drivers is not None:
            driver = step_drivers.get(step)
        else:
            driver = default_driver(adapter, step)
        if driver is None:
            result.add(step, False, "no driver for step", skipped=True)
            continue
        stamp = time.monotonic()
        try:
            outcome = await asyncio.wait_for(driver(), timeout=timeout)
        except asyncio.TimeoutError:
            result.add(step, False, error=f"timeout >{timeout}s", ms=(time.monotonic() - stamp) * 1000)
            continue
        except Exception as exc:  # noqa: BLE001
            result.add(step, False, error=f"{type(exc).__name__}: {exc}", ms=(time.monotonic() - stamp) * 1000)
            continue
        result.add(
            step,
            bool(outcome.get("passed")),
            detail=str(outcome.get("detail", "") or ""),
            error=outcome.get("error", ""),
            ms=(time.monotonic() - stamp) * 1000,
            skipped=bool(outcome.get("skipped")),
        )
    result.elapsed = time.monotonic() - started
    return result


def write_report(result: LiveCertResult, path: str) -> None:
    """Write machine (``.json``) + human (``.md``) certification reports."""
    import json

    with open(path, "w") as fh:
        json.dump(result.to_dict(), fh, indent=2)
    with open(path.replace(".json", ".md"), "w") as fh:
        fh.write(_to_markdown(result))


def _to_markdown(result: LiveCertResult) -> str:
    lines = [
        f"# Live Certification — {result.broker}",
        "",
        f"- Result: `{result.to_dict()['result']}`",
        f"- Elapsed: {result.elapsed:.2f}s",
        "",
        "| Check | Status | Detail | Latency |",
        "|-------|--------|--------|---------|",
    ]
    for step in result.steps.values():
        if step.get("skipped"):
            status = "SKIP"
        else:
            status = "PASS" if step.get("passed") else "FAIL"
        lines.append(
            f"| {step['check']} | {status} | {step.get('detail') or step.get('error') or ''} | {step.get('ms', 0)}ms |"
        )
    return "\n".join(lines) + "\n"


def _snippet(value: Any, limit: int = 80) -> str:
    try:
        text = str(value) if value is not None else ""
        if len(text) > limit:
            text = text[:limit] + "…"
        return text
    except Exception:
        return ""


__all__ = [
    "LIVE_STEPS",
    "OPT_IN_STEPS",
    "ORDER_STEPS",
    "LiveCertResult",
    "run_live_certification",
    "write_report",
    "default_driver",
]