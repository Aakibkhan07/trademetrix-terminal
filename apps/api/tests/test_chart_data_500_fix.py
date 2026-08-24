"""Regression tests for the chart-data 500 fix (2026-08-24).

The prod browser crawl found every chart widget (/live, /marketdata, /workspace)
getting 500s from GET /marketdata/historical because:
  1. the route had no error handling (ValueError escaped as an ASGI crash),
  2. the Yahoo fallback gate rejected the app's canonical BARE index symbols
     ("NIFTY50-INDEX" etc.) so no fallback data was ever fetched,
  3. quotes had the same hole (_to_yahoo built invalid "<sym>.NS" tickers),
  4. buyer_strategy_service silently fabricated candles on data failure.
"""

from unittest.mock import AsyncMock, patch

import pytest

from market.historical import HistoricalDataEngine
from providers.yahoo import YAHOO_SYMBOL_MAP, _to_yahoo


BARE_INDEX_SYMBOLS = [
    "NIFTY50-INDEX", "NIFTYBANK-INDEX", "FINNIFTY-INDEX", "MIDCPNIFTY-INDEX",
    "INDIAVIX-INDEX", "NIFTYIT-INDEX", "NIFTYPHARMA-INDEX", "NIFTYAUTO-INDEX",
    "NIFTYFMCG-INDEX", "NIFTYMETAL-INDEX", "NIFTYREALTY-INDEX",
]


class TestYahooSymbolMap:
    @pytest.mark.parametrize("symbol", BARE_INDEX_SYMBOLS)
    def test_bare_index_symbols_map_to_valid_yahoo_tickers(self, symbol):
        mapped = _to_yahoo(symbol)
        assert not mapped.endswith(".NS") or mapped[0].isalpha() and "INDEX" not in mapped
        assert symbol not in mapped or mapped in YAHOO_SYMBOL_MAP.values()

    def test_nifty50_bare_maps_to_nsei(self):
        assert _to_yahoo("NIFTY50-INDEX") == "^NSEI"


class TestYahooFallbackGate:
    @pytest.fixture
    def engine(self):
        return HistoricalDataEngine()

    @pytest.mark.asyncio
    async def test_bare_index_symbol_passes_gate_and_fetches(self, engine):
        with patch("providers.yahoo.fetch_historical", new=AsyncMock(return_value=[])) as fh:
            await engine._fetch_from_yahoo("NIFTY50-INDEX", "NSE", "5m", 1)
            assert fh.await_count == 1
            assert fh.await_args.kwargs.get("interval") or fh.await_args.args

    @pytest.mark.asyncio
    async def test_prefixed_index_symbol_passes_gate(self, engine):
        with patch("providers.yahoo.fetch_historical", new=AsyncMock(return_value=[])) as fh:
            await engine._fetch_from_yahoo("NSE:NIFTYIT-INDEX", "NSE", "5m", 1)
            assert fh.await_count == 1

    @pytest.mark.asyncio
    async def test_unknown_symbol_degrades_gracefully(self, engine):
        """Unknown symbols now attempt Yahoo (permissive gate) but never raise —
        they come back as an empty list and the route surfaces a clean 400."""
        with patch("providers.yahoo.fetch_historical", new=AsyncMock(return_value=[])):
            result = await engine._fetch_from_yahoo("TOTALLY-UNKNOWN-SYM", "NSE", "5m", 1)
            assert result == []

    @pytest.mark.asyncio
    async def test_gate_maps_bare_symbol_for_provider_call(self, engine):
        from core.models import Candle

        candle = Candle(
            symbol="^NSEI", timestamp=__import__("datetime").datetime(2026, 8, 21, 9, 15),
            open=1.0, high=2.0, low=0.5, close=1.5, volume=100,
            exchange="NSE", interval="1d",
        )
        with patch("providers.yahoo.fetch_historical", new=AsyncMock(return_value=[candle])) as fh:
            result = await engine._fetch_from_yahoo("NIFTY50-INDEX", "NSE", "1d", 7)
            assert len(result) == 1
            assert fh.await_args.args[0] == "NSE:NIFTY50-INDEX"


class TestHistoricalRouteErrorHandling:
    @pytest.mark.asyncio
    async def test_no_real_data_surfaces_as_400_not_500(self):
        from routes.v1_marketdata import get_historical

        user = type("U", (), {"id": "u1"})()
        err = ValueError("No real market data available for NIFTY50-INDEX (5m, 1d)")
        with patch("engine.backtest.fetch_historical_data", new=AsyncMock(side_effect=err)):
            import fastapi

            with pytest.raises(fastapi.HTTPException) as exc:
                await get_historical(symbol="NIFTY50-INDEX", exchange="NSE", interval="5m", days=1, current_user=user)
            assert exc.value.status_code == 400
            assert "No real market data" in exc.value.detail

    @pytest.mark.asyncio
    async def test_unexpected_failure_surfaces_as_502(self):
        from routes.v1_marketdata import get_historical

        user = type("U", (), {"id": "u1"})()
        with patch("engine.backtest.fetch_historical_data", new=AsyncMock(side_effect=RuntimeError("boom"))):
            import fastapi

            with pytest.raises(fastapi.HTTPException) as exc:
                await get_historical(symbol="NIFTY50-INDEX", exchange="NSE", interval="5m", days=1, current_user=user)
            assert exc.value.status_code == 502

    @pytest.mark.asyncio
    async def test_success_passthrough(self):
        from routes.v1_marketdata import get_historical

        user = type("U", (), {"id": "u1"})()
        candles = [{"timestamp": "t", "open": 1, "close": 1}]
        with patch("engine.backtest.fetch_historical_data", new=AsyncMock(return_value=candles)):
            result = await get_historical(symbol="NIFTY50-INDEX", exchange="NSE", interval="5m", days=1, current_user=user)
            assert result["candles"] == candles


class TestBuyerServiceRealDataOnly:
    @pytest.mark.asyncio
    async def test_backtest_raises_on_data_gap_never_simulates(self):
        from application.services.buyer_strategy_service import BuyerStrategyService

        svc = BuyerStrategyService()
        err = ValueError("No real market data available")
        # module-level import → patch the SOURCE reference in the service module
        with patch("application.services.buyer_strategy_service.fetch_historical_data", new=AsyncMock(side_effect=err)):
            with pytest.raises(ValueError):
                await svc.backtest(
                    strategy_key="macd_cross", symbol="NIFTY", user_id="u1",
                    exchange="NSE", interval="5m", days=30,
                    initial_capital=100000.0, config={},
                )

    def test_simulated_candles_generator_removed(self):
        from application.services.buyer_strategy_service import BuyerStrategyService

        assert not hasattr(BuyerStrategyService, "_generate_simulated_candles")
