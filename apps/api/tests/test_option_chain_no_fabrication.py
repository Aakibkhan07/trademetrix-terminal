"""No request path may return a fabricated option chain.

## What was wrong

`OptionChainEngine.get_option_chain` and `GET /marketdata/option-chain` each fell back to
`_generate_simulated_chain` when every real source failed. That generator is a closed-form formula:

    ce_ltp = round(max(100 - dist * 15, 1), 2)
    oi     = int(500000 * (1 - dist * 0.05))
    iv     = 14.0 + dist * 1.5

It produces a plausible-looking 19-strike ladder with round-number premiums — a 24,000 CE at
`100.00`, a put at `5.00`, open interest of `500000` — plus approximate greeks from a hand-rolled
Black-Scholes with a fixed `theta = -0.1`.

The response was labelled `is_simulated: True` by the engine and `mock: True` by the route — two
different flag names for the same thing — and **the frontend read neither**. So `/trade` and
`/terminal/option-chain` displayed fabricated premiums as a market, bid/ask included, and a trader
could size a live position off them.

This is the same violation the v1.7.0 real-data contract removed from the candle path, where
`_generate_simulated_candles` was deleted on the grounds that a backtest must never run on
fabricated data. An option premium is a price people trade against, so the rule has to hold here
too: showing no chain is correct, inventing one is not.

The generator is kept — it documents the shape and the tests below still exercise it — but it must
not be reachable from a request.
"""
from __future__ import annotations

import pytest

from market import option_chain as oc


class _StubEngine:
    """The engine with every real source forced to fail."""

    def __init__(self):
        self.simulated_calls = 0

    async def _fetch_nse_option_chain(self, symbol):
        return None

    async def _fetch_fyers_option_chain(self, symbol):
        return None

    def _fetch_nse_option_chain_sync(self, symbol):  # pragma: no cover - not used
        return None


@pytest.fixture
def engine(monkeypatch):
    """A real engine instance whose real data sources all fail."""
    eng = oc.OptionChainEngine.__new__(oc.OptionChainEngine)
    monkeypatch.setattr(eng, "_fetch_nse_option_chain", _StubEngine()._fetch_nse_option_chain)
    monkeypatch.setattr(eng, "_fetch_fyers_option_chain", _StubEngine()._fetch_fyers_option_chain)
    # An empty process-local cache, so a previous test cannot satisfy the lookup.
    monkeypatch.setattr(oc.market_cache, "_option_chains", {})
    return eng


@pytest.mark.asyncio
async def test_engine_returns_nothing_when_every_real_source_fails(engine, monkeypatch):
    """The engine's fallback after NSE and Fyers is `{}` — never a generated chain."""

    def _must_not_be_called(symbol):
        raise AssertionError(
            "_generate_simulated_chain was reached from a request path — "
            "the real-data contract requires an empty result instead"
        )

    monkeypatch.setattr(engine, "_generate_simulated_chain", _must_not_be_called)

    result = await engine.get_option_chain("NIFTY")
    assert result == {}, f"expected no chain, got fabricated data: {str(result)[:120]}"


@pytest.mark.asyncio
async def test_engine_does_not_cache_or_serve_a_simulated_chain(engine, monkeypatch):
    """Nothing simulated may enter the chain cache either.

    A simulated chain that only reached the cache would be served to the *next* request from the
    TTL path, long after the code that would have flagged it was gone.
    """
    monkeypatch.setattr(
        engine,
        "_generate_simulated_chain",
        lambda s: (_ for _ in ()).throw(AssertionError("simulated generator reached")),
    )

    await engine.get_option_chain("BANKNIFTY")

    for key, (_ts, data) in oc.market_cache._option_chains.items():
        assert not data, f"a fabricated chain was cached under {key}"
        assert not data.get("is_simulated"), f"a simulated chain was cached under {key}"


def test_the_route_does_not_fall_back_to_the_generator():
    """`GET /marketdata/option-chain` must not reach `_generate_simulated_chain`.

    Asserted on the source rather than by calling the route, because the route's fallback sat
    *after* two real sources that need a broker to exercise, and a test that cannot reach the
    branch is not a test of it.
    """
    import inspect

    from routes import v1_marketdata

    src = inspect.getsource(v1_marketdata)
    handler = src.split("async def get_option_chain")[1] if "async def get_option_chain" in src else src

    assert "_generate_simulated_chain" not in handler, (
        "the option-chain route calls the simulator again — a fabricated ladder would reach the UI, "
        "which does not read the mock flag"
    )


def test_the_generator_is_still_usable_for_tests():
    """It stays, so its shape remains documented and testable — it is simply not on a request path."""
    chain = oc.OptionChainEngine._generate_simulated_chain(None, "NIFTY")  # type: ignore[arg-type]
    assert chain and chain["optionChain"], "the generator should still produce its shape for tests"
    assert "mock" in chain and chain["mock"] is True, (
        "if the generator is ever used again it must still declare itself"
    )


def test_no_response_shape_carries_two_names_for_the_same_flag():
    """`is_simulated` and `mock` were two spellings of one fact, and the UI honoured neither.

    Documents the flag inconsistency so it cannot drift further: the route said `mock`, the engine
    said `is_simulated`, and a frontend grep for either returns nothing.
    """
    eng = oc.OptionChainEngine.__new__(oc.OptionChainEngine)
    chain = oc.OptionChainEngine._generate_simulated_chain(None, "NIFTY")  # type: ignore[arg-type]
    # The generator's own flag is `mock`; the engine used to add `is_simulated`. One of them has to
    # go, and nothing downstream reads either, which is why removing the fallback was the fix
    # rather than tidying the flag.
    assert "mock" in chain
    assert "is_simulated" not in chain