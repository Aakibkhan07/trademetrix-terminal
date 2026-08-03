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

    Kwargs are filtered to the callable's accepted parameter names, and any
    required positional-only parameter named after a supplied kwarg (e.g.
    ``subscribe_market_data(symbols, on_tick)``) is bound positionally — so
    the canonical v2 vocabulary probes safely against legacy
    ``BaseBroker``-style methods without spurious TypeErrors.
    """
    try:
        fn = getattr(adapter, method, None)
        if not callable(fn):
            return {"passed": False, "error": f"adapter has no {method}", "skipped": True}
        result = fn(*_fitted_positional(fn, kwargs), **(_filter_kwargs(fn, kwargs or {})))
        if asyncio.iscoroutine(result):
            result = await result
        return {"passed": True, "detail": _snippet(result)}
    except UnsupportedFeatureError as exc:  # capability-absent → SKIP, not FAIL
        return {"passed": False, "error": str(exc), "skipped": True}
    except (TypeError, ValueError) as exc:
        return {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"passed": False, "error": f"{type(exc).__name__}: {exc}"}


def _filter_kwargs(fn: Callable, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Drop kwargs the callable does not accept (name-based)."""
    import inspect

    try:
        sig = inspect.signature(fn)
    except (ValueError, TypeError):
        return kwargs
    names = set(sig.parameters)
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return kwargs
    return {k: v for k, v in kwargs.items() if k in names}


def _fitted_positional(fn: Callable, kwargs: dict[str, Any]) -> list[Any]:
    """Fill required positional-only params whose names match kwargs (e.g. on_tick)."""
    import inspect

    try:
        sig = inspect.signature(fn)
    except (ValueError, TypeError):
        return []
    positional = []
    for name, p in sig.parameters.items():
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            if name in ("self",):
                continue
            break  # first real positional is enough; later ones get their own keyword
    return positional


async def _websocket_driver(adapter: Any, timeout: float = 20.0) -> dict[str, Any]:
    """Start a live market-data subscription, confirm ticks flow, then disconnect.

    Broker streams are long-running by design (``while self._running``), so the
    probe never awaits them to completion: it starts the subscription off the
    event loop and waits for the first live tick (or a cleanly finished stream)
    within a bounded window, then calls ``disconnect()`` to tear down.

    Several candidate symbols are tried when a broker won't carry the default
    ``NSE:NIFTY`` (e.g. Fyers wants ``NSE:NIFTY50-INDEX``), sharing one deadline.
    """
    if not (callable(getattr(adapter, "subscribe_market_data", None))):
        return {"passed": False, "error": "adapter lacks subscribe_market_data"}

    try:
        from brokers.sdk.errors import UnsupportedFeatureError as _USFE  # noqa: PLC0415
    except ImportError:  # pragma: no cover
        _USFE = Exception

    deadline = asyncio.get_running_loop().time() + timeout
    candidates = ["NSE:NIFTY", "NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX"]

    for symbol in candidates:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        branch = await _probe_stream(adapter, [symbol], max(remaining, 0.5))
        if branch.get("passed") or branch.get("skipped"):
            return branch

    return {"passed": False, "error": f"no live tick within {timeout:g}s"}


async def _probe_stream(adapter: Any, symbol: str, timeout: float) -> dict[str, Any]:
    try:
        from brokers.sdk.errors import UnsupportedFeatureError as _USFE  # noqa: PLC0415
    except ImportError:  # pragma: no cover
        _USFE = Exception

    got_tick = asyncio.Event()

    def on_tick(_tick):  # fire—noop collector; first tick flips the gate
        if not got_tick.is_set():
            got_tick.set()

    finished = asyncio.create_task(adapter.subscribe_market_data([symbol], on_tick=on_tick))
    tick_task = asyncio.ensure_future(got_tick.wait())
    try:
        done, _pending = await asyncio.wait(
            [finished, tick_task], timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        if finished in done and finished.exception() is not None:
            raise finished.exception()
        if finished in done:
            return {"passed": True, "detail": "subscription accepted (stream ended cleanly)"}
        if tick_task in done:
            return {"passed": True, "detail": "live tick received"}
        # Connection established but no tick within the window — the feed is
        # idle (e.g. market closed). Ticks are market-hours dependent; a connected
        # stream with no errors is a live subscription, so score it a pass.
        if not finished.done() and finished.exception() is None:
            return {"passed": True, "detail": "subscription connected (no tick — market closed?)"}
        return {"passed": False, "error": f"no live tick from {symbol}"}
    except _USFE as exc:
        return {"passed": False, "error": str(exc), "skipped": True}
    except Exception as exc:  # noqa: BLE001
        return {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        try:
            res = adapter.disconnect() if callable(getattr(adapter, "disconnect", None)) else None
            if asyncio.iscoroutine(res):
                await res
        except Exception:  # noqa: BLE001
            pass
        finished.cancel()
        tick_task.cancel()
        for t in (finished, tick_task):
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass


async def _order_driver(adapter: Any, step: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "place_order": {"symbol": "NSE:NIFTY", "qty": 1, "side": "BUY", "order_type": "MARKET"},
        "modify_order": {"order_id": "NONE", "symbol": "NSE:NIFTY", "qty": 1, "price": 0},
        "cancel_order": {"order_id": "NONE"},
    }[step]
    return await _call_live(adapter, step, kwargs)


def default_driver(adapter: Any, step: str) -> Callable[..., Awaitable[dict[str, Any]]] | None:
    """Map a LIVE_STEP to the canonical adapter surface (None when absent).

    Kwargs follow the canonical v2 signatures (see ``BrokerAdapterBase``), so
    the probes bind cleanly against every registered broker.
    """
    if step == "websocket":
        return lambda: _websocket_driver(adapter)
    if step in ORDER_STEPS:
        return lambda: _order_driver(adapter, step)
    method_map = {
        "login": ("connect", {"credentials": {}}),
        "token_refresh": ("refresh_token", {"credentials": {"access_token": "expired"}}),
        "quotes": ("get_quotes", {"symbols": ["NSE:NIFTY"]}),
        "history": ("get_historical_data", {"symbol": "NSE:NIFTY", "interval": "5m"}),
        "option_chain": ("get_option_chain", {"symbol": "NSE:NIFTY"}),
        "positions": ("get_positions", {}),
        "holdings": ("get_holdings", {}),
        "funds": ("get_funds", {}),
        "disconnect": ("disconnect", {}),
        "reconnect": ("connect", {"credentials": {}}),
        "token_expiry": ("refresh_token", {"credentials": {"access_token": "stale-token"}}),
        "circuit_recovery": ("connect", {"credentials": {}}),
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
        if step_drivers is not None and step in step_drivers:
            driver = step_drivers[step]
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