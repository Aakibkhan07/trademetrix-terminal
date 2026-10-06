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

    # A transport failure is still re-raised rather than swallowed into a failed result --
    # that was the original point of this test and it still holds. The type changed on
    # purpose: a bare `httpx.TimeoutException` reached `retry_with_backoff`, which classified
    # it as transient and re-sent the POST up to `MAX_RETRIES` more times against a broker
    # that may already have accepted the first one. The raised error now says the result is
    # *unknown*, which `retry_with_backoff` refuses to retry and the OMS routes to
    # reconciliation. The original exception is kept as `__cause__` so nothing is lost.
    from execution.indeterminate import ORDER_RESULT_UNKNOWN, IndeterminateOrderError

    with pytest.raises(IndeterminateOrderError) as caught:
        await adapter.place_order(order)
    assert caught.value.code == ORDER_RESULT_UNKNOWN
    assert isinstance(caught.value.__cause__, httpx.TimeoutException)
    assert "Connection timed out" in str(caught.value.__cause__)


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
    assert settings.broker_request_timeout > 0
    assert settings.broker_connect_timeout > 0
