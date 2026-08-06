"""Canonical ``SignalGenerated`` payload contract tests.

Covers: ``SignalPayload`` versioning/defaults, the canonical Strategy Runtime
emitter (``strategy_runtime.workers``), warm-up suppression (execute=False never
publishes to the feed), and the legacy runtime mapper
(``runtime.manager``) producing the SAME canonical shape.
"""
import asyncio
import datetime
import json

import pytest

from core.models import (
    Candle,
    Exchange,
    NormalizedOrder,
    OrderSide,
    OrderType,
    ProductType,
)
from execution.event_bus import execution_event_bus
from strategies.base import SignalResult
from strategy_runtime.models import SignalPayload, StrategySpec
from strategy_runtime.registry import RuntimeRecord
from strategy_runtime.workers import StrategyWorker

USER = "signal-payload-test-user"
SID = "sig-payload-0001"


class FakeSignalStrategy:
    """Minimal GraphStrategy stand-in with a display name."""

    name = "Fake Signal"

    def __init__(self, config=None):
        self.config = config or {}
        self._memory = {}

    async def on_start(self):
        return None

    async def on_stop(self):
        return None

    async def on_tick(self, tick):
        return None

    async def on_candle(self, candle):
        if candle.close > 100.0:
            return SignalResult(reason="fake-buy", orders=[
                NormalizedOrder(
                    symbol="NSE:NIFTY50-INDEX",
                    exchange=Exchange.NSE,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    product=ProductType.INTRADAY,
                    quantity=10,
                    price=101.0,
                ),
            ])
        return None


class EventCapture:
    """Bus subscriber that records SignalGenerated events (self-cleaning)."""

    def __init__(self):
        self.events: list = []
        self.handler = self._handler

    async def _handler(self, event):
        self.events.append(event)

    def attach(self):
        execution_event_bus.subscribe("*", self.handler)

    def detach(self):
        execution_event_bus.unsubscribe("*", self.handler)

    def signal_generated(self):
        return [e for e in self.events if e.event_type == "SignalGenerated"]


@pytest.fixture
def capture():
    cap = EventCapture()
    cap.attach()
    yield cap
    cap.detach()


def _spec(is_paper: bool = True, broker: str = "paper") -> StrategySpec:
    return StrategySpec(
        strategy_id=SID,
        user_id=USER,
        symbol="NIFTY",
        exchange="NSE",
        interval="15m",
        timeframes=["15m"],
        mode="paper" if is_paper else "live",
        is_paper=is_paper,
        broker=broker,
        quantity=10,
    )


def _worker(spec: StrategySpec) -> StrategyWorker:
    record = RuntimeRecord(spec)
    worker = StrategyWorker(record, lifecycle=None)
    worker._strategy = FakeSignalStrategy({"symbol": spec.symbol, "strategy_id": spec.strategy_id})
    return worker


def _signal(side=OrderSide.BUY, qty=10, price=101.0, reason="unit-signal") -> SignalResult:
    return SignalResult(reason=reason, orders=[
        NormalizedOrder(
            symbol="NSE:NIFTY50-INDEX",
            exchange=Exchange.NSE,
            side=side,
            order_type=OrderType.MARKET,
            product=ProductType.INTRADAY,
            quantity=qty,
            price=price,
        ),
    ])


def _candle(close: float) -> Candle:
    return Candle(
        symbol="NSE:NIFTY50-INDEX",
        exchange=Exchange.NSE,
        interval="15m",
        open=close - 1.0,
        high=close + 1.0,
        low=close - 2.0,
        close=close,
        volume=1000.0,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        oi=0.0,
    )


# --------------------------------------------------------------------------- #
def test_payload_defaults_and_version():
    p = SignalPayload()
    assert p.signal_version == 1
    assert p.side == "HOLD"
    assert p.mode == "paper"
    assert p.confidence == 0.0
    assert p.price == 0.0
    assert p.sl_price == 0.0
    assert p.target_price == 0.0
    assert p.metadata == {}
    assert p.payload()["signal_version"] == 1
    for key in (
        "signal_version", "signal_id", "strategy_id", "strategy_name",
        "user_id", "symbol", "exchange", "side", "quantity", "price",
        "sl_price", "target_price", "confidence", "reason", "mode",
        "triggered_at", "metadata",
    ):
        assert key in p.payload(), f"missing canonical field {key}"


def test_payload_is_json_serializable():
    p = SignalPayload(strategy_id=SID, symbol="NSE:NIFTY50-INDEX", side="BUY")
    raw = json.dumps(p.payload())
    assert '"signal_version": 1' in raw
    assert '"side": "BUY"' in raw


def test_unknown_signal_version_ignored_fields():
    """Forward-compat rule: payload with a newer version must not break
    consumers that read only known fields."""
    p = SignalPayload()
    assert p.signal_version == 1  # consumers key on the version
    assert isinstance(p.payload(), dict)


@pytest.mark.asyncio
async def test_canonical_worker_emits_standard_signal(capture):
    worker = _worker(_spec(is_paper=True))
    worker._emit_signal(_signal(side=OrderSide.BUY, qty=10, price=101.0, reason="unit-buy"))
    await asyncio.sleep(0.05)

    emitted = capture.signal_generated()
    assert len(emitted) == 1
    p = emitted[0].payload
    assert p["signal_version"] == 1
    assert p["strategy_id"] == SID
    assert p["user_id"] == USER
    assert p["symbol"] == "NSE:NIFTY50-INDEX"
    assert p["side"] == "BUY"
    assert p["quantity"] == 10
    assert p["price"] == 101.0
    assert p["mode"] == "paper"
    assert p["strategy_name"] == "Fake Signal"
    assert p["reason"] == "unit-buy"
    assert p["metadata"]["interval"] == "15m"
    assert p["metadata"]["order_count"] == 1


@pytest.mark.asyncio
async def test_canonical_worker_live_mode(capture):
    worker = _worker(_spec(is_paper=False, broker="fyers"))
    worker._emit_signal(_signal(side=OrderSide.SELL, qty=5))
    await asyncio.sleep(0.05)

    emitted = capture.signal_generated()
    assert len(emitted) == 1
    assert emitted[0].payload["mode"] == "live"
    assert emitted[0].payload["side"] == "SELL"


@pytest.mark.asyncio
async def test_warmup_signal_not_emitted(capture):
    worker = _worker(_spec(is_paper=True))
    await worker._evaluate(_candle(close=101.0), execute=False)
    assert worker.record.stats["signals"] == 1  # counted...
    assert worker.record.stats["orders_placed"] == 0  # ...never executed
    await asyncio.sleep(0.05)
    assert len(capture.signal_generated()) == 0  # and never published


def test_legacy_runtime_payload_canonical_shape():
    from runtime.manager import runtime_manager
    from runtime.models import RuntimeConfig, RuntimeSignal, SignalSide

    config = RuntimeConfig(
        strategy_id=SID,
        user_id=USER,
        strategy_key="S",
        symbol="NIFTY",
        exchange="NSE",
        broker="fyers",
    )
    signal = RuntimeSignal(
        strategy_id=SID,
        signal_id="legacy-sig",
        side=SignalSide.BUY,
        confidence=0.9,
        reason="legacy-cross",
        symbol="NSE:NIFTY50-INDEX",
        exchange="NSE",
        quantity=25,
        price=101.5,
        sl_price=99.0,
        target_price=104.0,
        metadata={"latency_ms": 1.2},
    )
    payload = runtime_manager._signal_payload(config, FakeSignalStrategy({}), signal)

    assert payload["signal_version"] == 1
    assert payload["strategy_id"] == SID
    assert payload["strategy_name"] == "Fake Signal"
    assert payload["user_id"] == USER
    assert payload["symbol"] == "NSE:NIFTY50-INDEX"
    assert payload["side"] == "BUY"
    assert payload["quantity"] == 25
    assert payload["price"] == 101.5
    assert payload["sl_price"] == 99.0
    assert payload["target_price"] == 104.0
    assert payload["confidence"] == 0.9
    assert payload["mode"] == "live"  # configured broker -> live
    assert payload["metadata"]["latency_ms"] == 1.2


def test_legacy_runtime_payload_paper_mode():
    from runtime.manager import runtime_manager
    from runtime.models import RuntimeConfig, RuntimeSignal, SignalSide

    config = RuntimeConfig(strategy_id=SID, user_id=USER, strategy_key="s", symbol="NIFTY", broker="paper")
    signal = RuntimeSignal(strategy_id=SID, signal_id="x", side=SignalSide.BUY, symbol="NIFTY")
    payload = runtime_manager._signal_payload(config, FakeSignalStrategy({}), signal)
    assert payload["mode"] == "paper"