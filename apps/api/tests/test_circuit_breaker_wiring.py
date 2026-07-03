import asyncio
from unittest.mock import patch

import pytest

from core.models import Exchange, NormalizedOrder, OrderResult, OrderSide, OrderType, ProductType
from core.resilience import CircuitBreaker
from execution.broker_adapter import BrokerExecutionAdapter


@pytest.mark.asyncio
async def test_circuit_breaker_called_for_place_order():
    class MockAdapter:
        async def place_order(self, order):
            return OrderResult(success=True)

    adapter = BrokerExecutionAdapter("user1", "test_broker")
    adapter._adapter = MockAdapter()
    adapter._authenticated = True

    breaker = CircuitBreaker(name="broker_test_broker", failure_threshold=5, recovery_timeout=30.0)

    order = NormalizedOrder(
        symbol="RELIANCE", exchange=Exchange.NSE, side=OrderSide.BUY,
        order_type=OrderType.MARKET, product=ProductType.INTRADAY, quantity=1,
    )

    with patch("execution.broker_adapter._get_breaker", return_value=breaker):
        result = await adapter.place_order(order)
        assert result.success is True
        assert breaker.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_failures():
    class MockAdapter:
        async def place_order(self, order):
            raise ValueError("API error")

    adapter = BrokerExecutionAdapter("user1", "test_broker")
    adapter._adapter = MockAdapter()
    adapter._authenticated = True

    breaker = CircuitBreaker(name="broker_test_broker", failure_threshold=2, recovery_timeout=300.0)

    order = NormalizedOrder(
        symbol="RELIANCE", exchange=Exchange.NSE, side=OrderSide.BUY,
        order_type=OrderType.MARKET, product=ProductType.INTRADAY, quantity=1,
    )

    with patch("execution.broker_adapter._get_breaker", return_value=breaker):
        r1 = await adapter.place_order(order)
        assert r1.success is False
        assert breaker.state == "closed"
        assert breaker.failure_count == 1

        r2 = await adapter.place_order(order)
        assert r2.success is False
        assert breaker.failure_count == 2
        assert breaker.state == "open"

        r3 = await adapter.place_order(order)
        assert r3.success is False
        assert "CircuitBreaker" in r3.message


@pytest.mark.asyncio
async def test_circuit_breaker_recovery_after_timeout():
    class MockAdapter:
        def __init__(self):
            self.count = 0

        async def place_order(self, order):
            self.count += 1
            if self.count <= 2:
                raise ValueError("API error")
            return OrderResult(success=True)

    adapter = BrokerExecutionAdapter("user1", "test_broker")
    adapter._adapter = MockAdapter()
    adapter._authenticated = True

    breaker = CircuitBreaker(name="broker_test_broker", failure_threshold=2, recovery_timeout=0.05)

    order = NormalizedOrder(
        symbol="RELIANCE", exchange=Exchange.NSE, side=OrderSide.BUY,
        order_type=OrderType.MARKET, product=ProductType.INTRADAY, quantity=1,
    )

    with patch("execution.broker_adapter._get_breaker", return_value=breaker):
        await adapter.place_order(order)
        await adapter.place_order(order)
        assert breaker.state == "open"

        await asyncio.sleep(0.06)

        result = await adapter.place_order(order)
        assert result.success is True
        assert breaker.state == "closed"
        assert breaker.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_breaker_per_broker_isolation():
    breaker_map = {}

    class FailingAdapter:
        async def place_order(self, order):
            raise ValueError("API error")

    class SucceedingAdapter:
        async def place_order(self, order):
            return OrderResult(success=True)

    adapter_a = BrokerExecutionAdapter("user1", "broker_a")
    adapter_a._adapter = FailingAdapter()
    adapter_a._authenticated = True

    adapter_b = BrokerExecutionAdapter("user1", "broker_b")
    adapter_b._adapter = SucceedingAdapter()
    adapter_b._authenticated = True

    order = NormalizedOrder(
        symbol="RELIANCE", exchange=Exchange.NSE, side=OrderSide.BUY,
        order_type=OrderType.MARKET, product=ProductType.INTRADAY, quantity=1,
    )

    def side_effect(name):
        if name not in breaker_map:
            breaker_map[name] = CircuitBreaker(name=name, failure_threshold=1, recovery_timeout=300.0)
        return breaker_map[name]

    with patch("execution.broker_adapter._get_breaker", side_effect=side_effect):
        r1 = await adapter_a.place_order(order)
        assert r1.success is False
        assert breaker_map["broker_broker_a"].state == "open"

        r2 = await adapter_b.place_order(order)
        assert r2.success is True
        assert breaker_map["broker_broker_b"].state == "closed"
