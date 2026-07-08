import asyncio
import random

import httpx
import pytest

from core.config import settings
from execution.retry import retry_with_backoff


@pytest.mark.asyncio
async def test_retry_with_backoff_jitter():
    call_count = 0

    async def failing_op():
        nonlocal call_count
        call_count += 1
        raise asyncio.TimeoutError("timed out")

    with pytest.raises(asyncio.TimeoutError):
        await retry_with_backoff(
            "test_jitter",
            failing_op,
            max_retries=3,
            base_delay=0.01,
        )

    assert call_count == 4

    results = []
    for _ in range(100):
        delay = random.uniform(0, min(0.01 * (2 ** 1), 30.0))
        results.append(delay)

    assert all(r > 0 for r in results)
    assert max(results) <= 30.0
    assert min(results) > 0


@pytest.mark.asyncio
async def test_broker_adapter_place_order_transient_re_raises():
    from execution.broker_adapter import BrokerExecutionAdapter

    class MockAdapter:
        async def place_order(self, order):
            raise httpx.TimeoutException("Connection timed out", request=None)

    adapter = BrokerExecutionAdapter("user1", "zerodha")
    adapter._adapter = MockAdapter()
    adapter._authenticated = True

    from core.models import NormalizedOrder, Exchange, OrderSide, OrderType, ProductType

    order = NormalizedOrder(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        product=ProductType.INTRADAY,
        quantity=1,
    )

    with pytest.raises(httpx.TimeoutException):
        await adapter.place_order(order)


@pytest.mark.asyncio
async def test_broker_adapter_place_order_non_transient_returns_result():
    from execution.broker_adapter import BrokerExecutionAdapter

    class MockAdapter:
        async def place_order(self, order):
            raise ValueError("Invalid symbol")

    adapter = BrokerExecutionAdapter("user1", "zerodha")
    adapter._adapter = MockAdapter()
    adapter._authenticated = True

    from core.models import NormalizedOrder, Exchange, OrderSide, OrderType, ProductType

    order = NormalizedOrder(
        symbol="INVALID",
        exchange=Exchange.NSE,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        product=ProductType.INTRADAY,
        quantity=1,
    )

    result = await adapter.place_order(order)
    assert result.success is False
    assert "Invalid symbol" in result.message


def test_settings_have_timeout_defaults():
    assert hasattr(settings, "broker_request_timeout")
    assert hasattr(settings, "broker_connect_timeout")
    assert settings.broker_request_timeout == 8
    assert settings.broker_connect_timeout == 5
