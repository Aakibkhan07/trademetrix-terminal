import pytest

from market.data_socket import SharedDataSocket
from market.simulator import MarketSimulator


@pytest.mark.asyncio
async def test_shared_data_socket_singleton():
    s1 = SharedDataSocket()
    s2 = SharedDataSocket()
    assert s1 is s2


@pytest.mark.asyncio
async def test_market_simulator_start_stop():
    sim = MarketSimulator()
    await sim.start(["NIFTY", "BANKNIFTY"])
    assert sim._running is True
    await sim.stop()
    assert sim._running is False


@pytest.mark.asyncio
async def test_market_simulator_start_twice():
    sim = MarketSimulator()
    await sim.start(["NIFTY"])
    await sim.start(["RELIANCE"])
    assert len(sim._prices) == 1
    await sim.stop()
