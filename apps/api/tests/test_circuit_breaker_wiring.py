import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from brokers.circuit_breaker_broker import CircuitBreakerBroker
from core.models import Exchange, Funds, NormalizedOrder, OrderResult, OrderSide, OrderType, ProductType
from core.resilience import CircuitBreaker, CircuitBreakerError, CircuitBreakerState, reset_all_breakers


@pytest.fixture(autouse=True)
def _reset():
    reset_all_breakers()
    yield


@pytest.mark.asyncio
async def test_circuit_breaker_closed_to_open():
    breaker = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=300.0)
    assert breaker.state == CircuitBreakerState.CLOSED

    fn = AsyncMock(side_effect=ValueError("API error"))
    with pytest.raises(ValueError):
        await breaker.call(fn)
    assert breaker.failure_count == 1
    assert breaker.state == CircuitBreakerState.CLOSED

    with pytest.raises(ValueError):
        await breaker.call(fn)
    assert breaker.failure_count == 2
    assert breaker.state == CircuitBreakerState.OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_open_rejects():
    breaker = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=300.0)
    fn = AsyncMock(side_effect=ValueError("error"))
    with pytest.raises(ValueError):
        await breaker.call(fn)
    assert breaker.state == CircuitBreakerState.OPEN

    with pytest.raises(CircuitBreakerError):
        await breaker.call(fn)


@pytest.mark.asyncio
async def test_circuit_breaker_open_uses_fallback():
    breaker = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=300.0)
    fn = AsyncMock(side_effect=ValueError("error"))
    with pytest.raises(ValueError):
        await breaker.call(fn)

    result = await breaker.call(fn, fallback="cached")
    assert result == "cached"


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_success():
    breaker = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.05)
    fn = AsyncMock(side_effect=ValueError("error"))
    with pytest.raises(ValueError):
        await breaker.call(fn)
    assert breaker.state == CircuitBreakerState.OPEN

    recovery = breaker._calculate_recovery_timeout()
    await asyncio.sleep(recovery + 0.05)
    fn.side_effect = None
    fn.return_value = "success"
    result = await breaker.call(fn)
    assert result == "success"
    assert breaker.state == CircuitBreakerState.CLOSED
    assert breaker.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_failure_backoff():
    breaker = CircuitBreaker(
        name="test", failure_threshold=1,
        recovery_timeout=0.03, max_recovery_timeout=10.0, backoff_factor=2.0,
    )
    fn = AsyncMock(side_effect=ValueError("error"))
    with pytest.raises(ValueError):
        await breaker.call(fn)
    assert breaker.state == CircuitBreakerState.OPEN
    assert breaker._consecutive_open_count == 1

    timeout_1 = breaker._calculate_recovery_timeout()
    assert timeout_1 == pytest.approx(0.06, rel=0.1)

    await asyncio.sleep(timeout_1 + 0.05)
    with pytest.raises(ValueError):
        await breaker.call(fn)
    # transitions to HALF_OPEN, then fn fails → back to OPEN
    assert breaker.state == CircuitBreakerState.OPEN
    assert breaker._consecutive_open_count == 2

    timeout_2 = breaker._calculate_recovery_timeout()
    expected = min(0.03 * (2.0 ** 2), 10.0)
    assert timeout_2 == pytest.approx(expected, rel=0.1)
    assert timeout_2 > timeout_1

    await asyncio.sleep(timeout_2 + 0.05)
    fn.side_effect = None
    fn.return_value = "ok"
    result = await breaker.call(fn)
    assert result == "ok"
    assert breaker.state == CircuitBreakerState.CLOSED
    assert breaker._consecutive_open_count == 0


@pytest.mark.asyncio
async def test_exponential_backoff_capped():
    breaker = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=1.0, max_recovery_timeout=10.0, backoff_factor=3.0)
    breaker.state = CircuitBreakerState.OPEN
    breaker._consecutive_open_count = 5

    timeout = breaker._calculate_recovery_timeout()
    expected = min(1.0 * (3.0 ** 5), 10.0)
    assert timeout == expected
    assert timeout <= breaker.max_recovery_timeout


@pytest.mark.asyncio
async def test_circuit_breaker_reset():
    from core.resilience import _get_breaker
    breaker = _get_breaker("test_reset")
    breaker.failure_threshold = 1
    fn = AsyncMock(side_effect=ValueError("error"))
    with pytest.raises(ValueError):
        await breaker.call(fn)
    assert breaker.state == CircuitBreakerState.OPEN

    reset_all_breakers()
    assert breaker.state == CircuitBreakerState.CLOSED
    assert breaker.failure_count == 0
    assert breaker._consecutive_open_count == 0


@pytest.mark.asyncio
async def test_broker_wrapper_place_order():
    inner = MagicMock()
    inner.broker_name = "test_broker"
    inner.place_order = AsyncMock(return_value=OrderResult(success=True))
    wrapper = CircuitBreakerBroker(inner)

    order = NormalizedOrder(
        symbol="RELIANCE", exchange=Exchange.NSE, side=OrderSide.BUY,
        order_type=OrderType.MARKET, product=ProductType.INTRADAY, quantity=1,
    )
    result = await wrapper.place_order(order)
    assert result.success is True
    inner.place_order.assert_called_once_with(order)


@pytest.mark.asyncio
async def test_broker_wrapper_opens_on_failures():
    inner = MagicMock()
    inner.broker_name = "test_broker"
    inner.place_order = AsyncMock(side_effect=ValueError("API error"))
    wrapper = CircuitBreakerBroker(inner, breaker_name="broker_test_broker")

    order = NormalizedOrder(
        symbol="RELIANCE", exchange=Exchange.NSE, side=OrderSide.BUY,
        order_type=OrderType.MARKET, product=ProductType.INTRADAY, quantity=1,
    )
    breaker = wrapper._breaker
    breaker.failure_threshold = 2

    with pytest.raises(ValueError):
        await wrapper.place_order(order)
    assert breaker.state == CircuitBreakerState.CLOSED
    assert breaker.failure_count == 1

    with pytest.raises(ValueError):
        await wrapper.place_order(order)
    assert breaker.state == CircuitBreakerState.OPEN

    with pytest.raises(CircuitBreakerError):
        await wrapper.place_order(order)


@pytest.mark.asyncio
async def test_broker_wrapper_get_funds_fallback():
    inner = MagicMock()
    inner.broker_name = "test_broker"
    inner.get_funds = AsyncMock(side_effect=ValueError("API error"))
    wrapper = CircuitBreakerBroker(inner, breaker_name="broker_test_broker")
    wrapper._breaker.failure_threshold = 1

    funds = await wrapper.get_funds()
    assert isinstance(funds, Funds)
    assert funds.broker == "test_broker"


@pytest.mark.asyncio
async def test_broker_wrapper_get_orderbook_fallback():
    inner = MagicMock()
    inner.broker_name = "test_broker"
    inner.get_orderbook = AsyncMock(side_effect=ValueError("error"))
    wrapper = CircuitBreakerBroker(inner, breaker_name="broker_test_broker")
    wrapper._breaker.failure_threshold = 1

    result = await wrapper.get_orderbook()
    assert result == []


@pytest.mark.asyncio
async def test_broker_wrapper_broker_name():
    inner = MagicMock()
    inner.broker_name = "fyers"
    wrapper = CircuitBreakerBroker(inner)
    assert wrapper.broker_name == "fyers"


@pytest.mark.asyncio
async def test_state_gauge_callback():
    calls = []
    from core.resilience import set_breaker_state_callback

    def callback(name, state):
        calls.append((name, state))

    set_breaker_state_callback(callback)
    breaker = CircuitBreaker(name="test_gauge", failure_threshold=1, recovery_timeout=300.0)
    fn = AsyncMock(side_effect=ValueError("error"))
    with pytest.raises(ValueError):
        await breaker.call(fn)

    assert ("test_gauge", "open") in calls
    set_breaker_state_callback(None)
