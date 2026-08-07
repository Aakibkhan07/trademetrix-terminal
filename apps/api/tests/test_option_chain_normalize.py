import pytest

from market.option_chain import SUPPORTED_INDICES, normalize_index_symbol, option_chain_engine


def test_normalize_strips_exchange_prefix():
    assert normalize_index_symbol("NSE:NIFTY50-INDEX") == "NIFTY"
    assert normalize_index_symbol("BSE:SENSEX-INDEX") == "SENSEX"
    assert normalize_index_symbol("NFO:NIFTY50-INDEX") == "NIFTY"


def test_normalize_index_aliases():
    assert normalize_index_symbol("NIFTYBANK-INDEX") == "BANKNIFTY"
    assert normalize_index_symbol("FINNIFTY-INDEX") == "FINNIFTY"
    assert normalize_index_symbol("MIDCPNIFTY-INDEX") == "MIDCPNIFTY"
    assert normalize_index_symbol("SENSEX-INDEX") == "SENSEX"


def test_midcpnifty_supported_passthrough_and_simulated():
    assert "MIDCPNIFTY" in SUPPORTED_INDICES
    assert normalize_index_symbol("MIDCPNIFTY") == "MIDCPNIFTY"
    chain = option_chain_engine._generate_simulated_chain("MIDCPNIFTY-INDEX")
    assert chain is not None
    assert len(chain["optionChain"]) > 0


def test_normalize_passthrough():
    assert normalize_index_symbol("NIFTY") == "NIFTY"
    assert normalize_index_symbol("BANKNIFTY") == "BANKNIFTY"
    assert normalize_index_symbol("SENSEX") == "SENSEX"
    assert normalize_index_symbol("UNKNOWN") == "UNKNOWN"


def test_simulated_chain_supported_symbols():
    for sym in ("NIFTY50-INDEX", "NIFTYBANK-INDEX", "FINNIFTY-INDEX", "SENSEX-INDEX"):
        chain = option_chain_engine._generate_simulated_chain(sym)
        assert chain is not None, sym
        assert chain.get("mock") is True
        assert len(chain["optionChain"]) > 0
        assert len(chain["expiries"]) == 1
        row = chain["optionChain"][0]
        assert "call" in row and "put" in row
        assert "ltp" in row["call"] and "iv" in row["put"]


def test_simulated_chain_unsupported_returns_none():
    assert option_chain_engine._generate_simulated_chain("CRUDEOIL") is None


def test_simulated_chain_around_atm():
    chain = option_chain_engine._generate_simulated_chain("NIFTY")
    strikes = [r["strike"] for r in chain["optionChain"]]
    assert len(strikes) == 19
    assert strikes == sorted(strikes)
    assert all(s > 0 for s in strikes)


def test_pcr_and_max_pain_on_simulated():
    chain = option_chain_engine._generate_simulated_chain("BANKNIFTY")
    pcr = option_chain_engine.calculate_pcr(chain)
    assert 0 <= pcr <= 1
    mp = option_chain_engine.calculate_max_pain(chain)
    assert mp in [r["strike"] for r in chain["optionChain"]]
